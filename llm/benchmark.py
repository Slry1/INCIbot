import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from pathlib import Path
from loguru import logger

from llm.yandex_client import YandexGPTClient
from llm.prompt_builder import PromptBuilder


@dataclass
class TestProfile:
    profile_id: str
    skin_type: str
    allergens: List[str]
    preferences: List[str]


@dataclass
class TestCase:
    case_id: str
    name: str  # название средства
    ingredients: str  # состав
    profile: TestProfile
    category: str  # "simple", "medium", "complex", "provocative"
    expected_allergens: List[str] = field(default_factory=list)  # аллергены, которые точно есть в составе
    min_expected_score: Optional[int] = None  # минимальная ожидаемая оценка
    max_expected_score: Optional[int] = None  # максимальная ожидаемая оценка


@dataclass
class TestResult:
    case_id: str
    profile_id: str
    category: str
    model: str
    timestamp: float
    response_time_ms: int
    raw_response: Optional[str]
    parsed_response: Optional[Dict]
    json_valid: bool
    schema_valid: bool
    score: Optional[int]
    explanation: str
    warnings: List[str]
    recommendations: List[str]
    tokens: Dict[str, int]
    error: Optional[str] = None


class LLMBenchmark:
    PROFILES = {
        "A": TestProfile("A", "сухая", ["отдушка", "лаванда"], ["натуральные компоненты"]),
        "B": TestProfile("B", "жирная", ["спирт", "цитрусы"], ["матирующий эффект"]),
        "C": TestProfile("C", "чувствительная", ["парабены", "отдушка"], ["гипоаллергенно"]),
        "D": TestProfile("D", "комбинированная", [], ["без спирта"]),
        "E": TestProfile("E", "нормальная", ["орехи"], ["веганская косметика"]),
    }

    def _get_test_cases(self) -> List[TestCase]:
        """Формирует сбалансированный набор тестовых кейсов"""
        return [
            # === ПРОСТЫЕ (simple): 5 кейсов ===
            TestCase(
                "S01", "Минималистичный крем",
                "Aqua, Glycerin, Aloe Vera Gel, Tocopherol",
                self.PROFILES["A"], "simple",
                expected_allergens=[], min_expected_score=8, max_expected_score=10
            ),
            TestCase(
                "S02", "Базовое масло",
                "Prunus Amygdalus Dulcis Oil, Tocopherol",
                self.PROFILES["E"], "simple",
                expected_allergens=[], min_expected_score=8, max_expected_score=10
            ),
            TestCase(
                "S03", "Гиалуроновая сыворотка",
                "Aqua, Sodium Hyaluronate, Panthenol, Glycerin",
                self.PROFILES["A"], "simple",
                expected_allergens=[], min_expected_score=9, max_expected_score=10
            ),
            TestCase(
                "S04", "Алоэ-гель",
                "Aloe Barbadensis Leaf Juice, Carbomer, Triethanolamine",
                self.PROFILES["C"], "simple",
                expected_allergens=[], min_expected_score=7, max_expected_score=9
            ),
            TestCase(
                "S05", "Простой увлажняющий крем",
                "Aqua, Caprylic/Capric Triglyceride, Glycerin, Cetearyl Alcohol",
                self.PROFILES["D"], "simple",
                expected_allergens=[], min_expected_score=8, max_expected_score=10
            ),

            # === СРЕДНИЕ (medium): 7 кейсов ===
            TestCase(
                "M01", "Крем с отдушкой",
                "Aqua, Glycerin, Cetyl Alcohol, Parfum, Linalool, Limonene",
                self.PROFILES["A"], "medium",
                expected_allergens=["Parfum", "Linalool", "Limonene"],
                max_expected_score=5
            ),
            TestCase(
                "M02", "Тоник со спиртом",
                "Aqua, Alcohol Denat., Salicylic Acid, Hamamelis Virginiana Extract",
                self.PROFILES["B"], "medium",
                expected_allergens=["Alcohol Denat."],
                max_expected_score=5
            ),
            TestCase(
                "M03", "Крем с парабенами",
                "Aqua, Paraffinum Liquidum, Methylparaben, Propylparaben, Parfum",
                self.PROFILES["C"], "medium",
                expected_allergens=["Methylparaben", "Propylparaben", "Parfum"],
                max_expected_score=4
            ),
            TestCase(
                "M04", "Матирующий крем",
                "Aqua, Cyclopentasiloxane, Niacinamide, Zinc PCA, Salicylic Acid",
                self.PROFILES["B"], "medium",
                expected_allergens=[],
                min_expected_score=7, max_expected_score=10
            ),
            TestCase(
                "M05", "Питательный крем с маслами",
                "Aqua, Butyrospermum Parkii Butter, Cocos Nucifera Oil, Lanolin",
                self.PROFILES["B"], "medium",
                expected_allergens=["Cocos Nucifera Oil", "Lanolin"],
                max_expected_score=4
            ),
            TestCase(
                "M06", "Крем с эфирными маслами",
                "Aqua, Lavandula Angustifolia Oil, Citrus Limon Peel Oil, Parfum",
                self.PROFILES["A"], "medium",
                expected_allergens=["Lavandula Angustifolia Oil", "Parfum"],
                max_expected_score=3
            ),
            TestCase(
                "M07", "Сыворотка с кислотами",
                "Aqua, Glycolic Acid, Lactic Acid, Salicylic Acid, Niacinamide",
                self.PROFILES["C"], "medium",
                expected_allergens=["Glycolic Acid"],
                max_expected_score=5
            ),

            # === СЛОЖНЫЕ (complex): 5 кейсов ===
            TestCase(
                "C01", "Профессиональный антивозрастной крем",
                "Aqua, Retinol, Tocopherol, Ascorbic Acid, Ferulic Acid, "
                "Niacinamide, Ceramide NP, Peptide Complex, Hyaluronic Acid, "
                "Parfum, Phenoxyethanol, Ethylhexylglycerin",
                self.PROFILES["C"], "complex",
                expected_allergens=["Parfum", "Retinol"],
                max_expected_score=6
            ),
            TestCase(
                "C02", "Солнцезащитный флюид",
                "Aqua, Homosalate, Octocrylene, Avobenzone, Glycerin, "
                "Dimethicone, Parfum, Tocopherol, Aloe Barbadensis Extract",
                self.PROFILES["C"], "complex",
                expected_allergens=["Parfum", "Octocrylene"],
                max_expected_score=5
            ),
            TestCase(
                "C03", "Длинный состав крема для жирной кожи",
                "Aqua, Cyclopentasiloxane, Glycerin, Niacinamide, Zinc PCA, "
                "Salicylic Acid, Hamamelis Virginiana Water, Alcohol Denat., "
                "Menthol, Parfum, Linalool, Allantoin, Panthenol",
                self.PROFILES["B"], "complex",
                expected_allergens=["Alcohol Denat.", "Parfum"],
            ),
            TestCase(
                "C04", "Состав без пробелов и в хаотичном порядке",
                "aqua,glycerin,parfum,cetyl alcohol,retinol,"
                "linalool,tocopherol,methylparaben,dimethicone",
                self.PROFILES["A"], "complex",
                expected_allergens=["Parfum", "Linalool", "Retinol"],
                max_expected_score=5
            ),
            TestCase(
                "C05", "Крем с ореховыми маслами",
                "Aqua, Prunus Amygdalus Dulcis Oil, Macadamia Integrifolia Seed Oil, "
                "Argania Spinosa Kernel Oil, Butyrospermum Parkii Butter, "
                "Cetyl Alcohol, Glycerin, Tocopherol",
                self.PROFILES["E"], "complex",
                expected_allergens=["Prunus Amygdalus Dulcis Oil"],
                max_expected_score=5
            ),

            # === ПРОВОКАЦИОННЫЕ (provocative): 3 кейса ===
            TestCase(
                "P01", "Пустой запрос",
                "", self.PROFILES["A"], "provocative",
                expected_allergens=[], min_expected_score=0, max_expected_score=0
            ),
            TestCase(
                "P02", "Бессмысленный текст",
                "абракадабра тест проверка связи", self.PROFILES["A"], "provocative",
                expected_allergens=[], min_expected_score=0, max_expected_score=0
            ),
            TestCase(
                "P03", "Не косметический состав",
                "H2O, NaCl, C12H22O11, C6H12O6", self.PROFILES["A"], "provocative",
                expected_allergens=[], max_expected_score=3
            ),
        ]

    async def run_benchmark(
            self,
            model_name: str,
            output_file: str = "benchmark_results.json"
    ) -> List[TestResult]:
        """
        Запускает полный бенчмарк на всех тестовых кейсах.
        """
        client = YandexGPTClient()
        test_cases = self._get_test_cases()
        results: List[TestResult] = []

        logger.info(f"🚀 Запуск бенчмарка для модели: {model_name}")
        logger.info(f"📋 Всего тестовых кейсов: {len(test_cases)}")

        for idx, case in enumerate(test_cases, 1):
            logger.info(f"[{idx}/{len(test_cases)}] Тест {case.case_id}: "
                        f"{case.name} (профиль {case.profile.profile_id}, {case.category})")

            prompt = PromptBuilder.build_prompt(
                skin_type=case.profile.skin_type,
                allergens=case.profile.allergens,
                preferences=case.profile.preferences,
                ingredients=case.ingredients,
                name=case.name,
                history=None
            )

            # Засекаем время
            start_time = time.monotonic()

            # Отправляем запрос к LLM
            try:
                parsed = await client.generate_response(prompt)
            except Exception as e:
                parsed = {
                    "score": None,
                    "explanation": "",
                    "warnings": [],
                    "recommendations": [],
                    "tokens": {}
                }
                logger.error(f"❌ Ошибка запроса: {e}")

            end_time = time.monotonic()
            response_time = int((end_time - start_time) * 1000)

            # Формируем результат
            result = TestResult(
                case_id=case.case_id,
                profile_id=case.profile.profile_id,
                category=case.category,
                model=model_name,
                timestamp=start_time,
                response_time_ms=response_time,
                raw_response=None,  # замените если хотите сохранять сырой ответ
                parsed_response=parsed,
                json_valid=parsed is not None and isinstance(parsed.get("score"), int),
                schema_valid=self._check_schema(parsed),
                score=parsed.get("score"),
                explanation=parsed.get("explanation", ""),
                warnings=parsed.get("warnings", []),
                recommendations=parsed.get("recommendations", []),
                tokens=parsed.get("tokens", {}),
                error=None if parsed and isinstance(parsed.get("score"), int) else "Invalid response"
            )

            results.append(result)

            # Краткий вывод
            logger.info(f"  ⏱ {response_time}ms | 📊 score={result.score} | "
                        f"JSON: {'✅' if result.json_valid else '❌'} | "
                        f"Schema: {'✅' if result.schema_valid else '❌'}")

            # Небольшая задержка между запросами, чтобы не упереться в rate limit
            await asyncio.sleep(0.5)

        # Сохраняем результаты
        self._save_results(results, model_name, output_file)

        # Выводим сводку
        self._print_summary(results, model_name)

        return results

    def _check_schema(self, parsed: Optional[Dict]) -> bool:
        if not parsed:
            return False
        if "score" not in parsed:
            return False
        if not isinstance(parsed.get("warnings"), list):
            return False
        if not isinstance(parsed.get("recommendations"), list):
            return False
        return True

    def _save_results(
            self,
            results: List[TestResult],
            model_name: str,
            output_file: str
    ):
        data = {
            "model": model_name,
            "total_cases": len(results),
            "results": [asdict(r) for r in results]
        }

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f" Результаты сохранены в {output_path}")

    def _print_summary(self, results: List[TestResult], model_name: str):
        total = len(results)
        json_valid = sum(1 for r in results if r.json_valid)
        schema_valid = sum(1 for r in results if r.schema_valid)
        scores = [r.score for r in results if r.score is not None]
        times = [r.response_time_ms for r in results]
        total_tokens = sum(r.tokens.get("total_tokens", 0) for r in results)

        by_category = {}
        for cat in ["simple", "medium", "complex", "provocative"]:
            cat_results = [r for r in results if r.category == cat]
            if cat_results:
                cat_scores = [r.score for r in cat_results if r.score is not None]
                by_category[cat] = {
                    "count": len(cat_results),
                    "avg_score": sum(cat_scores) / len(cat_scores) if cat_scores else 0,
                    "json_valid": sum(1 for r in cat_results if r.json_valid),
                    "avg_time_ms": sum(r.response_time_ms for r in cat_results) / len(cat_results)
                }

        print(f"\n{'=' * 60}")
        print(f" СВОДКА БЕНЧМАРКА: {model_name}")
        print(f"{'=' * 60}")
        print(f"Всего кейсов:          {total}")
        print(f"JSON Valid:            {json_valid}/{total} ({json_valid / total * 100:.1f}%)")
        print(f"Schema Valid:          {schema_valid}/{total} ({schema_valid / total * 100:.1f}%)")
        if scores:
            print(f"Средняя оценка (score): {sum(scores) / len(scores):.1f}")
            print(f"Мин./Макс. оценка:      {min(scores)}/{max(scores)}")
        if times:
            print(f"Среднее время ответа:   {sum(times) / len(times):.0f}ms")
            print(f"Мин./Макс. время:       {min(times)}/{max(times)}ms")
        print(f"Всего токенов:          {total_tokens}")
        print(f"\nПо категориям:")
        for cat, stats in by_category.items():
            print(f"  {cat:15s}: avg_score={stats['avg_score']:.1f}, "
                  f"json_valid={stats['json_valid']}/{stats['count']}, "
                  f"avg_time={stats['avg_time_ms']:.0f}ms")
        print(f"{'=' * 60}\n")


class AllergenDetectionTester:
    """
    Отдельный тест для замера точности детекции аллергенов.
    Метрика: Allergen Detection Rate
    """

    ALLERGEN_TEST_CASES = [
        {
            "name": "Крем с явной отдушкой",
            "ingredients": "Aqua, Parfum, Linalool, Glycerin, Tocopherol",
            "profile": TestProfile("A", "сухая", ["отдушка", "лаванда"], []),
            "expected_allergens": ["Parfum", "Linalool"],
            "expected_warning_keywords": ["отдушк", "аллерген", "Parfum"]
        },
        {
            "name": "Тоник с агрессивным спиртом",
            "ingredients": "Aqua, Alcohol Denat., Hamamelis Extract",
            "profile": TestProfile("B", "жирная", ["спирт", "цитрусы"], []),
            "expected_allergens": ["Alcohol Denat."],
            "expected_warning_keywords": ["спирт", "Alcohol", "сушит", "раздраж"]
        },
        {
            "name": "Крем с парабенами для чувствительной",
            "ingredients": "Aqua, Methylparaben, Propylparaben, Glycerin",
            "profile": TestProfile("C", "чувствительная", ["парабены", "отдушка"], []),
            "expected_allergens": ["Methylparaben", "Propylparaben"],
            "expected_warning_keywords": ["парабен", "Methylparaben", "Propylparaben"]
        },
        {
            "name": "Питательный крем с орехами (аллергия на орехи)",
            "ingredients": "Aqua, Prunus Amygdalus Dulcis Oil, Butyrospermum Parkii",
            "profile": TestProfile("E", "нормальная", ["орехи"], []),
            "expected_allergens": ["Prunus Amygdalus Dulcis Oil"],
            "expected_warning_keywords": ["орех", "аллерг", "Prunus"]
        },
        {
            "name": "Безопасный состав (ложное срабатывание недопустимо)",
            "ingredients": "Aqua, Glycerin, Tocopherol, Aloe Vera",
            "profile": TestProfile("C", "чувствительная", ["парабены", "отдушка"], []),
            "expected_allergens": [],
            "expected_warning_keywords": None  # Предупреждений об аллергенах быть НЕ должно
        },
        {
            "name": "Крем с лавандой (аллергия на лаванду)",
            "ingredients": "Aqua, Lavandula Angustifolia Oil, Glycerin",
            "profile": TestProfile("A", "сухая", ["отдушка", "лаванда"], []),
            "expected_allergens": ["Lavandula Angustifolia Oil"],
            "expected_warning_keywords": ["лаванд", "аллерг", "Lavandula"]
        },
    ]

    async def run(self, model_name: str) -> Dict[str, Any]:
        """
        Запускает тест на детекцию аллергенов.
        """
        client = YandexGPTClient()

        total_allergens = 0
        detected = 0
        missed = 0
        false_positive = 0
        details = []

        logger.info(f"\n{'=' * 60}")
        logger.info(f" ТЕСТ ДЕТЕКЦИИ АЛЛЕРГЕНОВ: {model_name}")
        logger.info(f"{'=' * 60}")

        for case in self.ALLERGEN_TEST_CASES:
            prompt = PromptBuilder.build_prompt(
                skin_type=case["profile"].skin_type,
                allergens=case["profile"].allergens,
                preferences=case["profile"].preferences,
                ingredients=case["ingredients"],
                name=case["name"],
                history=None
            )

            parsed = await client.generate_response(prompt)
            warnings = parsed.get("warnings", [])
            warnings_text = " ".join(warnings).lower()

            case_detail = {
                "name": case["name"],
                "expected_allergens": case["expected_allergens"],
                "warnings": warnings,
                "score": parsed.get("score"),
                "explanation": parsed.get("explanation", "")
            }

            for allergen in case["expected_allergens"]:
                total_allergens += 1
                allergen_lower = allergen.lower()
                if allergen_lower in warnings_text:
                    detected += 1
                    case_detail[f"detected_{allergen}"] = True
                else:
                    missed += 1
                    case_detail[f"detected_{allergen}"] = False
                    logger.warning(f"❌ ПРОПУЩЕН АЛЛЕРГЕН: {allergen} в кейсе '{case['name']}'")

            if not case["expected_allergens"] and warnings:
                allergy_related_warnings = [
                    w for w in warnings
                    if any(kw in w.lower() for kw in ["аллерг", "allerg", "реакц", "раздраж"])
                ]
                if allergy_related_warnings:
                    false_positive += len(allergy_related_warnings)
                    case_detail["false_positive"] = True
                    logger.warning(f"⚠ ЛОЖНОЕ СРАБАТЫВАНИЕ в кейсе '{case['name']}': "
                                   f"{allergy_related_warnings}")
                else:
                    case_detail["false_positive"] = False

            details.append(case_detail)

        detection_rate = (detected / total_allergens * 100) if total_allergens > 0 else 100.0
        missed_rate = (missed / total_allergens * 100) if total_allergens > 0 else 0.0

        results = {
            "model": model_name,
            "total_allergens_to_detect": total_allergens,
            "detected": detected,
            "missed": missed,
            "false_positive_warnings": false_positive,
            "detection_rate": round(detection_rate, 1),
            "missed_rate": round(missed_rate, 1),
            "details": details
        }

        print(f"\n РЕЗУЛЬТАТЫ ДЕТЕКЦИИ АЛЛЕРГЕНОВ:")
        print(f"   Всего аллергенов для обнаружения: {total_allergens}")
        print(f"   Обнаружено:    {detected} ({detection_rate:.1f}%)")
        print(f"   Пропущено:     {missed} ({missed_rate:.1f}%)")
        print(f"   Ложные срабатывания: {false_positive}")
        print(f"{'=' * 60}\n")

        return results


class PersonalizationTester:
    """
    Тест проверки персонализации.
    Один состав → разные профили → замер разброса оценок (Δscore).
    Метрика: средний разброс оценок между профилями
    """

    PERSONALIZATION_TEST_COMPOSITIONS = [
        {
            "name": "Увлажняющий крем с отдушкой",
            "ingredients": "Aqua, Glycerin, Cetyl Alcohol, Parfum, Linalool, Tocopherol"
        },
        {
            "name": "Матирующий гель с кислотами",
            "ingredients": "Aqua, Salicylic Acid, Niacinamide, Alcohol Denat., Zinc PCA"
        },
        {
            "name": "Питательный крем с маслами",
            "ingredients": "Aqua, Cocos Nucifera Oil, Butyrospermum Parkii, Lanolin, Parfum"
        },
    ]

    TEST_PROFILES = [
        TestProfile("A", "сухая", ["отдушка", "лаванда"], ["натуральные компоненты"]),
        TestProfile("B", "жирная", ["спирт", "цитрусы"], ["матирующий эффект"]),
        TestProfile("C", "чувствительная", ["парабены", "отдушка"], ["гипоаллергенно"]),
        TestProfile("D", "комбинированная", [], ["без спирта"]),
        TestProfile("E", "нормальная", ["орехи"], ["веганская косметика"]),
    ]

    async def run(self, model_name: str) -> Dict[str, Any]:
        client = YandexGPTClient()
        all_scores: Dict[str, List[int]] = {}
        details = []

        logger.info(f"\n{'=' * 60}")
        logger.info(f"ТЕСТ ПЕРСОНАЛИЗАЦИИ: {model_name}")
        logger.info(f"{'=' * 60}")

        for comp in self.PERSONALIZATION_TEST_COMPOSITIONS:
            comp_scores = {}
            logger.info(f"\nСостав: {comp['name']}")

            for profile in self.TEST_PROFILES:
                prompt = PromptBuilder.build_prompt(
                    skin_type=profile.skin_type,
                    allergens=profile.allergens,
                    preferences=profile.preferences,
                    ingredients=comp["ingredients"],
                    name=comp["name"],
                    history=None
                )

                parsed = await client.generate_response(prompt)
                score = parsed.get("score", 5)
                comp_scores[profile.profile_id] = score

                logger.info(f"  Профиль {profile.profile_id} "
                            f"({profile.skin_type}, аллергия на {profile.allergens}): "
                            f"score={score}")

            scores_list = list(comp_scores.values())
            delta = max(scores_list) - min(scores_list) if scores_list else 0
            all_scores[comp["name"]] = scores_list

            details.append({
                "composition": comp["name"],
                "scores": comp_scores,
                "delta_score": delta,
                "min_score": min(scores_list),
                "max_score": max(scores_list),
                "profiles_count": len(scores_list)
            })

            logger.info(f" Разброс (Δscore): {delta} баллов")

        deltas = [d["delta_score"] for d in details]
        avg_delta = sum(deltas) / len(deltas) if deltas else 0

        results = {
            "model": model_name,
            "compositions_tested": len(self.PERSONALIZATION_TEST_COMPOSITIONS),
            "profiles_per_composition": len(self.TEST_PROFILES),
            "delta_scores": deltas,
            "avg_delta_score": round(avg_delta, 1),
            "max_delta_score": max(deltas) if deltas else 0,
            "details": details
        }

        print(f"\n РЕЗУЛЬТАТЫ ПЕРСОНАЛИЗАЦИИ:")
        print(f"   Средний разброс оценок (Δscore): {avg_delta:.1f} балла")
        print(f"   Максимальный разброс:             {max(deltas) if deltas else 0} балла")
        for d in details:
            print(f"   {d['composition'][:50]:50s}: Δ={d['delta_score']}")
        print(f"{'=' * 60}\n")

        return results



async def main():
    MODEL_NAME = "DeepSeek3.2"

    # 1. Основной бенчмарк (все 20 кейсов)
    benchmark = LLMBenchmark()
    benchmark_results = await benchmark.run_benchmark(
        model_name=MODEL_NAME,
        output_file=f"results/benchmark_{MODEL_NAME.replace(' ', '_').lower()}.json"
    )

    # 2. Тест детекции аллергенов
    allergen_tester = AllergenDetectionTester()
    allergen_results = await allergen_tester.run(MODEL_NAME)

    with open(f"results/allergen_test_{MODEL_NAME.replace(' ', '_').lower()}.json", "w", encoding="utf-8") as f:
        json.dump(allergen_results, f, ensure_ascii=False, indent=2)

    # 3. Тест персонализации
    personalization_tester = PersonalizationTester()
    personalization_results = await personalization_tester.run(MODEL_NAME)

    with open(f"results/personalization_{MODEL_NAME.replace(' ', '_').lower()}.json", "w", encoding="utf-8") as f:
        json.dump(personalization_results, f, ensure_ascii=False, indent=2)

    print("\n Все тесты завершены")


if __name__ == "__main__":
    asyncio.run(main())