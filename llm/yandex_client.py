import aiohttp
import asyncio
import json
import re
from typing import Optional, Dict, Any
from loguru import logger
from config import config


_TIMEOUT_CONNECT  = 5
_TIMEOUT_SOCK_READ = 45
_TIMEOUT_TOTAL    = 55


class YandexGPTClient:

    def __init__(self):
        self.api_key    = config.YANDEX_API_KEY
        self.project_id = config.YANDEX_FOLDER_ID
        self.prompt_id  = config.YANDEX_PROMPT_ID
        self.base_url   = "https://ai.api.cloud.yandex.net/v1"
        self.max_retries = 3
        self.retry_delay = 1.0

    async def _make_request(
        self,
        user_input: str,
    ) -> tuple[Optional[str], Optional[Dict]]:

        prompt_id = self.prompt_id

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self.api_key}",
            "OpenAI-Project": self.project_id,
        }
        payload = {
            "prompt": {"id": prompt_id},
            "input": user_input,
        }
        url = f"{self.base_url}/responses"

        timeout = aiohttp.ClientTimeout(
            connect=_TIMEOUT_CONNECT,
            sock_read=_TIMEOUT_SOCK_READ,
            total=_TIMEOUT_TOTAL,
        )

        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=timeout,
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            token_info = self._extract_token_info(result)
                            if token_info:
                                cost = (
                                    token_info.get("input_tokens", 0) * 0.0005
                                    + token_info.get("output_tokens", 0) * 0.0008
                                )
                                logger.info(
                                    f"Токены: input={token_info.get('input_tokens', 0)}, "
                                    f"output={token_info.get('output_tokens', 0)}, "
                                    f"total={token_info.get('total_tokens', 0)}, "
                                    f"стоимость={cost:.4f} руб."
                                )
                            text = self._extract_text_from_response(result)
                            return text, token_info

                        elif response.status == 429:
                            retry_after = int(response.headers.get("Retry-After", 10))
                            logger.warning(
                                f"Yandex API 429 Rate Limit, "
                                f"ждём {retry_after} сек (attempt {attempt+1})"
                            )
                            await asyncio.sleep(retry_after)
                            continue

                        elif response.status >= 500:
                            error_text = await response.text()
                            logger.warning(
                                f"Yandex API {response.status} (attempt {attempt+1}): "
                                f"{error_text[:200]}"
                            )

                        else:
                            error_text = await response.text()
                            logger.error(
                                f"Yandex API {response.status}: {error_text[:200]}"
                            )
                            return None, None

            except asyncio.TimeoutError:
                logger.warning(
                    f"Timeout (attempt {attempt+1}/{self.max_retries}): "
                    f"connect={_TIMEOUT_CONNECT}s, read={_TIMEOUT_SOCK_READ}s"
                )
            except aiohttp.ServerDisconnectedError:
                logger.warning(f"Server disconnected (attempt {attempt+1})")
            except Exception as e:
                logger.error(f"Request error: {e}")

            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (2 ** attempt)
                logger.debug(f"Retry через {delay:.1f} сек")
                await asyncio.sleep(delay)

        return None, None

    def _extract_text_from_response(self, result: Dict) -> Optional[str]:
        if not isinstance(result, dict):
            return str(result)
        if "output" in result and isinstance(result["output"], list):
            for output_item in result["output"]:
                if "content" in output_item and isinstance(output_item["content"], list):
                    for content_item in output_item["content"]:
                        if "text" in content_item:
                            return content_item["text"]
        if "content" in result and isinstance(result["content"], list):
            for item in result["content"]:
                if "text" in item:
                    return item["text"]
        if "text" in result:
            return result["text"]
        logger.warning(f"Could not extract text from response: {result}")
        return str(result)

    def _extract_token_info(self, result: Dict) -> Optional[Dict]:
        if not isinstance(result, dict):
            return None
        if "usage" in result and isinstance(result["usage"], dict):
            usage = result["usage"]
            return {
                "input_tokens":  usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens":  usage.get("total_tokens", 0),
            }
        if "completionOptions" in result:
            opts = result["completionOptions"]
            return {
                "input_tokens":  opts.get("input_tokens", 0),
                "output_tokens": opts.get("output_tokens", 0),
                "total_tokens":  opts.get("total_tokens", 0),
            }
        return None

    async def generate_response(
        self,
        prompt: str,
        use_deepseek: bool = False,
    ) -> Optional[Dict[str, Any]]:

        raw_response, token_info = await self._make_request(prompt, use_deepseek)

        if raw_response is None:
            return {
                "score": 5,
                "explanation": "Не удалось получить ответ от API",
                "warnings": [],
                "recommendations": ["Попробуйте повторить запрос позже"],
                "tokens": token_info or {},
            }

        text_to_parse = raw_response if isinstance(raw_response, str) else str(raw_response)
        cleaned = text_to_parse.strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        json_match = re.search(r'\{[^{}]*"score"[^{}]*\}', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group()

        logger.debug(f"Cleaned response: {cleaned[:200]}...")

        try:
            parsed = json.loads(cleaned)

            if "score" in parsed:
                try:
                    parsed["score"] = int(float(parsed["score"]))
                    if not (0 <= parsed["score"] <= 10):
                        logger.warning(
                            f"Score вне диапазона: {parsed['score']} — сброс до 5"
                        )
                        parsed["score"] = 5
                except (ValueError, TypeError):
                    parsed["score"] = 5

            if "explanation" not in parsed:
                parsed["explanation"] = text_to_parse[:200]
            else:
                parsed["explanation"] = str(parsed["explanation"])[:1000]

            if "warnings" not in parsed:
                parsed["warnings"] = []
            elif not isinstance(parsed["warnings"], list):
                parsed["warnings"] = [str(parsed["warnings"])]
            else:
                parsed["warnings"] = [
                    str(w)[:300] for w in parsed["warnings"][:10]
                ]

            if "recommendations" not in parsed:
                parsed["recommendations"] = []
            elif not isinstance(parsed["recommendations"], list):
                parsed["recommendations"] = [str(parsed["recommendations"])]
            else:
                parsed["recommendations"] = [
                    str(r)[:300] for r in parsed["recommendations"][:10]
                ]

            parsed["tokens"] = token_info or {}

            logger.info(
                f"Ответ получен: score={parsed.get('score')}, "
                f"токены={parsed.get('tokens', {}).get('total_tokens', 'N/A')}"
            )
            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}\nResponse: {cleaned[:500]}")
            return {
                "score": 5,
                "explanation": text_to_parse[:200] if text_to_parse else "Ошибка обработки ответа",
                "warnings": [],
                "recommendations": ["Проверьте формат запроса"],
                "tokens": token_info or {},
            }