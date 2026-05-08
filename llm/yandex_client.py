import aiohttp
import asyncio
import json
import re
from typing import Optional, Dict, Any
from loguru import logger
from config import config


class YandexGPTClient:

    def __init__(self):
        self.api_key = config.YANDEX_API_KEY
        self.project_id = config.YANDEX_FOLDER_ID
        self.prompt_id = config.YANDEX_PROMPT_ID
        self.base_url = "https://ai.api.cloud.yandex.net/v1"
        self.max_retries = 3
        self.retry_delay = 1.0

    async def _make_request(self, user_input: str) -> tuple[Optional[str], Optional[Dict]]:

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self.api_key}",
            "OpenAI-Project": self.project_id
        }

        payload = {
            "prompt": {
                "id": self.prompt_id
            },
            "input": user_input
        }

        url = f"{self.base_url}/responses"

        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                            url,
                            headers=headers,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=60)
                    ) as response:
                        if response.status == 200:
                            result = await response.json()

                            token_info = self._extract_token_info(result)
                            if token_info:
                                logger.info(
                                    f"📊 Токены: input={token_info.get('input_tokens', 0)}, "
                                    f"output={token_info.get('output_tokens', 0)}, "
                                    f"total={token_info.get('total_tokens', 0)}"
                                    f"Стоимость={(token_info.get('input_tokens', 0)*0.0005 + token_info.get('output_tokens', 0)*0.0008)} Рублей"
                                )
                            text = self._extract_text_from_response(result)
                            return text, token_info
                        else:
                            error_text = await response.text()
                            logger.error(f"Yandex API error: {response.status} - {error_text}")

            except asyncio.TimeoutError:
                logger.warning(f"Timeout attempt {attempt + 1}/{self.max_retries}")
            except Exception as e:
                logger.error(f"Request error: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (2 ** attempt))

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
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            }

        if "completionOptions" in result:
            opts = result["completionOptions"]
            return {
                "input_tokens": opts.get("input_tokens", 0),
                "output_tokens": opts.get("output_tokens", 0),
                "total_tokens": opts.get("total_tokens", 0)
            }

        return None

    async def generate_response(self, prompt: str) -> Optional[Dict[str, Any]]:
        raw_response, token_info = await self._make_request(prompt)

        if raw_response is None:
            return {
                "score": 5,
                "explanation": "Не удалось получить ответ от API",
                "warnings": [],
                "recommendations": ["Попробуйте повторить запрос позже"],
                "tokens": token_info or {}
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

        logger.debug(f"Prompt: {prompt} \n" f"Cleaned response for parsing: {cleaned[:200]}...")

        try:
            parsed = json.loads(cleaned)

            if "score" in parsed:
                try:
                    parsed["score"] = int(float(parsed["score"]))
                except (ValueError, TypeError):
                    parsed["score"] = 5

            if "explanation" not in parsed:
                parsed["explanation"] = text_to_parse[:200]
            if "warnings" not in parsed:
                parsed["warnings"] = []
            if "recommendations" not in parsed:
                parsed["recommendations"] = []

            if not isinstance(parsed["warnings"], list):
                parsed["warnings"] = [str(parsed["warnings"])]
            if not isinstance(parsed["recommendations"], list):
                parsed["recommendations"] = [str(parsed["recommendations"])]

            parsed["tokens"] = token_info or {}

            logger.info(
                f"✅ Ответ получен: score={parsed.get('score')}, "
                f"токены={parsed.get('tokens', {}).get('total_tokens', 'N/A')}"
            )

            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}\nResponse: {cleaned[:500]}")
            return {
                "score": 5,
                "explanation": text_to_parse[:200] if text_to_parse else "Ошибка обработки ответа",
                "warnings": [],
                "recommendations": ["Проверьте формат запроса"],
                "tokens": token_info or {}
            }