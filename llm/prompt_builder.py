from typing import List, Any, Optional
from llm.rag_module import IngredientRAG


class PromptBuilder:

    @staticmethod
    def build_prompt(
            skin_type: str,
            allergens: List[str],
            preferences: List[str],
            ingredients: str,
            name: str,
            history: List[Any] = None,
            rag: Optional['IngredientRAG'] = None,
            ocr_warnings: Optional[List[str]] = None,
    ) -> str:

        rag_context = ""
        if rag:
            rag_context = rag.enrich_prompt(ingredients)

        # Блок предупреждений о качестве OCR-распознавания
        ocr_note = ""
        if ocr_warnings:
            warnings_text = "\n".join(f"- {w}" for w in ocr_warnings)
            ocr_note = f"""
ПРИМЕЧАНИЕ ОБ ИСТОЧНИКЕ СОСТАВА

Состав получен методом OCR (распознавание текста с фотографии этикетки). Обрати внимание:
{warnings_text}

Учитывай это при формировании оценки: если состав неполный или содержит нераспознанные токены, отрази это в explanation и warnings.
"""

        prompt = f"""{rag_context}
Пользовательские параметры:
- Тип кожи: {skin_type if skin_type else "не указан"}
- Аллергены: {allergens if allergens else "не указаны"}
- Предпочтения: {preferences if preferences else "не указаны"}
- Название средства: {name if name else "не указано"}
{ocr_note}
Текущий состав для оценки:
<ingredients>
{ingredients}
</ingredients>
"""
        return prompt