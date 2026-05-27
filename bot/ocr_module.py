import re
import json
import base64
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from difflib import get_close_matches, SequenceMatcher
from typing import Optional

import aiohttp
from loguru import logger

VISION_URL = "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText"
FUZZY_CUTOFF   = 0.82
MIN_INCI_WORDS = 2
MIN_TEXT_LEN   = 30


INCI_KEYWORDS = {
    "aqua", "water", "glycerin", "glycerol", "alcohol", "extract",
    "acid", "oxide", "sodium", "potassium", "parfum", "fragrance",
    "phenoxyethanol", "carbomer", "dimethicone", "silica", "mica",
    "niacinamide", "retinol", "tocopherol", "panthenol", "allantoin",
    "ceramide", "hyaluronic", "peptide", "collagen", "ethylhexyl",
}


COMPOSITION_MARKERS = [
    r"(?:состав|ингредиенты|ingredients?|composition|inci|tarkibi|składniki|içindekiler)"
    r"(?:\s*/\s*[\w]+)*\s*\n",
    r"состав\s*/?\s*[\w]*\s*:",
    r"inci\s*:",
    r"ingredients?\s*:",
    r"composition\s*:",
    r"ингредиенты\s*:",
    r"tarkibi\s*:",
    r"składniki\s*:",
    r"içindekiler\s*:",
    r"[cс][oо][cс][tт][aа][bв]\s*:",
    r"[cс][oо][cс][tт][aа][bв]\s*/?\s*[\w]*\s*\n",
]

END_MARKERS = [
    r"меры\s+предосторожности",
    r"предупреждение",
    r"внимание\s*:",
    r"способ\s+применения",
    r"хранить\s+при",
    r"срок\s+годности",
    r"масс?овая\s+доля",
    r"не\s+глотать",
    r"\bwarning[s]?\b",
    r"\bcaution\b",
    r"keep\s+out\s+of",
    r"do\s+not\s+swallow",
    r"how\s+to\s+use",
    r"\bapply\b",
    r"\bstore\b",
    r"\n[А-ЯЁ][А-ЯЁ\s]{5,}:",
    r"\n(use|how to|нанес|хранить)",
    r"\d{2}[/\.]\d{4}",
    r"www\.",
    r"[A-Z]{2,}-\d{5,}",
    r"\n[A-Z]{2}\d{4,}",
]

NOISE_PATTERNS = [
    r"^\d+[\s\d]*$",
    r"(hamburg|germany|almaniya|россия|russia|гамбург)",
    r"(baki|azerbaijan|azerbaycan)",
    r"(rossiya|moskva|toshkent|o`zbekiston|sergeli|nizami|balashixa)",
    r"(küçəsi|viloyati|tumani|shahri|şəh)",
    r"(istanbul|turkey|maltepe|aydinevler)",
    r"(bucharest|mihai viteazu)",
    r"(tel\.|e-mail|@|\.com|\.ru)",
    r"(ооо|оао|gmbh|ltd|ag|inc)\b",
    r"(дата изг|годен до|best before|exp\.)",
    r"^(ean|артикул|ref|lot|batch)\b",
    r"(дерматологически|протестировано|dermatologically)",
    r"^(без|free|no |sans )",
    r"[а-яё]{4,}",
    r"\b\d{4,}\b",
    r"(пом\.|ком\.|road\.|no:\s*\d)",
    r"^[a-z]{2}\d{4}$",
    r"(warning|pressurised|do not pierce|keep away)",
]

_TRADE_NAMES = [
    r'shea', r'coconut', r'sweet\s+almond', r'almond', r'ivy',
    r'lavender', r'rose', r'chamomile', r'green\s+tea', r'jojoba',
    r'argan', r'sunflower', r'olive', r'linseed', r'flaxseed',
    r'avocado', r'peppermint', r'mint', r'ginger', r'sage', r'clary',
    r'lemon', r'lime', r'orange', r'raspberry', r'rasberry', r'horsetail',
    r'nettle', r'rosemary', r'thyme', r'grapefruit', r'bergamot',
    r'soybean', r'matricaria', r'corn', r'anise', r'cocoa', r'water',
    r'vitamin\s+[a-z]', r'provitamin\s+[a-z]',
    r'[a-z\s\-]+\s+oil', r'[a-z\s\-]+\s+extract', r'[a-z\s\-]+\s+butter',
]
_TRADE_RE = re.compile(
    r'\s*\((?:' + '|'.join(_TRADE_NAMES) + r')[^)]*\)',
    re.IGNORECASE
)

_DUAL_SLASH_RE = re.compile(
    r'^([A-Z][A-Z0-9\s\-/]+?)\s*/\s*[A-Z][A-Z\s]+(OIL|EXTRACT|BUTTER|WATER|POWDER|ACID|GUM).*$',
    re.IGNORECASE
)

EXTRA_INCI = {
    "ALLANTOIN", "PPG-8", "PPG-9", "PPG-10", "PPG-12", "PPG-15",
    "ALPHA-ISOMETHYL IONONE", "HYDROXYACETOPHENONE",
    "TETRAMETHYL ACETYLOCTAHYDRONAPHTHALENES",
    "SODIUM MONOFLUOROPHOSPHATE", "ISOBUTANE", "BUTANE", "PROPANE",
    "SEA SALT", "FRAGRANCE", "AROMA", "DIMETHYL PHENETHYL ACETATE",
    "PINENE", "ALPHA-PINENE", "BETA-PINENE", "3-AMINOPROPANOL",
    "SALVIA SCLAREA OIL", "MENTHA PIPERITA OIL",
    "HELIANTHUS ANNUUS SEED OIL", "PRUNUS AMYGDALUS DULCIS SEED OIL",
    "LINUM USITATISSIMUM SEED OIL", "EQUISETUM ARVENSE EXTRACT",
    "RUBUS IDAEUS LEAF EXTRACT", "ZINGIBER OFFICINALE ROOT EXTRACT",
    "CITRUS LIMON PEEL OIL", "OLEA EUROPAEA FRUIT OIL",
    "PERSEA GRATISSIMA OIL", "COCOS NUCIFERA OIL",
    "GLYCINE SOJA OIL", "CHAMOMILLA RECUTITA FLOWER EXTRACT",
    "PAEONIA OFFICINALIS EXTRACT", "COCO GLYCOSIDE",
    "PARFUM / FRAGRANCE", "PROPANE/BUTANE/ISOBUTANE",
    "WIND PARSNIP ROOT EXTRACT", "LICORICE ROOT EXTRACT",
}


@dataclass
class OCRProcessResult:
    success: bool
    composition: str = ""
    raw_text: str = ""
    exact_rate: float = 0.0
    total_ingredients: int = 0
    corrections: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    error: str = ""
    quality_warnings: list[str] = field(default_factory=list)


class OCRModule:

    def __init__(
        self,
        api_key: str,
        folder_id: str,
        inci_db_path: Optional[str] = None,
    ):
        self.api_key = api_key
        self.folder_id = folder_id
        self._inci_set: set[str] = set()
        self._inci_list: list[str] = []

        if inci_db_path:
            self._load_inci_db(inci_db_path)

    def _load_inci_db(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            for name in raw:
                n = name.strip().upper()
                self._inci_set.add(n)
                self._inci_list.append(n)
            for name in EXTRA_INCI:
                n = name.strip().upper()
                if n not in self._inci_set:
                    self._inci_set.add(n)
                    self._inci_list.append(n)
            logger.info(f"OCR: INCI-база загружена: {len(self._inci_set)} ингредиентов")
        except Exception as e:
            logger.warning(f"OCR: не удалось загрузить INCI-базу: {e}")

    async def _recognize(
        self, photo_bytes: bytes, session: aiohttp.ClientSession
    ) -> tuple[str, str]:
        try:
            content = base64.b64encode(photo_bytes).decode("utf-8")
            if photo_bytes[:3] == b'\xff\xd8\xff':
                mime = "JPEG"
            else:
                mime = "PNG"

            payload = {
                "mimeType": mime,
                "languageCodes": ["ru", "en"],
                "model": "page",
                "content": content,
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {self.api_key}",
                "x-folder-id": self.folder_id,
                "x-data-logging-enabled": "false",
            }
            async with session.post(
                VISION_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return "", f"HTTP {resp.status}: {body[:200]}"
                data = await resp.json()
                text = (
                    data.get("result", {})
                    .get("textAnnotation", {})
                    .get("fullText", "")
                )
                return text, ""
        except asyncio.TimeoutError:
            return "", "Timeout (30s)"
        except Exception as e:
            return "", f"{type(e).__name__}: {e}"

    @staticmethod
    def _extract_block(text: str) -> tuple[str, bool]:
        text_lower = text.lower()
        start_idx = -1

        for pattern in COMPOSITION_MARKERS:
            m = re.search(pattern, text_lower)
            if m:
                start_idx = m.end()
                break

        if start_idx == -1:
            return text, False

        block = text[start_idx:]
        for end_pattern in END_MARKERS:
            m = re.search(end_pattern, block, re.IGNORECASE)
            if m and m.start() > 20:
                block = block[:m.start()]
                break

        return block.strip(), True

    @staticmethod
    def _clean_token(raw: str) -> str:
        s = raw.strip()
        s = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', s)
        s = re.sub(r'(\w)/\s*\n\s*(\w)', r'\1/\2', s)
        s = re.sub(r'\n', ' ', s)
        s = re.sub(r'[*+†‡°"\'`ʼ′""''^]', '', s)
        m = _DUAL_SLASH_RE.match(s)
        if m:
            s = m.group(1).strip()
        s = _TRADE_RE.sub('', s)
        s = re.sub(r'\s*\(?\s*[\d,\.]+\s*%\s*\)?', '', s)
        s = re.sub(r'\bCL\s+(\d)', r'CI \1', s)
        s = re.sub(r'^С[Ii]\s+(\d)', r'CI \1', s)
        s = re.sub(r'[\[\]]', '', s)
        s = re.sub(r'[–—]', '-', s)
        s = re.sub(r'\s+', ' ', s)
        s = s.strip('.,;:-/"\'')
        return s.strip().upper()

    @staticmethod
    def _is_noise(token: str) -> bool:
        t = token.lower()
        if len(token) < 3 or len(token) > 80:
            return True
        if not re.search(r'[a-zA-Z]', token):
            return True
        if re.match(r'^CI\s+\d{4,6}$', token, re.IGNORECASE):
            return False
        for pattern in NOISE_PATTERNS:
            if re.search(pattern, t, re.IGNORECASE):
                return True
        return False

    def _parse_ingredients(self, block: str) -> list[str]:
        block = re.sub(r',\n', ', ', block)
        block = re.sub(r'\n(?=[a-z])', ' ', block)
        block = re.sub(r'(?<=\w)\n(?=[A-Z][a-z])', ' ', block)
        parts = re.split(r'[,;·•]', block)
        result = []
        for part in parts:
            cleaned = self._clean_token(part)
            if cleaned and not self._is_noise(cleaned):
                result.append(cleaned)
        return result

    def _validate_ingredient(self, ingredient: str) -> tuple[str, str, str]:
        upper = ingredient.upper().strip()
        if upper in self._inci_set:
            return "exact", upper, ""

        if self._inci_list:
            close = get_close_matches(upper, self._inci_list, n=1, cutoff=FUZZY_CUTOFF)
            if close:
                return "fuzzy", close[0], f"{upper} → {close[0]}"

        return "unknown", "", ""

    def _validate_and_correct(
        self, ingredients: list[str]
    ) -> tuple[list[str], list[str], list[str], float]:
        corrected = []
        corrections = []
        unknown = []
        exact_count = 0

        for ing in ingredients:
            status, matched, label = self._validate_ingredient(ing)
            if status == "exact":
                corrected.append(ing)
                exact_count += 1
            elif status == "fuzzy":
                corrected.append(matched)
                corrections.append(label)
                exact_count += 1
            else:
                corrected.append(f"[?]{ing}")
                unknown.append(ing)

        rate = exact_count / len(ingredients) * 100 if ingredients else 0.0
        return corrected, corrections, unknown, rate

    async def process_photo(
        self, photo_bytes: bytes, session: aiohttp.ClientSession
    ) -> OCRProcessResult:
        raw_text, error = await self._recognize(photo_bytes, session)
        if error:
            logger.warning(f"OCR: ошибка распознавания: {error}")
            return OCRProcessResult(success=False, error=error)

        if not raw_text or len(raw_text) < MIN_TEXT_LEN:
            return OCRProcessResult(
                success=False,
                raw_text=raw_text,
                error="Текст не распознан — изображение нечёткое или пустое",
            )

        block, marker_found = self._extract_block(raw_text)
        logger.debug(f"OCR: блок {'найден' if marker_found else 'не найден по маркеру'}, {len(block)} симв.")

        text_lower = raw_text.lower()
        inci_hits = sum(1 for kw in INCI_KEYWORDS if kw in text_lower)
        if inci_hits < MIN_INCI_WORDS:
            return OCRProcessResult(
                success=False,
                raw_text=raw_text,
                error="Состав косметического средства не обнаружен на фотографии",
            )

        ingredients = self._parse_ingredients(block)
        if not ingredients:
            ingredients = self._parse_ingredients(raw_text)

        if not ingredients:
            return OCRProcessResult(
                success=False,
                raw_text=raw_text,
                error="Не удалось извлечь ингредиенты из текста",
            )

        corrected, corrections, unknown, exact_rate = self._validate_and_correct(ingredients)

        quality_warnings: list[str] = []
        total_raw_tokens = len(re.split(r'[,;·•]', block)) if block else 0

        if len(ingredients) < 5:
            quality_warnings.append(
                f"Распознано только {len(ingredients)} ингредиент(а) — состав вероятно неполный. "
                "Возможно, часть этикетки не попала в кадр или текст обрезан."
            )
        elif len(ingredients) < 10 and total_raw_tokens > len(ingredients) * 2:
            quality_warnings.append(
                f"Распознано {len(ingredients)} ингредиентов — состав может быть неполным."
            )

        unknown_rate = len(unknown) / len(ingredients) * 100 if ingredients else 0
        if unknown_rate > 40:
            quality_warnings.append(
                f"Низкое качество распознавания: {unknown_rate:.0f}% токенов не идентифицированы как INCI. "
                "Оценка может быть неточной."
            )

        composition = ", ".join(corrected)

        logger.info(
            f"OCR: {len(ingredients)} ингредиентов, "
            f"точность {exact_rate:.1f}%, "
            f"исправлений {len(corrections)}, "
            f"неизвестных {len(unknown)}"
        )

        return OCRProcessResult(
            success=True,
            composition=composition,
            raw_text=raw_text,
            exact_rate=exact_rate,
            total_ingredients=len(ingredients),
            corrections=corrections,
            unknown=unknown,
            quality_warnings=quality_warnings,
        )