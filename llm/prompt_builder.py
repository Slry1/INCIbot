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
    ) -> str:

        history_text = ""
        if history:
            history_text = "\nИстория предыдущих запросов:\n"
            for i, h in enumerate(history[-5:], 1):
                history_text += f"{i}. {h.user_message[:100]}...\n"

        rag_context = ""
        if rag:
            rag_context = rag.enrich_prompt(ingredients)

        prompt = f"""{rag_context}
Пользовательские параметры:
- Тип кожи: {skin_type if skin_type else "не указан"}
- Аллергены: {allergens if allergens else "не указаны"}
- Предпочтения: {preferences if preferences else "не указаны"}
- Название средства: {name if name else "не указано"}

Текущий состав для оценки:
<ingredients>
{ingredients}
</ingredients>
"""
        return prompt