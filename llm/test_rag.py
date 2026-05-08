import pytest
from llm.rag_module import IngredientRAG, RAGStatistics
from llm.prompt_builder import PromptBuilder


# ==================== Фикстура ====================

@pytest.fixture(scope="module")
def rag():
    """Загружает реальную базу знаний (создаётся один раз на все тесты)"""
    return IngredientRAG("data/ingredients.json")


# ==================== Тесты поиска (search) ====================

class TestSearchRealIngredients:
    """Поиск реальных ингредиентов из базы Renude"""

    def test_search_linoleic_acid(self, rag):
        """Точный поиск: Linoleic Acid"""
        result = rag.search("Linoleic Acid")
        assert result is not None, "Linoleic Acid должен быть в базе"
        assert result["name"].lower() == "linoleic acid"
        assert "short_description" in result
        assert "what_does_it_do" in result

    def test_search_safflower_seed_oil(self, rag):
        """Точный поиск: Safflower Seed Oil"""
        result = rag.search("Safflower Seed Oil")
        assert result is not None, "Safflower Seed Oil должен быть в базе"
        assert "safflower" in result["name"].lower()
        assert "short_description" in result

    def test_search_mandelic_acid(self, rag):
        """Точный поиск: Mandelic Acid"""
        result = rag.search("Mandelic Acid")
        assert result is not None, "Mandelic Acid должен быть в базе"
        assert "mandelic" in result["name"].lower()
        assert "short_description" in result

    def test_search_cucumber_extract(self, rag):
        """Точный поиск: Cucumber Extract"""
        result = rag.search("Cucumber Extract")
        assert result is not None, "Cucumber Extract должен быть в базе"
        assert "cucumber" in result["name"].lower()
        assert "short_description" in result

    def test_search_cholesterol(self, rag):
        """Точный поиск: Cholesterol"""
        result = rag.search("Cholesterol")
        assert result is not None, "Cholesterol должен быть в базе"
        assert result["name"].lower() == "cholesterol"
        assert "short_description" in result


class TestSearchCaseInsensitive:
    """Поиск не зависит от регистра"""

    @pytest.mark.parametrize("query,expected_name", [
        ("linoleic acid", "linoleic acid"),
        ("LINOLEIC ACID", "linoleic acid"),
        ("Linoleic acid", "linoleic acid"),
        ("safflower seed oil", "safflower seed oil"),
        ("SAFFLOWER SEED OIL", "safflower seed oil"),
        ("mandelic acid", "mandelic acid"),
        ("MANDELIC ACID", "mandelic acid"),
        ("cucumber extract", "cucumber extract"),
        ("CUCUMBER EXTRACT", "cucumber extract"),
        ("cholesterol", "cholesterol"),
        ("CHOLESTEROL", "cholesterol"),
    ])
    def test_search_case_insensitive(self, rag, query, expected_name):
        """Регистронезависимый поиск"""
        result = rag.search(query)
        assert result is not None, f"Не найден: {query}"
        assert result["name"].lower() == expected_name


class TestSearchWithExtraSpaces:
    """Поиск с лишними пробелами"""

    @pytest.mark.parametrize("query", [
        "  Linoleic Acid",
        "Linoleic Acid  ",
        "  Linoleic  Acid  ",
        "	Safflower Seed Oil	",
        " Mandelic   Acid ",
    ])
    def test_search_trimmed(self, rag, query):
        """Лишние пробелы не мешают поиску"""
        result = rag.search(query)
        assert result is not None, f"Не найден после обрезки пробелов: '{query}'"
        assert "short_description" in result


# ==================== Тесты поиска несуществующих ингредиентов ====================

class TestSearchNonexistent:
    """Поиск того, чего нет в базе"""

    def test_search_nonexistent_simple(self, rag):
        """Простой несуществующий ингредиент"""
        result = rag.search("Unicorn Extract")
        assert result is None

    def test_search_empty_string(self, rag):
        """Пустая строка"""
        result = rag.search("")
        assert result is None

    def test_search_random_text(self, rag):
        """Случайный текст"""
        result = rag.search("абракадабра тест проверка")
        assert result is None



# ==================== Тесты enrich_prompt ====================

class TestEnrichPromptRealIngredients:
    """Формирование справочного блока для промпта LLM"""

    def test_enrich_all_five_known(self, rag):
        """Все 5 ингредиентов известны"""
        composition = (
            "Linoleic Acid, Safflower Seed Oil, Mandelic Acid, "
            "Cucumber Extract, Cholesterol"
        )
        result = rag.enrich_prompt(composition)

        assert "СПРАВОЧНАЯ ИНФОРМАЦИЯ" in result
        assert "Linoleic Acid" in result
        assert "Safflower Seed Oil" in result
        assert "Mandelic Acid" in result
        assert "Cucumber Extract" in result
        assert "Cholesterol" in result

    def test_enrich_all_five_known_reversed_order(self, rag):
        """Порядок ингредиентов не влияет на поиск"""
        composition = (
            "Cholesterol, Cucumber Extract, Safflower Seed Oil, "
            "Mandelic Acid, Linoleic Acid"
        )
        result = rag.enrich_prompt(composition)
        assert "Linoleic Acid" in result
        assert "Safflower Seed Oil" in result
        assert "Mandelic Acid" in result
        assert "Cucumber Extract" in result
        assert "Cholesterol" in result

    def test_enrich_mixed_known_unknown(self, rag):
        """Смесь известных и неизвестных ингредиентов"""
        composition = (
            "Aqua, Linoleic Acid, UnknownThing, Mandelic Acid, "
            "AnotherUnknown, Cholesterol"
        )
        result = rag.enrich_prompt(composition)

        assert "Linoleic Acid" in result
        assert "Mandelic Acid" in result
        assert "Cholesterol" in result

    def test_enrich_single_ingredient(self, rag):
        """Один ингредиент"""
        result = rag.enrich_prompt("Mandelic Acid")
        assert "Mandelic Acid" in result

    def test_enrich_all_unknown(self, rag):
        """Все ингредиенты неизвестны — возврат пустой строки"""
        result = rag.enrich_prompt("Thing1, Thing2, Thing3")
        assert result == ""

    def test_enrich_empty_composition(self, rag):
        """Пустой состав"""
        result = rag.enrich_prompt("")
        assert result == ""

    def test_enrich_includes_all_fields_present(self, rag):
        """Проверка что поля из БД попадают в результат"""
        result = rag.enrich_prompt("Linoleic Acid")

        # Поля которые точно есть в структуре Renude
        assert "Действие:" in result or "what_does_it_do" in result.lower()


# ==================== Тесты интеграции с PromptBuilder ====================

class TestPromptBuilderWithRealRAG:
    """Интеграция RAG с PromptBuilder на реальных данных"""

    def test_build_prompt_with_rag(self, rag):
        """Промпт с RAG содержит справочную информацию"""
        prompt = PromptBuilder.build_prompt(
            skin_type="сухая",
            allergens=["отдушка"],
            preferences=["натуральное"],
            ingredients="Linoleic Acid, Mandelic Acid, Cholesterol",
            name="Тестовый крем",
            rag=rag
        )
        assert "СПРАВОЧНАЯ ИНФОРМАЦИЯ" in prompt
        assert "Linoleic Acid" in prompt
        assert "Mandelic Acid" in prompt
        assert "Cholesterol" in prompt

    def test_build_prompt_without_rag(self, rag):
        """Промпт без RAG не содержит справочной информации"""
        prompt = PromptBuilder.build_prompt(
            skin_type="жирная",
            allergens=[],
            preferences=[],
            ingredients="Linoleic Acid, Safflower Seed Oil",
            name="Тестовое масло",
            rag=None
        )
        assert "СПРАВОЧНАЯ ИНФОРМАЦИЯ" not in prompt

    def test_build_prompt_rag_does_not_break_structure(self, rag):
        """RAG не ломает обязательные секции промпта"""
        prompt = PromptBuilder.build_prompt(
            skin_type="комбинированная",
            allergens=["спирт", "парабены"],
            preferences=["без отдушек", "веган"],
            ingredients="Cucumber Extract, Cholesterol",
            name="Успокаивающий крем",
            rag=rag
        )
        assert "Пользовательские параметры:" in prompt
        assert "Тип кожи: комбинированная" in prompt
        assert "спирт" in prompt
        assert "парабены" in prompt
        assert "Название средства: Успокаивающий крем" in prompt
        assert "Текущий состав для оценки: Cucumber Extract, Cholesterol" in prompt


# ==================== Тесты производительности ====================

class TestPerformance:
    """Быстродействие на реальной базе"""

    def test_search_speed_100_iterations(self, rag):
        """100 поисков — среднее время < 1 мс"""
        import time

        start = time.perf_counter()
        for _ in range(100):
            rag.search("Linoleic Acid")
        elapsed = time.perf_counter() - start

        avg_us = (elapsed / 100) * 1_000_000
        assert avg_us < 1000, f"Слишком медленно: {avg_us:.0f}мкс (ожидалось < 1000мкс)"

    def test_enrich_prompt_speed_100_iterations(self, rag):
        """100 enrich_prompt — среднее время < 5 мс"""
        import time

        composition = (
            "Linoleic Acid, Safflower Seed Oil, Mandelic Acid, "
            "Cucumber Extract, Cholesterol"
        )

        start = time.perf_counter()
        for _ in range(100):
            rag.enrich_prompt(composition)
        elapsed = time.perf_counter() - start

        avg_us = (elapsed / 100) * 1_000_000
        assert avg_us < 5000, f"Слишком медленно: {avg_us:.0f}мкс (ожидалось < 5000мкс)"


# ==================== Запуск ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])