import re
import asyncio
import json
from typing import Optional, List
from dataclasses import dataclass
from bisect import bisect
import requests
import aiohttp
from bs4 import BeautifulSoup
from loguru import logger

BASKET_ENDS = [
    143, 287, 431, 719, 1007, 1061, 1115, 1169, 1313, 1601,
    1655, 1919, 2045, 2189, 2405, 2621, 2837, 3053, 3269, 3485,
    3701, 3917, 4133, 4349, 4565, 4877, 5189, 5501, 5813, 6125,
    6437, 6749, 7061, 7373, 7685, 7997, 8309, 8741, 9173, 9605,
    10373, 11141, 11909, 12677, 13445, 14213
]

@dataclass
class ProductInfo:
    name: str
    brand: str
    ingredients: str
    source_url: str
    source: str  # "wildberries" | "search"

    def __str__(self):
        return (
            f"🛍 <b>{self.name}</b> ({self.brand})\n"
            f"🔗 Источник: {self.source_url}\n\n"
            f"📋 Состав:\n{self.ingredients}"
        )


class WildberriesParser:
    SEARCH_API = "https://www.wildberries.ru/__internal/search/exactmatch/ru/common/v18/search"
    CDN_TEMPLATE = "https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{nm}/info/ru/card.json"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }

    @staticmethod
    def extract_article(url: str) -> Optional[str]:
        """Извлекает артикул из URL вида https://www.wildberries.ru/catalog/12345678/detail.aspx"""
        match = re.search(r"/catalog/(\d+)/", url)
        return match.group(1) if match else None

    @staticmethod
    def calc_numb_basket(short_id: int) -> str:
        basket = bisect(BASKET_ENDS, short_id) + 1
        return f"{basket:02d}"

    async def fetch_card_data(
        self, session: aiohttp.ClientSession, nm_id: int
    ) -> Optional[dict]:
        vol = nm_id // 100000
        part = nm_id // 1000
        basket = self.calc_numb_basket(vol)

        if not basket:
            logger.warning(f"Cannot find basket for NM {nm_id}")
            return None

        url = self.CDN_TEMPLATE.format(
            basket=basket, vol=vol, part=part, nm=nm_id
        )

        try:
            async with session.get(
                url, headers=self.HEADERS,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"CDN fetch error for NM {nm_id}: {e}")
            return None

    @staticmethod
    def _extract_composition(data: dict) -> Optional[str]:
        for option in data.get('options', []):
            if option.get('name') == 'Состав':
                return option.get('value')

        for group in data.get('grouped_options', []):
            for option in group.get('options', []):
                if option.get('name') == 'Состав':
                    return option.get('value')

        compositions = data.get('compositions', [])
        if compositions:
            return '; '.join(
                comp.get('name', '') for comp in compositions
            )

        return None

    @staticmethod
    def _extract_ingredients_from_text(text: str) -> Optional[str]:
        if not text:
            return None

        patterns = [
            r"(?:^|\n)[Сс]остав\s*:?\s*(.+?)(?:\n\n|\n[А-Я]|\Z)",
            r"Ingredients?\s*:?\s*(.+?)(?:\n\n|\Z)",
            r"INCI\s*:?\s*(.+?)(?:\n\n|\Z)",
        ]

        for p in patterns:
            m = re.search(p, text, re.DOTALL)
            if m:
                ingredients = m.group(1).strip()
                if len(ingredients) > 20 and (
                    ',' in ingredients or ';' in ingredients or
                    'Aqua' in ingredients or 'Water' in ingredients or
                    'вода' in ingredients.lower()
                ):
                    return ingredients

        return None

    async def fetch_by_article(
        self, session: aiohttp.ClientSession, article: str
    ) -> Optional[ProductInfo]:
        nm_id = int(article)
        data = await self.fetch_card_data(session, nm_id)

        if not data:
            return None

        name = data.get('imt_name', 'Без названия')
        brand = data.get('selling', {}).get('brand_name', '')

        # Получаем состав из options/compositions
        ingredients = self._extract_composition(data)

        # Если не нашли — ищем в описании
        if not ingredients:
            description = data.get('description', '')
            ingredients = self._extract_ingredients_from_text(description)

        url = f"https://www.wildberries.ru/catalog/{article}/detail.aspx"
        return ProductInfo(
            name=name,
            brand=brand,
            ingredients=ingredients or "Состав не найден",
            source_url=url,
            source="wildberries",
        )

    def fetch_by_article_sync(self, article: str) -> Optional[ProductInfo]:
        nm_id = int(article)
        vol = nm_id // 100000
        part = nm_id // 1000
        basket = self.calc_numb_basket(vol)

        if not basket:
            return None

        url = self.CDN_TEMPLATE.format(basket=basket, vol=vol, part=part, nm=nm_id)

        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
        except Exception as e:
            logger.error(f"CDN fetch error: {e}")
            return None

        name = data.get('imt_name', 'Без названия')
        brand = data.get('selling', {}).get('brand_name', '')
        ingredients = self._extract_composition(data)

        if not ingredients:
            description = data.get('description', '')
            ingredients = self._extract_ingredients_from_text(description)

        url = f"https://www.wildberries.ru/catalog/{article}/detail.aspx"
        return ProductInfo(
            name=name,
            brand=brand,
            ingredients=ingredients or "Состав не найден",
            source_url=url,
            source="wildberries",
        )

    def search_sync(self, query: str) -> Optional[ProductInfo]:
        """Поиск по названию через синхронный requests"""

        cookies = {
            #<WB Cookies>
        }

        headers = {
            #<Your headers>
        }

        params = {
            'ab_testid': 'promo_mask_test_2',
            'appType': '1',
            'curr': 'rub',
            'dest': '-5818883',
            'hide_vflags': '4294967296',
            'inheritFilters': 'false',
            'lang': 'ru',
            'locale': 'ru',
            'query': query,
            'resultset': 'catalog',
            'sort': 'popular',
            'spp': '30',
            'suppressSpellcheck': 'false',
            'uclusters': '3',
        }

        try:
            resp = requests.get(
                self.SEARCH_API,
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=15
            )

            if resp.status_code == 200:
                logger.info(resp)
            if resp.status_code != 200:
                logger.error(f"Search returned {resp.status_code}")
                return None

            data = resp.json()

        except Exception as e:
            logger.error(f"WB search error: {e}")
            return None

        products = data.get("products", [])

        if not products:
            logger.warning(f"No products found for query: {query}")
            return None

        article = str(products[0]["id"])
        logger.info(f"Found article: {article}")

        return self.fetch_by_article_sync(article)

    def search_sync_multiple(self, query: str, limit: int = 5) -> List[dict]:

        cookies = {
            #<WB Cookies>
        }

        headers = {
            #<Your headers>
        }

        params = {
            'ab_testid': 'promo_mask_test_2',
            'appType': '1',
            'curr': 'rub',
            'dest': '-5818883',
            'hide_vflags': '4294967296',
            'inheritFilters': 'false',
            'lang': 'ru',
            'locale': 'ru',
            'query': query,
            'resultset': 'catalog',
            'sort': 'popular',
            'spp': '30',
            'suppressSpellcheck': 'false',
            'uclusters': '3',
        }

        try:
            resp = requests.get(
                self.SEARCH_API,
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=15
            )

            if resp.status_code != 200:
                logger.error(f"Search returned {resp.status_code}")
                return []

            data = resp.json()

        except Exception as e:
            logger.error(f"WB search error: {e}")
            return []

        products = data.get("products", [])

        if not products:
            return []

        results = []
        for p in products[:limit]:
            try:
                price = p.get('sizes', [{}])[0].get('price', {}).get('product', 0) // 100
            except (IndexError, KeyError, TypeError):
                price = 0
            results.append({
                'id': p.get('id'),
                'name': p.get('name', 'Без названия'),
                'brand': p.get('brand', 'Неизвестный бренд'),
                'price': price,
                'rating': p.get('reviewRating', 0),
                'feedbacks': p.get('feedbacks', 0),
            })

        return results


class CosmeticParser:
    def __init__(self):
        self.wb = WildberriesParser()

    @staticmethod
    def detect_source(text: str) -> str:
        """Определяет источник по тексту (URL или название)."""
        text_lower = text.lower()
        if "wildberries.ru" in text_lower or "wb.ru" in text_lower:
            return "wildberries_url"
        if "ozon.ru" in text_lower:
            return "ozon_url"
        if "goldapple.ru" in text_lower:
            return "goldapple_url"
        # Если похоже на URL без домена
        if text_lower.startswith("http") or "/" in text_lower:
            return "unknown_url"
        return "search"

    @staticmethod
    def looks_like_search_query(text: str) -> bool:
        stripped = text.strip()
        comma_count = stripped.count(",")
        word_count = len(stripped.split())
        if comma_count >= 3:
            return False
        if word_count > 15 and comma_count == 0:
            return False
        return word_count <= 10

    async def parse(self, text: str) -> Optional[ProductInfo]:
        source = self.detect_source(text.strip())
        logger.info(f"CosmeticParser: source={source}, input={text[:80]}")

        async with aiohttp.ClientSession() as session:
            if source == "wildberries_url":
                article = self.wb.extract_article(text)
                if article:
                    return await self.wb.fetch_by_article(session, article)
                return None

            elif source == "search":
                logger.info(f"Searching WB for: {text}")
                return await asyncio.to_thread(
                    self.wb.search_sync, text
                )

        return None
