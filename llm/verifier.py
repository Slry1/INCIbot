import json
import aiohttp
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger

from config import config


@dataclass
class VerificationResult:
    verified: bool = True
    hallucinations: list = field(default_factory=list)
    contradictions: list = field(default_factory=list)
    score_penalty: int = 0
    verifier_tokens: dict = field(default_factory=dict)
    # True если верификатор не смог выполнить запрос или распарсить ответ
    verifier_failed: bool = False


class ResponseVerifier:

    RESPONSES_URL = "https://ai.api.cloud.yandex.net/v1/responses"

    def __init__(self):
        self.api_key = config.YANDEX_API_KEY
        self.project_id = config.YANDEX_FOLDER_ID
        self.prompt_id = config.YANDEX_PROMPT_ID_VERIFIER
        self.enabled = config.VERIFIER_ENABLED

    @property
    def _is_configured(self) -> bool:
        return bool(self.prompt_id)

    async def verify(
        self,
        ingredients: str,
        llm_response: dict,
        skin_type: str = "",
        allergens: list = None,
    ) -> VerificationResult:

        if not self.enabled:
            return VerificationResult()

        if not self._is_configured:
            logger.warning(
                "Верификатор: YANDEX_PROMPT_ID_VERIFIER не задан в .env — "
                "верификация пропущена"
            )
            return VerificationResult(verifier_failed=True)

        user_input = self._build_input(
            ingredients, llm_response, skin_type, allergens or []
        )

        raw, token_info = await self._call_api(user_input)

        if raw is None:
            logger.warning("Верификатор: не получен ответ от API")
            return VerificationResult(verifier_failed=True)

        result = self._parse_response(raw)
        result.verifier_tokens = token_info or {}

        if not result.verifier_failed:
            self._log_result(result)

        return result

    def apply_corrections(
        self,
        llm_response: dict,
        verification: VerificationResult,
    ) -> dict:
        if verification.verifier_failed or verification.verified:
            llm_response["_verified"] = True
            llm_response["_corrections"] = []
            return llm_response

        corrected = llm_response.copy()
        corrections_log = []

        if verification.score_penalty > 0:
            original_score = corrected.get("score", 5)
            corrected["score"] = max(1, original_score - verification.score_penalty)
            corrections_log.append(
                f"score: {original_score} -> {corrected['score']} "
                f"(penalty={verification.score_penalty})"
            )

        hallucinatory = {
            h["ingredient"].lower() for h in verification.hallucinations
        }

        for field_name in ("warnings", "recommendations"):
            original = corrected.get(field_name, [])
            cleaned = []
            for item in original:
                if any(ing in item.lower() for ing in hallucinatory):
                    corrections_log.append(f"Удалено из {field_name}: \"{item[:80]}\"")
                else:
                    cleaned.append(item)
            corrected[field_name] = cleaned

        if verification.hallucinations:
            corrected["explanation"] = (
                corrected.get("explanation", "")
                + " Часть утверждений была автоматически скорректирована системой верификации."
            )

        corrected["_verified"] = False
        corrected["_corrections"] = corrections_log

        logger.info(f"Верификатор применил коррекции: {corrections_log}")

        return corrected

    def _build_input(
        self,
        ingredients: str,
        llm_response: dict,
        skin_type: str,
        allergens: list,
    ) -> str:
        response_for_check = {
            "score": llm_response.get("score"),
            "explanation": llm_response.get("explanation", ""),
            "warnings": llm_response.get("warnings", []),
            "recommendations": llm_response.get("recommendations", []),
        }
        return (
            f"СОСТАВ:\n{ingredients}\n\n"
            f"ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:\n"
            f"Тип кожи: {skin_type or 'не указан'}\n"
            f"Аллергены: {', '.join(allergens) if allergens else 'не указаны'}\n\n"
            f"ОЦЕНКА ДЛЯ ПРОВЕРКИ:\n"
            f"{json.dumps(response_for_check, ensure_ascii=False, indent=2)}"
        )

    async def _call_api(
        self, user_input: str
    ) -> tuple[Optional[str], Optional[dict]]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self.api_key}",
            "OpenAI-Project": self.project_id,
        }
        payload = {
            "prompt": {
                "id": self.prompt_id
            },
            "input": user_input,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.RESPONSES_URL,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        text = self._extract_text(result)
                        token_info = self._extract_tokens(result)
                        logger.info(
                            f"Верификатор: ответ получен, "
                            f"токены={token_info.get('total_tokens', 'N/A') if token_info else 'N/A'}"
                        )
                        return text, token_info
                    else:
                        error = await response.text()
                        logger.error(
                            f"Верификатор API error {response.status}: {error}"
                        )
                        return None, None

        except asyncio.TimeoutError:
            logger.warning("Верификатор: таймаут запроса")
            return None, None
        except Exception as e:
            logger.error(f"Верификатор: ошибка запроса: {e}")
            return None, None

    def _extract_text(self, result: dict) -> Optional[str]:
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

        logger.warning(f"Верификатор: не удалось извлечь текст из ответа: {result}")
        return None

    def _extract_tokens(self, result: dict) -> Optional[dict]:
        if "usage" in result and isinstance(result["usage"], dict):
            usage = result["usage"]
            return {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
        return None

    def _parse_response(self, raw: str) -> VerificationResult:
        try:
            data = json.loads(raw.strip())
            hallucinations = data.get("hallucinations", [])
            contradictions = data.get("contradictions", [])
            penalty = int(data.get("score_penalty", 0))
            has_issues = bool(hallucinations or contradictions)

            return VerificationResult(
                verified=not has_issues,
                hallucinations=hallucinations,
                contradictions=contradictions,
                score_penalty=penalty,
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                f"Верификатор: не удалось распарсить ответ: {e}\n"
                f"Ответ: {raw[:300]}"
            )
            return VerificationResult(verifier_failed=True)

    def _log_result(self, result: VerificationResult) -> None:
        if result.verified:
            logger.info("Верификатор: ответ прошёл проверку")
        else:
            logger.warning(
                f"Верификатор нашёл проблемы: "
                f"галлюцинации={len(result.hallucinations)}, "
                f"противоречия={len(result.contradictions)}, "
                f"penalty={result.score_penalty}"
            )
            for h in result.hallucinations:
                logger.warning(
                    f"  Галлюцинация: \"{h.get('ingredient')}\" "
                    f"в поле {h.get('found_in')}"
                )
            for c in result.contradictions:
                logger.warning(f"  Противоречие: {c.get('description')}")