import json
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from loguru import logger


class IngredientRAG:
    def __init__(self, kb_path: str = "C:\\Users\\timof\yandexgpt_bot\llm\data\ingredients.json"):
        with open(kb_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.source = data["source"]
        self.ingredients: List[Dict] = data["ingredients"]
        self._build_index()

        logger.info(f"RAG инициализирован: {len(self.ingredients)} ингредиентов из {self.source}")

    def _build_index(self):
        """Строит индекс для быстрого поиска"""
        self.exact_index = {}  # точное совпадение имени
        self.sci_index = {}  # по научному названию
        self.word_index = {}  # по отдельным словам

        for ing in self.ingredients:
            name = ing["name"].lower().strip()
            self.exact_index[name] = ing

            for word in re.split(r'[\s/-]+', name):
                if len(word) > 2:
                    if word not in self.word_index:
                        self.word_index[word] = []
                    self.word_index[word].append(ing)

    STOP_WORDS = {
        'extract', 'oil', 'acid', 'water', 'powder', 'juice',
        'butter', 'wax', 'seed', 'fruit', 'leaf', 'root',
        'flower', 'peel', 'kernel', 'milk', 'protein',
        'extract', 'oil', 'water', 'powder', 'juice',
        'sodium', 'potassium', 'magnesium', 'calcium',
        'alcohol', 'glycol', 'glycerin', 'sorbitan',
        'cetearyl', 'cetyl', 'stearyl', 'stearate',
    }

    def search(self, ingredient_text: str) -> Optional[Dict]:
        text = ingredient_text.strip()
        text = re.sub(r'[\n\r\t]+', ', ', text)  # переносы строк → пробелы
        text = re.sub(r'\s+', ' ', text)  # множественные пробелы → один
        text = text.strip()
        text_lower = text.lower()


        if not text_lower:
            return None

        # 1. Точное совпадение
        if text_lower in self.exact_index:
            return self.exact_index[text_lower]

        # 2. Совпадение без скобок
        cleaned = re.sub(r'\([^)]*\)', '', text_lower).strip()
        if cleaned and cleaned != text_lower and cleaned in self.exact_index:
            return self.exact_index[cleaned]

        # 3. Поиск по научному названию
        if hasattr(self, 'sci_index') and text_lower in self.sci_index:
            return self.sci_index[text_lower]

        # 4. Частичное совпадение проверяем ПАРЫ соседних слов из запроса
        words = re.split(r'[\s/-]+', text_lower)
        words = [w for w in words if w]  # убираем пустые

        # Если одно слово и оно стоп-слово — не ищем
        if len(words) == 1 and words[0] in self.STOP_WORDS:
            return None

        # Если несколько слов — ищем точное вхождение ПАРЫ слов
        if len(words) >= 2:
            for i in range(len(words) - 1):
                pair = f"{words[i]} {words[i + 1]}"
                # Ищем в названиях ингредиентов
                for name, ing in self.exact_index.items():
                    if pair in name:
                        return ing

            # Ищем одно значимое слово (не стоп-слово)
            significant_words = [w for w in words if w not in self.STOP_WORDS and len(w) > 2]
            if significant_words:
                # Ищем самое длинное значимое слово в названиях
                for word in sorted(significant_words, key=len, reverse=True):
                    for name, ing in self.exact_index.items():
                        if word in name.split():
                            return ing
            return None

        # 5. Одно слово (не стоп-слово) — ищем точное совпадение в названиях
        if len(words) == 1 and words[0] not in self.STOP_WORDS:
            word = words[0]
            if word in self.word_index:
                candidates = self.word_index[word]
                if len(candidates) == 1:
                    return candidates[0]
                # Если несколько — ищем где слово является точным названием
                for ing in candidates:
                    if ing["name"].lower() == word:
                        return ing

        return None

    def enrich_prompt(self, ingredients_text: str) -> str:
        ingredient_list = [i.strip() for i in ingredients_text.split(",") if i.strip()]

        found_ingredients = []
        not_found_count = 0

        for ing_text in ingredient_list:
            info = self.search(ing_text)
            if info:
                found_ingredients.append(info)
            else:
                not_found_count += 1

        if not found_ingredients:
            return ""

        blocks = []
        blocks.append("=== СПРАВОЧНАЯ ИНФОРМАЦИЯ ОБ ИНГРЕДИЕНТАХ ===")
        blocks.append("")

        for ing in found_ingredients:
            block = f"• {ing['name']}"
            block += ":"

            if ing.get('what_does_it_do'):
                block += f"\n  Действие: {ing['what_does_it_do']}"
            if ing.get('who_is_it_good_for'):
                block += f"\n  Подходит для: {ing['who_is_it_good_for']}"
            if ing.get('who_should_avoid'):
                block += f"\n  Кому избегать: {ing['who_should_avoid']}"

            blocks.append(block)
            blocks.append("")

        blocks.append("=== КОНЕЦ СПРАВКИ ===")

        return "\n".join(blocks)


class RAGStatistics:

    def __init__(self):
        self.total_searches = 0
        self.exact_matches = 0
        self.partial_matches = 0
        self.not_found = 0

    def record_match(self, match_type: str):
        self.total_searches += 1
        if match_type == "exact":
            self.exact_matches += 1
        elif match_type == "partial":
            self.partial_matches += 1
        else:
            self.not_found += 1

    @property
    def coverage_rate(self) -> float:
        if self.total_searches == 0:
            return 0.0
        return (self.exact_matches + self.partial_matches) / self.total_searches * 100

    def report(self) -> str:
        return (
            f"RAG Статистика: всего поисков={self.total_searches}, "
            f"точных={self.exact_matches}, частичных={self.partial_matches}, "
            f"не найдено={self.not_found}, "
            f"покрытие={self.coverage_rate:.1f}%"
        )