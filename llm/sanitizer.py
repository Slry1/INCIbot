import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from loguru import logger


class ThreatLevel(Enum):
    NONE = "none"
    LOW = "low"
    HIGH = "high"


@dataclass
class SanitizationResult:
    is_safe: bool
    threat_level: ThreatLevel
    threat_type: Optional[str]
    detail: Optional[str]

_HIGH_PATTERNS: list[tuple[str, str]] = [
    (r"игнорируй\s+(все\s+)?предыдущие\s+инструкции",                                        "override_ru"),
    (r"ignore\s+(all\s+)?previous\s+instructions",                                           "override_en"),
    (r"забудь\s+(все\s+)?что\s+тебе\s+(говорили|сказали)",                                   "forget_ru"),
    (r"forget\s+(everything|all)\s+(you('ve)?\s+been\s+told|above)",                         "forget_en"),
    (r"ты\s+теперь\s+.{0,60}(бот|ии|модель|ассистент|gpt)",                                  "persona_ru"),
    (r"you\s+are\s+now\s+.{0,60}(bot|ai|model|assistant|gpt)",                               "persona_en"),
    (r"притворись\s+(что\s+ты\s+)?.{0,60}(без\s+ограничений|можешь\s+все)",                  "jailbreak_ru"),
    (r"pretend\s+(you\s+are|to\s+be)\s+.{0,60}(without\s+restrictions|can\s+do\s+anything)", "jailbreak_en"),
    (r"act\s+as\s+(if\s+you\s+are\s+)?dan",                                                  "dan_jailbreak"),
    (r"(поставь|выставь|верни|напиши)\s+(score|оценку|балл)\s*[:\s]\s*10",                   "score_manipulation"),
    (r"(always|всегда)\s+(return|respond|отвечай)\s+(with\s+)?score\s*[:\s]*10",             "score_force"),
    (r"<\s*system\s*>",                                                                      "system_tag"),
    (r"\[INST\]",                                                                            "inst_tag"),
    (r"###\s*(system|instruction|prompt|override)",                                          "section_override"),
    (r"system\s*:\s*(you|ты|ignore|игнорируй)",                                              "system_prefix"),
]

_LOW_PATTERNS: list[tuple[str, str]] = [

    (r"```\s*(json|python|system)",                          "code_block"),
    (r"\{\s*\"role\"\s*:\s*\"system\"",                      "role_system_json"),
    (r"data:text/html",                                      "data_uri"),
    (r"javascript:",                                         "js_injection"),
]


_MAX_INGREDIENTS_LENGTH = 1000


class InputSanitizer:
    @staticmethod
    def check(text: str, source: str = "user") -> SanitizationResult:
        if not text:
            return SanitizationResult(
                is_safe=True,
                threat_level=ThreatLevel.NONE,
                threat_type=None,
                detail=None,
            )

        if len(text) > _MAX_INGREDIENTS_LENGTH:
            logger.warning(
                f"InputSanitizer: превышена длина ({len(text)} символов), "
                f"source={source}"
            )
            return SanitizationResult(
                is_safe=False,
                threat_level=ThreatLevel.LOW,
                threat_type="excessive_length",
                detail=f"длина {len(text)} > {_MAX_INGREDIENTS_LENGTH}",
            )

        for pattern, threat_type in _HIGH_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(
                    f"InputSanitizer: HIGH угроза «{threat_type}», "
                    f"source={source}, "
                    f"фрагмент: {text[:100]!r}"
                )
                return SanitizationResult(
                    is_safe=False,
                    threat_level=ThreatLevel.HIGH,
                    threat_type=threat_type,
                    detail=pattern,
                )

        for pattern, threat_type in _LOW_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.info(
                    f"InputSanitizer: LOW подозрение «{threat_type}», "
                    f"source={source}"
                )
                return SanitizationResult(
                    is_safe=False,
                    threat_level=ThreatLevel.LOW,
                    threat_type=threat_type,
                    detail=pattern,
                )

        return SanitizationResult(
            is_safe=True,
            threat_level=ThreatLevel.NONE,
            threat_type=None,
            detail=None,
        )

    @staticmethod
    def neutralize(text: str) -> str:
        if not text:
            return text

        result = text[:_MAX_INGREDIENTS_LENGTH]

        result = re.sub(r'<(\s*system\s*)', r'&lt;\1', result, flags=re.IGNORECASE)
        result = re.sub(r'\[INST\]', '[INST_BLOCKED]', result, flags=re.IGNORECASE)

        for word in ('ignore', 'forget', 'system', 'instructions'):
            result = re.sub(
                rf'\b{word}\b',
                word[0] + '\u200b' + word[1:],
                result,
                flags=re.IGNORECASE,
            )

        return result

    @staticmethod
    def check_all(
        ingredients: str,
        name: str = "",
        source: str = "user",
    ) -> SanitizationResult:
        results = [
            InputSanitizer.check(ingredients, source=f"{source}/ingredients"),
            InputSanitizer.check(name, source=f"{source}/name"),
        ]

        for result in results:
            if result.threat_level == ThreatLevel.HIGH:
                return result
        for result in results:
            if result.threat_level == ThreatLevel.LOW:
                return result

        return SanitizationResult(
            is_safe=True,
            threat_level=ThreatLevel.NONE,
            threat_type=None,
            detail=None,
        )
