"""
data/load_ingredients_kb.py
Загрузка и предобработка датасета Renude для RAG-модуля.
"""
import csv
import json
import ast
import re
from pathlib import Path

def clean_text(value: str) -> str:
    """Очищает текст от лишних пробелов, возвращает пустую строку если значение пустое"""
    if value is None:
        return ""
    cleaned = str(value).strip()
    # Если после очистки осталась только пустая строка или пробелы
    return cleaned if cleaned and cleaned != '' else ""

def clean_list_to_string(value: str, keywords_to_remove: list = None) -> str:
    """
    Очищает поле, которое выглядит как список Python, и преобразует в строку через запятую.
    Удаляет указанные ключевые слова.

    Пример: "[' ', 'Acne', ' ', 'Blackheads']" -> "Acne, Blackheads"
    """
    if keywords_to_remove is None:
        keywords_to_remove = ['Related Allergy']

    if not value or value.strip() == '':
        return ""

    try:
        # Пытаемся распарсить как Python literal
        parsed = ast.literal_eval(value)
        if isinstance(parsed, list):
            # Очищаем каждый элемент и убираем пустые/пробельные значения
            cleaned_items = []
            for item in parsed:
                if isinstance(item, str):
                    item_cleaned = item.strip()
                    # Пропускаем пустые значения и ключевые слова для удаления
                    if item_cleaned and item_cleaned != '':
                        # Проверяем, не нужно ли удалить этот элемент
                        should_remove = False
                        for keyword in keywords_to_remove:
                            if keyword.lower() in item_cleaned.lower():
                                should_remove = True
                                break
                        if not should_remove:
                            cleaned_items.append(item_cleaned)

            # Преобразуем в строку через запятую
            return ", ".join(cleaned_items)
    except:
        # Если не парсится, пробуем через regex
        items = re.findall(r"'([^']*)'", value)
        cleaned_items = []
        for item in items:
            item_cleaned = item.strip()
            if item_cleaned and item_cleaned != '':
                should_remove = False
                for keyword in keywords_to_remove:
                    if keyword.lower() in item_cleaned.lower():
                        should_remove = True
                        break
                if not should_remove:
                    cleaned_items.append(item_cleaned)
        return ", ".join(cleaned_items)

    return ""

def load_renude_dataset(csv_path: str = "ingredientsList.csv") -> list[dict]:
    """Загружает CSV и преобразует в список словарей для RAG"""
    ingredients = []

    # Список ключевых слов для удаления
    remove_keywords = [
        'Related Allergy', 'related allergy', 'Related', 'related',
        'Allergy', 'allergy', 'Allergies', 'allergies'
    ]

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Обрабатываем текстовые поля
            ingredient = {
                "name": clean_text(row.get("name", "")),
                "short_description": clean_text(row.get("short_description", "")),
                "what_is_it": clean_text(row.get("what_is_it", "")),
                "what_does_it_do": clean_text(row.get("what_does_it_do", "")),
                "url": clean_text(row.get("url", "")),
            }

            # Специальная обработка для списков - преобразуем в строки
            ingredient["who_is_it_good_for"] = clean_list_to_string(
                row.get("who_is_it_good_for", ""),
                remove_keywords
            )
            ingredient["who_should_avoid"] = clean_list_to_string(
                row.get("who_should_avoid", ""),
                remove_keywords
            )

            if ingredient["name"]:  # только если есть название
                ingredients.append(ingredient)

    print(f"Загружено {len(ingredients)} ингредиентов из Renude")
    return ingredients


def build_search_index(ingredients: list[dict]) -> dict:
    """
    Строит индекс для быстрого поиска по названиям ингредиентов
    """
    index = {}

    for ing in ingredients:
        name_lower = ing["name"].lower()
        # Точное совпадение по названию
        index[name_lower] = ing

        # Отдельные слова из названия (для частичного совпадения)
        for word in name_lower.split():
            if len(word) > 3:  # игнорируем короткие слова
                if word not in index:
                    index[word] = []
                if isinstance(index[word], list):
                    index[word].append(ing)

    return index


if __name__ == "__main__":
    ingredients = load_renude_dataset()
    index = build_search_index(ingredients)

    # Сохраняем в JSON для RAG-модуля
    output_path = Path("ingredients.json")
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "source": "(https://renude.co/ingredients)",
            "total_ingredients": len(ingredients),
            "ingredients": ingredients,
        }, f, ensure_ascii=False, indent=2)

    print(f"База знаний сохранена в {output_path}")