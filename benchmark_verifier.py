
import asyncio
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional

from llm.verifier import ResponseVerifier


TEST_CASES = [
    {
        "id": "hall_001",
        "description": "Ретинол упомянут в warnings, но отсутствует в составе",
        "ingredients": "Aqua, Glycerin, Niacinamide, Zinc PCA, Sodium Hyaluronate, Panthenol",
        "profile": {"skin_type": "жирная", "allergens": []},
        "response_with_hallucination": {
            "score": 7,
            "explanation": "Хороший состав для жирной кожи с ниацинамидом и цинком.",
            "warnings": ["Ретинол может вызвать раздражение при первом применении"],
            "recommendations": ["Используйте SPF при применении ретинола"]
        },
        "response_clean": {
            "score": 8,
            "explanation": "Хороший состав для жирной кожи с ниацинамидом и цинком.",
            "warnings": [],
            "recommendations": ["Подходит для ежедневного использования"]
        },
        "expected_hallucination": "ретинол"
    },
    {
        "id": "hall_002",
        "description": "Парабен упомянут как аллерген, но его нет в составе",
        "ingredients": "Aqua, Cetearyl Alcohol, Glycerin, Shea Butter, Tocopherol, Phenoxyethanol",
        "profile": {"skin_type": "чувствительная", "allergens": ["парабены"]},
        "response_with_hallucination": {
            "score": 3,
            "explanation": "Состав содержит консерванты.",
            "warnings": ["Methylparaben — аллерген пользователя, присутствует в составе"],
            "recommendations": ["Избегайте средств с парабенами"]
        },
        "response_clean": {
            "score": 7,
            "explanation": "Мягкий состав без парабенов, подходит для чувствительной кожи.",
            "warnings": ["Phenoxyethanol — консервант, может раздражать очень чувствительную кожу"],
            "recommendations": ["Проведите патч-тест перед первым применением"]
        },
        "expected_hallucination": "methylparaben"
    },
    {
        "id": "hall_003",
        "description": "Противоречие score и warnings (score высокий, warnings критические)",
        "ingredients": "Aqua, Alcohol Denat, Fragrance, Citric Acid, Sodium Lauryl Sulfate",
        "profile": {"skin_type": "сухая", "allergens": ["отдушка"]},
        "response_with_hallucination": {
            "score": 8,
            "explanation": "Освежающий тоник с кислотами.",
            "warnings": ["Fragrance — аллерген пользователя", "Alcohol Denat сушит кожу"],
            "recommendations": []
        },
        "response_clean": {
            "score": 2,
            "explanation": "Агрессивный состав для сухой кожи: спирт сушит, отдушка — аллерген.",
            "warnings": ["Fragrance — аллерген пользователя", "Alcohol Denat сушит кожу"],
            "recommendations": ["Выберите средство без спирта и отдушек"]
        },
        "expected_hallucination": None  # нет галлюцинации, есть противоречие score
    },
    {
        "id": "hall_004",
        "description": "Гиалуроновая кислота упомянута как риск, но её нет в составе",
        "ingredients": "Aqua, Glycerin, Ceramide NP, Cholesterol, Fatty Acids",
        "profile": {"skin_type": "сухая", "allergens": []},
        "response_with_hallucination": {
            "score": 6,
            "explanation": "Состав с церамидами. Гиалуроновая кислота может привлекать влагу.",
            "warnings": ["Гиалуроновая кислота в высокой концентрации может стянуть кожу в сухом климате"],
            "recommendations": ["Наносите поверх увлажняющей сыворотки с гиалуроновой кислотой"]
        },
        "response_clean": {
            "score": 9,
            "explanation": "Отличный состав с церамидами и холестерином для восстановления барьера.",
            "warnings": [],
            "recommendations": ["Подходит для ежедневного применения утром и вечером"]
        },
        "expected_hallucination": "гиалуроновая кислота"
    },
    {
        "id": "hall_005",
        "description": "Чистый ответ без галлюцинаций — проверка False Positive Rate",
        "ingredients": "Aqua, Salicylic Acid, Niacinamide, Zinc PCA, Glycerin",
        "profile": {"skin_type": "жирная", "allergens": []},
        "response_with_hallucination": None,  # нет версии с галлюцинацией
        "response_clean": {
            "score": 8,
            "explanation": "Эффективный состав для жирной кожи. Салициловая кислота отшелушивает, ниацинамид регулирует выработку себума.",
            "warnings": ["Salicylic Acid — не рекомендуется при беременности"],
            "recommendations": ["Используйте вечером, утром наносите SPF"]
        },
        "expected_hallucination": None
    },
]


@dataclass
class BenchmarkMetrics:
    total_cases: int = 0
    hallucination_detected: int = 0   # верификатор нашёл галлюцинацию когда она была
    hallucination_missed: int = 0     # верификатор пропустил галлюцинацию
    false_positives: int = 0          # верификатор нашёл галлюцинацию там где её нет
    true_negatives: int = 0           # верификатор корректно пропустил чистый ответ
    contradiction_detected: int = 0   # верификатор нашёл противоречие score/warnings
    score_corrections: int = 0        # сколько раз был скорректирован score
    verifier_failures: int = 0        # верификатор не смог распарсить свой ответ

    total_verifier_time_ms: int = 0
    total_verifier_tokens: int = 0

    @property
    def hallucination_detection_rate(self) -> float:
        total_positive = self.hallucination_detected + self.hallucination_missed
        return self.hallucination_detected / total_positive if total_positive else 0.0

    @property
    def false_positive_rate(self) -> float:
        total_negative = self.false_positives + self.true_negatives
        return self.false_positives / total_negative if total_negative else 0.0

    @property
    def avg_verifier_time_ms(self) -> float:
        return self.total_verifier_time_ms / self.total_cases if self.total_cases else 0.0

    @property
    def avg_verifier_tokens(self) -> float:
        return self.total_verifier_tokens / self.total_cases if self.total_cases else 0.0


async def run_benchmark():
    verifier = ResponseVerifier()
    metrics = BenchmarkMetrics()
    detailed_results = []

    print(f"\n{'='*60}")
    print("Бенчмарк верификатора галлюцинаций")
    print(f"{'='*60}\n")

    for case in TEST_CASES:
        case_id = case["id"]
        description = case["description"]
        ingredients = case["ingredients"]
        profile = case["profile"]
        expected_hallucination = case["expected_hallucination"]

        print(f"[{case_id}] {description}")

        case_result = {
            "id": case_id,
            "description": description,
            "runs": []
        }

        if case["response_with_hallucination"]:
            metrics.total_cases += 1
            t0 = time.time()

            verification = await verifier.verify(
                ingredients=ingredients,
                llm_response=case["response_with_hallucination"],
                skin_type=profile["skin_type"],
                allergens=profile["allergens"],
            )

            elapsed_ms = int((time.time() - t0) * 1000)
            metrics.total_verifier_time_ms += elapsed_ms
            metrics.total_verifier_tokens += verification.verifier_tokens.get("total_tokens", 0)

            if verification.verifier_failed:
                metrics.verifier_failures += 1
                status = "VERIFIER_FAILED"
            elif expected_hallucination and not verification.verified:
                found_ingredients = {
                    h["ingredient"].lower() for h in verification.hallucinations
                }
                if any(expected_hallucination.lower() in fi for fi in found_ingredients):
                    metrics.hallucination_detected += 1
                    status = "✅ DETECTED"
                else:
                    metrics.hallucination_missed += 1
                    status = "❌ MISSED"
            elif expected_hallucination is None and not verification.verified:
                # Ожидали только противоречие, не галлюцинацию
                if verification.contradictions:
                    metrics.contradiction_detected += 1
                    status = "✅ CONTRADICTION_DETECTED"
                else:
                    status = "⚠️ UNEXPECTED_HALLUCINATION_FOUND"
            else:
                metrics.hallucination_missed += 1
                status = "❌ MISSED (verified=True but should not)"

            corrected = verifier.apply_corrections(
                case["response_with_hallucination"].copy(), verification
            )
            if corrected.get("score") != case["response_with_hallucination"].get("score"):
                metrics.score_corrections += 1

            print(f"  С галлюцинацией:  {status} | {elapsed_ms}ms | "
                  f"tokens={verification.verifier_tokens.get('total_tokens', 0)}")

            case_result["runs"].append({
                "variant": "with_hallucination",
                "status": status,
                "hallucinations_found": verification.hallucinations,
                "contradictions_found": verification.contradictions,
                "score_before": case["response_with_hallucination"].get("score"),
                "score_after": corrected.get("score"),
                "time_ms": elapsed_ms,
            })

        if case["response_clean"]:
            metrics.total_cases += 1
            t0 = time.time()

            verification = await verifier.verify(
                ingredients=ingredients,
                llm_response=case["response_clean"],
                skin_type=profile["skin_type"],
                allergens=profile["allergens"],
            )

            elapsed_ms = int((time.time() - t0) * 1000)
            metrics.total_verifier_time_ms += elapsed_ms
            metrics.total_verifier_tokens += verification.verifier_tokens.get("total_tokens", 0)

            if verification.verifier_failed:
                metrics.verifier_failures += 1
                status = "VERIFIER_FAILED"
            elif verification.verified:
                metrics.true_negatives += 1
                status = "✅ TRUE_NEGATIVE"
            else:
                metrics.false_positives += 1
                status = f"❌ FALSE_POSITIVE (found: {[h['ingredient'] for h in verification.hallucinations]})"

            print(f"  Чистый ответ:     {status} | {elapsed_ms}ms | "
                  f"tokens={verification.verifier_tokens.get('total_tokens', 0)}")

            case_result["runs"].append({
                "variant": "clean",
                "status": status,
                "hallucinations_found": verification.hallucinations,
                "time_ms": elapsed_ms,
            })

        detailed_results.append(case_result)
        print()

    print(f"{'='*60}")
    print("ИТОГОВЫЕ МЕТРИКИ ВЕРИФИКАТОРА")
    print(f"{'='*60}")
    print(f"Всего прогонов:             {metrics.total_cases}")
    print(f"Hallucination Detection Rate: {metrics.hallucination_detection_rate:.1%}")
    print(f"False Positive Rate:          {metrics.false_positive_rate:.1%}")
    print(f"Противоречий обнаружено:      {metrics.contradiction_detected}")
    print(f"Score скорректирован:         {metrics.score_corrections}")
    print(f"Ошибки верификатора:          {metrics.verifier_failures}")
    print(f"Среднее время верификатора:   {metrics.avg_verifier_time_ms:.0f} мс")
    print(f"Среднее токенов верификатора: {metrics.avg_verifier_tokens:.0f}")
    print(f"{'='*60}\n")

    output = {
        "summary": {
            "total_cases": metrics.total_cases,
            "hallucination_detection_rate": round(metrics.hallucination_detection_rate, 4),
            "false_positive_rate": round(metrics.false_positive_rate, 4),
            "contradiction_detected": metrics.contradiction_detected,
            "score_corrections": metrics.score_corrections,
            "verifier_failures": metrics.verifier_failures,
            "avg_verifier_time_ms": round(metrics.avg_verifier_time_ms, 1),
            "avg_verifier_tokens": round(metrics.avg_verifier_tokens, 1),
        },
        "detailed": detailed_results,
    }

    with open("verifier_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("Результаты сохранены в verifier_benchmark_results.json")
    return output


if __name__ == "__main__":
    asyncio.run(run_benchmark())
