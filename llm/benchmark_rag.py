"""
benchmarks/benchmark_rag_ab.py
Бенчмарк A/B: сравнение ответов LLM с RAG и без RAG.

Используется в Главе 4 ВКР, Раздел 4.X "Влияние RAG на качество оценки".

Запуск:
    python benchmarks/benchmark_rag_ab.py

На выходе:
    results/benchmark_rag_ab.json — сырые данные
    results/benchmark_rag_ab_summary.json — агрегированные метрики
"""
import json
import asyncio
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from pathlib import Path
from loguru import logger

from llm.yandex_client import YandexGPTClient
from llm.prompt_builder import PromptBuilder
from llm.rag_module import IngredientRAG


# Модель для тестирования
MODEL_NAME = "DeepSeek3.2"

# Результаты
OUTPUT_DIR = Path("results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


PROFILES = {
    "A": {"skin_type": "сухая", "allergens": ["отдушка", "лаванда"], "preferences": ["натуральные компоненты"]},
    "B": {"skin_type": "жирная", "allergens": ["спирт", "цитрусы"], "preferences": ["матирующий эффект"]},
    "C": {"skin_type": "чувствительная", "allergens": ["парабены", "отдушка"], "preferences": ["гипоаллергенно"]},
}


RAG_TEST_CASES = [
    {
        "id": "RAG01",
        "name": "Крем с маслом сафлора и линолевой кислотой",
        "ingredients": "Aqua, Safflower Seed Oil, Linoleic Acid, Glycerin, Tocopherol",
        "profile": "A",
        "category": "rag_positive",
        "description": "Все компоненты кроме Aqua есть в RAG-базе",
        "expected_from_rag": [
            "Safflower Seed Oil",  # должен найти в базе
            "Linoleic Acid",
            "Glycerin",
            "Tocopherol",
        ]
    },
    {
        "id": "RAG02",
        "name": "Пилинг с миндальной кислотой",
        "ingredients": "Aqua, Mandelic Acid, Salicylic Acid, Niacinamide, Glycerin",
        "profile": "B",
        "category": "rag_positive",
        "description": "Кислоты для жирной кожи — RAG должен подсказать противопоказания",
        "expected_from_rag": [
            "Mandelic Acid",
            "Salicylic Acid",
            "Niacinamide",
            "Glycerin",
        ]
    },
    {
        "id": "RAG03",
        "name": "Успокаивающий крем с огурцом и холестерином",
        "ingredients": "Aqua, Cucumber Extract, Cholesterol, Tocopherol, Glycerin",
        "profile": "C",
        "category": "rag_positive",
        "description": "Успокаивающие компоненты — RAG должен подтвердить безопасность",
        "expected_from_rag": [
            "Cucumber Extract",
            "Cholesterol",
            "Tocopherol",
            "Glycerin",
        ]
    },
    {
        "id": "RAG04",
        "name": "Крем с отдушкой",
        "ingredients": "Aqua, Glycerin, Cetyl Alcohol, Parfum, Linalool, Limonene",
        "profile": "A",
        "category": "rag_negative",
        "description": "Parfum и отдушки — RAG должен предупредить who_should_avoid",
        "expected_from_rag": [
            "Glycerin",
            "Parfum",  # RAG знает что Parfum — аллерген
        ]
    },
    {
        "id": "RAG05",
        "name": "",
        "ingredients": "Aqua, Dimethicone, Carbomer, Triethanolamine, Phenoxyethanol",
        "profile": "B",
        "category": "rag_none",
        "description": "Ни одного ингредиента из базы Renude",
        "expected_from_rag": []  # Ничего не найдено
    },
    {
        "id": "RAG06",
        "name": "Масло сафлора для жирной кожи",
        "ingredients": "Safflower Seed Oil, Tocopherol",
        "profile": "B",
        "category": "rag_specific",
        "description": "RAG должен подсказать что Safflower подходит для жирной кожи",
        "expected_from_rag": [
            "Safflower Seed Oil",
            "Tocopherol",
        ]
    },
    {
        "id": "RAG07",
        "name": "Сыворотка с линолевой кислотой и ниацинамидом",
        "ingredients": "Aqua, Linoleic Acid, Niacinamide, Salicylic Acid, Glycerin",
        "profile": "B",
        "category": "rag_positive",
        "description": "Много активов — RAG даст доп. информацию по каждому",
        "expected_from_rag": [
            "Linoleic Acid",
            "Niacinamide",
            "Salicylic Acid",
            "Glycerin",
        ]
    },
    {
        "id": "RAG08",
        "name": "Крем с холестерином для сухой кожи",
        "ingredients": "Aqua, Cholesterol, Glycerin, Cetearyl Alcohol, Tocopherol",
        "profile": "A",
        "category": "rag_specific",
        "description": "Холестерин для сухой кожи — RAG должен подтвердить",
        "expected_from_rag": [
            "Cholesterol",
            "Glycerin",
            "Tocopherol",
        ]
    },
    {
        "id": "RAG09",
        "name": "Тоник с огуречным экстрактом и спиртом",
        "ingredients": "Aqua, Alcohol Denat., Cucumber Extract, Menthol",
        "profile": "B",
        "category": "rag_conflict",
        "description": "Конфликт: огурец успокаивает, но спирт раздражает",
        "expected_from_rag": [
            "Cucumber Extract",
        ]
    },
    {
        "id": "RAG10",
        "name": "Пустой/некорректный запрос",
        "ingredients": "",
        "profile": "A",
        "category": "rag_edge",
        "description": "Пустой состав — оба промпта должны вернуть score=0",
        "expected_from_rag": []
    },
]


# ==================== Структуры данных ====================

@dataclass
class ABResult:
    """Результат одного A/B теста"""
    case_id: str
    case_name: str
    profile_id: str
    category: str

    # С RAG
    rag_score: Optional[int]
    rag_explanation: str
    rag_warnings: List[str]
    rag_recommendations: List[str]
    rag_tokens: Dict[str, int]
    rag_time_ms: int
    rag_ingredients_found: int  # сколько ингредиентов найдено в RAG-базе

    # Без RAG
    no_rag_score: Optional[int]
    no_rag_explanation: str
    no_rag_warnings: List[str]
    no_rag_recommendations: List[str]
    no_rag_tokens: Dict[str, int]
    no_rag_time_ms: int

    # Разницы
    score_delta: int  # rag_score - no_rag_score
    time_delta_ms: int  # rag_time_ms - no_rag_time_ms
    tokens_delta: int  # rag_tokens_total - no_rag_tokens_total
    explanation_length_delta: int  # разница в длине пояснения


# ==================== Основной бенчмарк ====================

async def run_ab_benchmark():
    """Запускает A/B тестирование для всех кейсов"""

    # Инициализация
    rag = IngredientRAG()
    client = YandexGPTClient()

    results: List[ABResult] = []

    logger.info(f"{'=' * 60}")
    logger.info(f"🚀 A/B БЕНЧМАРК RAG: {MODEL_NAME}")
    logger.info(f"{'=' * 60}")
    logger.info(f"Кейсов: {len(RAG_TEST_CASES)}")
    logger.info(f"Профилей: {len(PROFILES)}")
    logger.info(f"{'=' * 60}\n")

    for idx, case in enumerate(RAG_TEST_CASES, 1):
        profile = PROFILES[case["profile"]]

        logger.info(f"[{idx}/{len(RAG_TEST_CASES)}] {case['id']}: {case['name']}")
        logger.info(f"  Профиль: {case['profile']} ({profile['skin_type']})")
        logger.info(f"  Категория: {case['category']}")
        logger.info(f"  Состав: {case['ingredients'][:80]}...")

        # === ЗАПРОС С RAG ===
        prompt_rag = PromptBuilder.build_prompt(
            skin_type=profile["skin_type"],
            allergens=profile["allergens"],
            preferences=profile["preferences"],
            ingredients=case["ingredients"],
            name=case["name"],
            history=None,
            rag=rag  # <-- RAG включен
        )

        start_rag = time.monotonic()
        response_rag = await client.generate_response(prompt_rag)
        time_rag = int((time.monotonic() - start_rag) * 1000)

        # Считаем сколько ингредиентов нашлось в RAG
        rag_context = rag.enrich_prompt(case["ingredients"])
        if "Найдено в базе:" in rag_context:
            found_str = rag_context.split("Найдено в базе:")[1].split()[0]
            ingredients_found = int(found_str)
        else:
            ingredients_found = 0

        # Пауза чтобы не упереться в rate limit
        await asyncio.sleep(0.3)

        # === ЗАПРОС БЕЗ RAG ===
        prompt_no_rag = PromptBuilder.build_prompt(
            skin_type=profile["skin_type"],
            allergens=profile["allergens"],
            preferences=profile["preferences"],
            ingredients=case["ingredients"],
            name=case["name"],
            history=None,
            rag=None  # <-- RAG выключен
        )

        start_no_rag = time.monotonic()
        response_no_rag = await client.generate_response(prompt_no_rag)
        time_no_rag = int((time.monotonic() - start_no_rag) * 1000)

        # === ФОРМИРУЕМ РЕЗУЛЬТАТ ===
        result = ABResult(
            case_id=case["id"],
            case_name=case["name"],
            profile_id=case["profile"],
            category=case["category"],

            rag_score=response_rag.get("score"),
            rag_explanation=response_rag.get("explanation", ""),
            rag_warnings=response_rag.get("warnings", []),
            rag_recommendations=response_rag.get("recommendations", []),
            rag_tokens=response_rag.get("tokens", {}),
            rag_time_ms=time_rag,
            rag_ingredients_found=ingredients_found,

            no_rag_score=response_no_rag.get("score"),
            no_rag_explanation=response_no_rag.get("explanation", ""),
            no_rag_warnings=response_no_rag.get("warnings", []),
            no_rag_recommendations=response_no_rag.get("recommendations", []),
            no_rag_tokens=response_no_rag.get("tokens", {}),
            no_rag_time_ms=time_no_rag,

            score_delta=(response_rag.get("score") or 0) - (response_no_rag.get("score") or 0),
            time_delta_ms=time_rag - time_no_rag,
            tokens_delta=(
                    response_rag.get("tokens", {}).get("total_tokens", 0) -
                    response_no_rag.get("tokens", {}).get("total_tokens", 0)
            ),
            explanation_length_delta=len(response_rag.get("explanation", "")) -
                                     len(response_no_rag.get("explanation", "")),
        )

        results.append(result)

        # Краткий вывод в консоль
        logger.info(
            f"  📊 RAG: score={result.rag_score}, {result.rag_time_ms}ms, "
            f"найдено={result.rag_ingredients_found}"
        )
        logger.info(
            f"  📊 NO:  score={result.no_rag_score}, {result.no_rag_time_ms}ms"
        )
        logger.info(
            f"  Δ: score={result.score_delta:+d}, time={result.time_delta_ms:+d}ms, "
            f"tokens={result.tokens_delta:+d}"
        )
        logger.info("")

        await asyncio.sleep(0.5)  # Пауза между кейсами

    # Сохраняем сырые результаты
    raw_output = OUTPUT_DIR / "benchmark_rag_ab.json"
    with open(raw_output, 'w', encoding='utf-8') as f:
        json.dump({
            "model": MODEL_NAME,
            "total_cases": len(results),
            "results": [asdict(r) for r in results],
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"📁 Сырые данные: {raw_output}")

    # Агрегируем и сохраняем сводку
    summary = compute_summary(results)
    summary_output = OUTPUT_DIR / "benchmark_rag_ab_summary.json"
    with open(summary_output, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info(f"📁 Сводка: {summary_output}")

    # Выводим итоги в консоль
    print_summary(summary)

    return results, summary


def compute_summary(results: List[ABResult]) -> Dict[str, Any]:
    """Агрегирует результаты A/B теста"""

    total = len(results)

    # Разбивка по категориям
    categories = {}
    for cat in ["rag_positive", "rag_negative", "rag_none", "rag_specific", "rag_conflict", "rag_edge"]:
        cat_results = [r for r in results if r.category == cat]
        if cat_results:
            categories[cat] = {
                "count": len(cat_results),
                "avg_rag_score": sum(r.rag_score for r in cat_results if r.rag_score) /
                                 max(1, sum(1 for r in cat_results if r.rag_score)),
                "avg_no_rag_score": sum(r.no_rag_score for r in cat_results if r.no_rag_score) /
                                    max(1, sum(1 for r in cat_results if r.no_rag_score)),
                "avg_score_delta": sum(r.score_delta for r in cat_results) / len(cat_results),
                "avg_rag_time_ms": sum(r.rag_time_ms for r in cat_results) / len(cat_results),
                "avg_no_rag_time_ms": sum(r.no_rag_time_ms for r in cat_results) / len(cat_results),
                "avg_rag_ingredients_found": sum(r.rag_ingredients_found for r in cat_results) / len(cat_results),
            }

    # Общие метрики
    valid_results = [r for r in results if r.rag_score is not None and r.no_rag_score is not None]

    return {
        "model": MODEL_NAME,
        "total_cases": total,
        "categories": categories,
        "overall": {
            "avg_rag_score": sum(r.rag_score for r in valid_results) / len(valid_results) if valid_results else 0,
            "avg_no_rag_score": sum(r.no_rag_score for r in valid_results) / len(valid_results) if valid_results else 0,
            "avg_score_delta": sum(r.score_delta for r in valid_results) / len(valid_results) if valid_results else 0,
            "avg_rag_time_ms": sum(r.rag_time_ms for r in results) / total,
            "avg_no_rag_time_ms": sum(r.no_rag_time_ms for r in results) / total,
            "avg_time_overhead_ms": sum(r.time_delta_ms for r in results) / total,
            "avg_tokens_overhead": sum(r.tokens_delta for r in results) / total,
            "avg_ingredients_found": sum(r.rag_ingredients_found for r in results) / total,
            "cases_with_higher_rag_score": sum(1 for r in valid_results if r.score_delta > 0),
            "cases_with_lower_rag_score": sum(1 for r in valid_results if r.score_delta < 0),
            "cases_with_same_score": sum(1 for r in valid_results if r.score_delta == 0),
            "avg_explanation_delta_chars": sum(r.explanation_length_delta for r in results) / total,
        }
    }


def print_summary(summary: Dict[str, Any]):
    """Выводит сводку в консоль"""
    overall = summary["overall"]
    categories = summary["categories"]

    print(f"\n{'=' * 60}")
    print(f"📊 СВОДКА A/B БЕНЧМАРКА RAG: {MODEL_NAME}")
    print(f"{'=' * 60}")
    print(f"Всего кейсов: {summary['total_cases']}")
    print()
    print(f"ОБЩИЕ МЕТРИКИ:")
    print(f"  Средний score с RAG:     {overall['avg_rag_score']:.1f}")
    print(f"  Средний score без RAG:   {overall['avg_no_rag_score']:.1f}")
    print(f"  Средняя Δscore:          {overall['avg_score_delta']:+.1f}")
    print(f"  Score выше с RAG:        {overall['cases_with_higher_rag_score']}")
    print(f"  Score ниже с RAG:        {overall['cases_with_lower_rag_score']}")
    print(f"  Score одинаковый:        {overall['cases_with_same_score']}")
    print()
    print(f"  Среднее время с RAG:     {overall['avg_rag_time_ms']:.0f}ms")
    print(f"  Среднее время без RAG:   {overall['avg_no_rag_time_ms']:.0f}ms")
    print(f"  Накладные расходы RAG:   {overall['avg_time_overhead_ms']:.0f}ms")
    print(f"  Доп. токенов с RAG:      {overall['avg_tokens_overhead']:.0f}")
    print(f"  Среднее найдено в базе:  {overall['avg_ingredients_found']:.1f}")
    print(f"  Δ длины пояснения:       {overall['avg_explanation_delta_chars']:+.0f} символов")
    print()
    print(f"ПО КАТЕГОРИЯМ:")
    for cat, stats in categories.items():
        print(f"  {cat:20s}: rag_score={stats['avg_rag_score']:.1f}, "
              f"no_rag={stats['avg_no_rag_score']:.1f}, "
              f"Δ={stats['avg_score_delta']:+.1f}, "
              f"ингредиентов найдено={stats['avg_rag_ingredients_found']:.1f}")
    print(f"{'=' * 60}\n")


# ==================== Точка входа ====================

async def main():
    await run_ab_benchmark()


if __name__ == "__main__":
    asyncio.run(main())