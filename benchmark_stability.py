import asyncio
import json
import time
import statistics
from dataclasses import dataclass, field, asdict
from typing import Optional

from llm.yandex_client import YandexGPTClient
from llm.prompt_builder import PromptBuilder
from llm.rag_module import IngredientRAG


REPEATS = 5
STABILITY_THRESHOLD = 1
DELAY_BETWEEN_REQUESTS = 1.0


TEST_CASES = [
    {
        "id": "stab_001",
        "description": "Простой безопасный состав — ожидаем высокий стабильный score",
        "profile": {"skin_type": "нормальная", "allergens": []},
        "ingredients": "Aqua, Glycerin, Sodium Hyaluronate, Panthenol, Allantoin, Phenoxyethanol",
        "expected_range": "8-10",
    },
    {
        "id": "stab_002",
        "description": "Состав с аллергеном пользователя — score должен быть стабильно низким",
        "profile": {"skin_type": "чувствительная", "allergens": ["отдушка"]},
        "ingredients": "Aqua, Glycerin, Cetyl Alcohol, Parfum, Linalool, Panthenol, Phenoxyethanol",
        "expected_range": "1-4",
    },
    {
        "id": "stab_003",
        "description": "Неоднозначный состав — ожидаем умеренный score",
        "profile": {"skin_type": "жирная", "allergens": []},
        "ingredients": (
            "Aqua, Glycerin, Cocos Nucifera Oil, Niacinamide, Cetyl Alcohol, "
            "Stearic Acid, Parfum, Phenoxyethanol, Linalool"
        ),
        "expected_range": "4-7",
    },
    {
        "id": "stab_004",
        "description": "Длинный реальный состав — проверка стабильности при большом контексте",
        "profile": {"skin_type": "сухая", "allergens": []},
        "ingredients": (
            "Aqua, Glycerin, Cetearyl Alcohol, Ceteareth-20, Dimethicone, "
            "Glyceryl Stearate, PEG-100 Stearate, Sodium Hyaluronate, "
            "Ceramide NP, Ceramide AP, Ceramide EOP, Cholesterol, "
            "Phytosphingosine, Sodium Lauroyl Lactylate, Carbomer, "
            "Xanthan Gum, Sodium Hydroxide, Disodium EDTA, "
            "Phenoxyethanol, Ethylhexylglycerin"
        ),
        "expected_range": "7-10",
    },
    {
        "id": "stab_005",
        "description": "Проблемный состав для сухой кожи — стабильно низкий score",
        "profile": {"skin_type": "сухая", "allergens": []},
        "ingredients": (
            "Aqua, Alcohol Denat., Glycerin, Salicylic Acid, "
            "Niacinamide, Zinc PCA, Witch Hazel Extract, Menthol, Parfum"
        ),
        "expected_range": "2-5",
    },
    {
        "id": "stab_006",
        "description": "Состав с ретинолом — проверка что модель стабильно его обрабатывает",
        "profile": {"skin_type": "нормальная", "allergens": []},
        "ingredients": (
            "Aqua, Glycerin, Retinyl Palmitate, Niacinamide, "
            "Squalane, Ceramide NP, Tocopherol, Phenoxyethanol"
        ),
        "expected_range": "6-9",
    },
]


@dataclass
class SingleRun:
    run_number: int
    score: Optional[int]
    time_ms: int
    success: bool
    error: Optional[str] = None


@dataclass
class CaseResult:
    id: str
    description: str
    profile: dict
    ingredients_length: int
    expected_range: str
    runs: list = field(default_factory=list)

    score_mean: float = 0.0
    score_std: float = 0.0
    score_min: int = 0
    score_max: int = 0
    score_range: int = 0
    cv: float = 0.0           # коэффициент вариации %
    is_stable: bool = False
    successful_runs: int = 0
    avg_time_ms: float = 0.0


@dataclass
class SummaryMetrics:
    total_cases: int = 0
    stable_cases: int = 0
    stability_rate: float = 0.0      # доля стабильных кейсов
    mean_range: float = 0.0          # средний разброс score
    mean_std: float = 0.0            # среднее стандартное отклонение
    mean_cv: float = 0.0             # средний коэффициент вариации %
    mean_response_time_ms: float = 0.0
    total_api_calls: int = 0
    failed_calls: int = 0

class StabilityBenchmark:

    def __init__(self):
        self.client = YandexGPTClient()
        self.rag = IngredientRAG()

    def _build_prompt(self, ingredients: str, profile: dict) -> str:
        return PromptBuilder.build_prompt(
            skin_type=profile.get("skin_type", ""),
            allergens=profile.get("allergens", []),
            preferences=[],
            name="",
            ingredients=ingredients,
            history=[],
            rag=self.rag,
        )

    async def _single_request(self, prompt: str, run_num: int) -> SingleRun:
        t0 = time.time()
        try:
            response = await self.client.generate_response(prompt)
            elapsed = int((time.time() - t0) * 1000)

            if response and response.get("score") is not None:
                score = int(response["score"])
                return SingleRun(
                    run_number=run_num,
                    score=score,
                    time_ms=elapsed,
                    success=True,
                )
            else:
                return SingleRun(
                    run_number=run_num,
                    score=None,
                    time_ms=elapsed,
                    success=False,
                    error="no_score_in_response",
                )
        except Exception as e:
            elapsed = int((time.time() - t0) * 1000)
            return SingleRun(
                run_number=run_num,
                score=None,
                time_ms=elapsed,
                success=False,
                error=str(e)[:100],
            )

    async def run_case(self, case: dict) -> CaseResult:
        result = CaseResult(
            id=case["id"],
            description=case["description"],
            profile=case["profile"],
            ingredients_length=len(case["ingredients"]),
            expected_range=case["expected_range"],
        )

        prompt = self._build_prompt(case["ingredients"], case["profile"])
        scores = []
        times = []

        print(f"\n  [{case['id']}] {case['description'][:60]}")
        print(f"  Профиль: {case['profile']['skin_type']}, "
              f"аллергены: {case['profile']['allergens'] or 'нет'}")

        for i in range(1, REPEATS + 1):
            run = await self._single_request(prompt, i)
            result.runs.append(run)

            if run.success:
                scores.append(run.score)
                times.append(run.time_ms)
                print(f"    Запрос {i}/{REPEATS}: score={run.score}, {run.time_ms} мс")
            else:
                print(f"    Запрос {i}/{REPEATS}: ОШИБКА — {run.error}")

            if i < REPEATS:
                await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

        result.successful_runs = len(scores)

        if len(scores) >= 2:
            result.score_mean = round(statistics.mean(scores), 2)
            result.score_std = round(statistics.stdev(scores), 2)
            result.score_min = min(scores)
            result.score_max = max(scores)
            result.score_range = result.score_max - result.score_min
            result.cv = round(
                (result.score_std / result.score_mean * 100)
                if result.score_mean > 0 else 0.0,
                1
            )
            result.is_stable = result.score_range <= STABILITY_THRESHOLD
            result.avg_time_ms = round(statistics.mean(times), 1)

        elif len(scores) == 1:
            result.score_mean = scores[0]
            result.score_std = 0.0
            result.score_min = scores[0]
            result.score_max = scores[0]
            result.score_range = 0
            result.cv = 0.0
            result.is_stable = True
            result.avg_time_ms = times[0]

        stability_label = "СТАБИЛЬНО" if result.is_stable else "НЕСТАБИЛЬНО"
        print(
            f"  Итог: mean={result.score_mean}, std={result.score_std}, "
            f"range={result.score_range}, CV={result.cv}% → {stability_label}"
        )

        return result

    async def run(self) -> dict:
        print(f"\n{'='*60}")
        print(f"Тест стабильности score LLM")
        print(f"Модель: DeepSeek | Повторов: {REPEATS} | Порог: ±{STABILITY_THRESHOLD}")
        print(f"{'='*60}")

        case_results = []
        for case in TEST_CASES:
            result = await self.run_case(case)
            case_results.append(result)

        # Итоговые метрики
        summary = self._compute_summary(case_results)
        self._print_summary(summary, case_results)

        output = {
            "config": {
                "repeats": REPEATS,
                "stability_threshold": STABILITY_THRESHOLD,
                "delay_between_requests_s": DELAY_BETWEEN_REQUESTS,
            },
            "summary": asdict(summary),
            "cases": [asdict(r) for r in case_results],
        }

        with open("stability_benchmark_results.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\nРезультаты сохранены в stability_benchmark_results.json")
        return output

    def _compute_summary(self, results: list[CaseResult]) -> SummaryMetrics:
        s = SummaryMetrics()
        s.total_cases = len(results)
        s.stable_cases = sum(1 for r in results if r.is_stable)
        s.stability_rate = round(s.stable_cases / s.total_cases, 4) if s.total_cases else 0.0

        ranges = [r.score_range for r in results if r.successful_runs >= 2]
        stds   = [r.score_std   for r in results if r.successful_runs >= 2]
        cvs    = [r.cv          for r in results if r.successful_runs >= 2]
        times  = [r.avg_time_ms for r in results if r.successful_runs > 0]

        s.mean_range = round(statistics.mean(ranges), 2) if ranges else 0.0
        s.mean_std   = round(statistics.mean(stds), 2)   if stds   else 0.0
        s.mean_cv    = round(statistics.mean(cvs), 1)    if cvs    else 0.0
        s.mean_response_time_ms = round(statistics.mean(times), 1) if times else 0.0

        s.total_api_calls = sum(r.successful_runs for r in results) + \
                            sum(REPEATS - r.successful_runs for r in results)
        s.failed_calls    = sum(REPEATS - r.successful_runs for r in results)

        return s

    def _print_summary(self, summary: SummaryMetrics, results: list[CaseResult]) -> None:
        print(f"\n{'='*60}")
        print("ИТОГОВЫЕ МЕТРИКИ СТАБИЛЬНОСТИ")
        print(f"{'='*60}")
        print(f"Всего кейсов:          {summary.total_cases}")
        print(f"Стабильных:            {summary.stable_cases} / {summary.total_cases}")
        print(f"Stability Rate:        {summary.stability_rate:.1%}")
        print(f"Mean Range (max-min):  {summary.mean_range:.2f} баллов")
        print(f"Mean Std Dev:          {summary.mean_std:.2f}")
        print(f"Mean CV:               {summary.mean_cv:.1f}%")
        print(f"Mean Response Time:    {summary.mean_response_time_ms:.0f} мс")
        print(f"Всего API-запросов:    {summary.total_api_calls}")
        print(f"Ошибок:                {summary.failed_calls}")
        print(f"{'='*60}")

        print("\nДетализация по кейсам:")
        print(f"{'ID':<12} {'Mean':>6} {'Std':>5} {'Range':>6} {'CV%':>6} {'Статус'}")
        print("-" * 55)
        for r in results:
            status = "STABLE" if r.is_stable else "UNSTABLE"
            if r.successful_runs == 0:
                status = "FAILED"
            print(
                f"{r.id:<12} {r.score_mean:>6.1f} {r.score_std:>5.2f} "
                f"{r.score_range:>6} {r.cv:>5.1f}% {status}"
            )

        print(f"\nИнтерпретация:")
        if summary.stability_rate >= 0.8:
            print(f"  Stability Rate {summary.stability_rate:.1%} >= 80%")
        else:
            print(f"  Stability Rate {summary.stability_rate:.1%} < 80%")

        if summary.mean_range <= 1.5:
            print(f"  Mean Range {summary.mean_range:.2f} <= 1.5 — разброс в пределах нормы")
        else:
            print(f"  Mean Range {summary.mean_range:.2f} > 1.5 — высокий разброс")


if __name__ == "__main__":
    benchmark = StabilityBenchmark()
    asyncio.run(benchmark.run())
