"""
Сравнительная визуализация результатов тестирования 4 LLM-моделей.
Модели: YandexGPT 5 Lite, YandexGPT 5.1 PRO, DeepSeek 3.2, Qwen3 235B
Запуск: python compare_models.py
"""
import json
import numpy as np
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11

MODELS = ["YandexGPT 5 Lite", "YandexGPT 5.1 PRO", "DeepSeek 3.2", "Qwen3 235B"]
MODEL_SHORT = ["YandexGPT\n5 Lite", "YandexGPT\n5.1 PRO", "DeepSeek\n3.2", "Qwen3\n235B"]
COLORS_MODEL = ['#FF9800', '#FF5722', '#2196F3', '#4CAF50']  # оранж, красно-оранж, синий, зеленый

OUTPUT_DIR = Path("results/charts_compare")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_json(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)


# ==================== 1. СРАВНЕНИЕ ДЕТЕКЦИИ АЛЛЕРГЕНОВ ====================

def plot_allergen_comparison():
    files = [
        "results/allergen_test_yandexgpt_5_lite.json",
        "results/allergen_test_yandexgpt_5.1_pro.json",
        "results/allergen_test_deepseek_3.2.json",
        "results/allergen_test_qwen3_235b.json",
    ]

    detection_rates = []
    missed_rates = []
    fp_counts = []
    model_names = []

    for f in files:
        d = load_json(f)
        model_names.append(d['model'])
        detection_rates.append(d['detection_rate'])
        missed_rates.append(d['missed_rate'])
        fp_counts.append(d['false_positive_warnings'])

    fig, axes = plt.subplots(1, 2, figsize=(16, 5.5))
    fig.suptitle('Сравнение детекции аллергенов по моделям', fontsize=15, fontweight='bold', y=1.02)

    # Левая: Detection Rate
    ax1 = axes[0]
    x = np.arange(len(model_names))
    width = 0.55

    bars = ax1.bar(x, detection_rates, width, color=COLORS_MODEL, edgecolor='white', alpha=0.9)

    for bar, rate in zip(bars, detection_rates):
        color = 'green' if rate >= 85 else 'orange' if rate >= 50 else 'red'
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.8,
                 f'{rate:.1f}%', ha='center', fontsize=15, fontweight='bold', color=color)

    ax1.set_xticks(x)
    ax1.set_xticklabels(model_names, fontsize=9, rotation=15)
    ax1.set_ylabel('Detection Rate (%)', fontsize=12)
    ax1.set_title('Полнота обнаружения аллергенов (Allergen Detection Rate)', fontsize=12, pad=12)
    ax1.set_ylim(0, 120)
    ax1.grid(axis='y', alpha=0.3)
    ax1.axhline(y=100, color='green', linestyle='--', alpha=0.4, linewidth=1.5, label='100%')
    ax1.legend(fontsize=9)

    # Правая: Missed + False Positive
    ax2 = axes[1]
    x2 = np.arange(len(model_names))
    width2 = 0.35

    bars_missed = ax2.bar(x2 - width2 / 2, missed_rates, width2,
                          color='#F44336', edgecolor='white', alpha=0.85, label='Пропущено')
    bars_fp = ax2.bar(x2 + width2 / 2, fp_counts, width2,
                      color='#FF9800', edgecolor='white', alpha=0.85, label='Ложные срабатывания')

    for bar, val in zip(bars_missed, missed_rates):
        if val > 0:
            ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                     f'{val:.1f}%', ha='center', fontsize=12, fontweight='bold', color='red')
        else:
            ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                     '0', ha='center', fontsize=12, fontweight='bold', color='green')

    for bar, val in zip(bars_fp, fp_counts):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                 str(val), ha='center', fontsize=12, fontweight='bold')

    ax2.set_xticks(x2)
    ax2.set_xticklabels(model_names, fontsize=9, rotation=15)
    ax2.set_ylabel('Количество / Процент', fontsize=12)
    ax2.set_title('Пропущенные аллергены и ложные срабатывания', fontsize=12, pad=12)
    ax2.legend(fontsize=10)
    ax2.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    path = OUTPUT_DIR / "01_allergen_comparison.png"
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


# ==================== 2. СВОДНАЯ ТАБЛИЦА МЕТРИК БЕНЧМАРКА ====================

def plot_benchmark_table():
    """Группированная столбчатая диаграмма по 4 ключевым метрикам"""
    files = [
        "results/benchmark_yandexgpt_5_lite.json",
        "results/benchmark_yandexgpt_5.1_pro.json",
        "results/benchmark_deepseek_3.2.json",
        "results/benchmark_qwen3_235b.json",
    ]

    all_data = [load_json(f) for f in files]

    # Собираем метрики
    json_valid_rates = []
    schema_valid_rates = []
    avg_scores = []
    avg_times = []

    for data in all_data:
        results = data['results']
        total = len(results)
        json_valid_rates.append(sum(1 for r in results if r['json_valid']) / total * 100)
        schema_valid_rates.append(sum(1 for r in results if r['schema_valid']) / total * 100)
        avg_scores.append(np.mean([r['score'] for r in results if r['score'] is not None]))
        avg_times.append(np.mean([r['response_time_ms'] for r in results]))

    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle('Сравнение ключевых метрик бенчмарка', fontsize=16, fontweight='bold', y=0.99)

    metric_configs = [
        (axes[0, 0], 'JSON Valid (%)', json_valid_rates, 'Доля корректного JSON', 0, 110),
        (axes[0, 1], 'Schema Valid (%)', schema_valid_rates, 'Соответствие схеме ответа', 0, 110),
        (axes[1, 0], 'Средний Score', avg_scores, 'Средняя оценка (0-10)', 0, 11),
        (axes[1, 1], 'Среднее время ответа (мс)', avg_times, 'Быстродействие', 0, max(avg_times) * 1.3),
    ]

    for ax, title, values, subtitle, ymin, ymax in metric_configs:
        x = np.arange(len(MODEL_SHORT))
        width = 0.6

        bars = ax.bar(x, values, width, color=COLORS_MODEL, edgecolor='white', alpha=0.9)

        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + (ymax - ymin) * 0.02,
                    f'{val:.1f}' if val < 100 else f'{val:.0f}',
                    ha='center', fontsize=13, fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels(MODEL_SHORT, fontsize=9)
        ax.set_title(f'{subtitle}', fontsize=13, pad=10)
        ax.set_ylim(ymin, ymax)
        ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    path = OUTPUT_DIR / "02_benchmark_metrics.png"
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


# ==================== 3. СРАВНЕНИЕ ПО КАТЕГОРИЯМ СЛОЖНОСТИ ====================

def plot_scores_by_category():
    """Группированная столбчатая: средний score по категориям"""
    files = [
        "results/benchmark_yandexgpt_5_lite.json",
        "results/benchmark_yandexgpt_5.1_pro.json",
        "results/benchmark_deepseek_3.2.json",
        "results/benchmark_qwen3_235b.json",
    ]

    all_data = [load_json(f) for f in files]
    categories = ['simple', 'medium', 'complex', 'provocative']
    cat_labels = ['Простые', 'Средние', 'Сложные', 'Провокационные']

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.suptitle('Средний Score по категориям сложности', fontsize=15, fontweight='bold')

    x = np.arange(len(cat_labels))
    width = 0.2

    for i, (data, color, label) in enumerate(zip(all_data, COLORS_MODEL, MODELS)):
        results = data['results']
        means = []
        for cat in categories:
            cat_scores = [r['score'] for r in results if r['category'] == cat and r['score'] is not None]
            means.append(np.mean(cat_scores) if cat_scores else 0)

        offset = (i - 1.5) * width
        bars = ax.bar(x + offset, means, width, color=color, edgecolor='white',
                      alpha=0.9, label=label)

        for bar, mean in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15,
                    f'{mean:.1f}', ha='center', fontsize=9, fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(cat_labels, fontsize=12)
    ax.set_ylabel('Средний Score', fontsize=12)
    ax.set_ylim(0, 11)
    ax.legend(fontsize=10, loc='upper right')
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    path = OUTPUT_DIR / "03_scores_by_category.png"
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


# ==================== 4. СРАВНЕНИЕ СКОРОСТИ ПО КАТЕГОРИЯМ ====================

def plot_time_by_category():
    """Группированная столбчатая: среднее время по категориям"""
    files = [
        "results/benchmark_yandexgpt_5_lite.json",
        "results/benchmark_yandexgpt_5.1_pro.json",
        "results/benchmark_deepseek_3.2.json",
        "results/benchmark_qwen3_235b.json",
    ]

    all_data = [load_json(f) for f in files]
    categories = ['simple', 'medium', 'complex', 'provocative']
    cat_labels = ['Простые', 'Средние', 'Сложные', 'Провокационные']

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.suptitle('Среднее время ответа по категориям сложности', fontsize=15, fontweight='bold')

    x = np.arange(len(cat_labels))
    width = 0.2

    for i, (data, color, label) in enumerate(zip(all_data, COLORS_MODEL, MODELS)):
        results = data['results']
        means = []
        for cat in categories:
            cat_times = [r['response_time_ms'] for r in results if r['category'] == cat]
            means.append(np.mean(cat_times) if cat_times else 0)

        offset = (i - 1.5) * width
        bars = ax.bar(x + offset, means, width, color=color, edgecolor='white',
                      alpha=0.9, label=label)

        for bar, mean in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 50,
                    f'{mean:.0f}', ha='center', fontsize=8, fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(cat_labels, fontsize=12)
    ax.set_ylabel('Время ответа (мс)', fontsize=12)
    ax.legend(fontsize=10, loc='upper left')
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    path = OUTPUT_DIR / "04_time_by_category.png"
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


# ==================== 5. СРАВНЕНИЕ ПЕРСОНАЛИЗАЦИИ ====================

def plot_personalization_comparison():
    """Столбчатая диаграмма: средний Δscore по моделям"""
    files = [
        "results/personalization_yandexgpt_5_lite.json",
        "results/personalization_yandexgpt_5.1_pro.json",
        "results/personalization_deepseek_3.2.json",
        "results/personalization_qwen3_235b.json",
    ]

    all_data = [load_json(f) for f in files]
    avg_deltas = [d['avg_delta_score'] for d in all_data]
    max_deltas = [d['max_delta_score'] for d in all_data]

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle('Сравнение персонализации: средний разброс оценок (Δscore)', fontsize=14, fontweight='bold')

    x = np.arange(len(MODEL_SHORT))
    width = 0.35

    bars_avg = ax.bar(x - width / 2, avg_deltas, width, color=COLORS_MODEL, edgecolor='white',
                      alpha=0.9, label='Средний Δscore')
    bars_max = ax.bar(x + width / 2, max_deltas, width, color=COLORS_MODEL, edgecolor='black',
                      alpha=0.5, label='Макс. Δscore', hatch='//')

    for bar, val in zip(bars_avg, avg_deltas):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                f'{val:.1f}', ha='center', fontsize=14, fontweight='bold')

    for bar, val in zip(bars_max, max_deltas):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                f'{val:.0f}', ha='center', fontsize=11)

    ax.set_xticks(x)
    ax.set_xticklabels(MODEL_SHORT, fontsize=10)
    ax.set_ylabel('Разброс оценок (баллы)', fontsize=12)
    ax.set_ylim(0, max(max_deltas) + 1.5)
    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3)

    # Аннотация
    best_model = MODELS[avg_deltas.index(max(avg_deltas))]
    ax.text(0.5, -0.15, f' Наибольший разброс: {best_model} (Δscore={max(avg_deltas):.1f})',
            transform=ax.transAxes, ha='center', fontsize=12, fontweight='bold',
            color=COLORS_MODEL[avg_deltas.index(max(avg_deltas))])

    plt.tight_layout()
    path = OUTPUT_DIR / "05_personalization_comparison.png"
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


def plot_personalization_heatmaps():
    """Тепловые карты персонализации для всех моделей на одном листе"""
    files = [
        "results/personalization_yandexgpt_5_lite.json",
        "results/personalization_yandexgpt_5.1_pro.json",
        "results/personalization_deepseek_3.2.json",
        "results/personalization_qwen3_235b.json",
    ]

    all_data = [load_json(f) for f in files]

    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle('Тепловые карты персонализации: Score по профилям и составам',
                 fontsize=15, fontweight='bold', y=0.99)

    profiles_labels = ['A\n(Сухая)', 'B\n(Жирная)', 'C\n(Чувств.)', 'D\n(Комби.)', 'E\n(Норм.)']

    for idx, (data, ax, color_base) in enumerate(zip(all_data, axes.flatten(), COLORS_MODEL)):
        details = data['details']
        compositions = [d['composition'][:35] + '...' for d in details]
        profiles = ['A', 'B', 'C', 'D', 'E']

        matrix = []
        for detail in details:
            row = [detail['scores'].get(p, 0) for p in profiles]
            matrix.append(row)

        im = ax.imshow(matrix, cmap='RdYlGn', aspect='auto', vmin=0, vmax=10)

        for i in range(len(compositions)):
            for j in range(len(profiles)):
                val = matrix[i][j]
                text_color = 'white' if val <= 4 or val >= 9 else 'black'
                ax.text(j, i, val, ha='center', va='center', fontsize=13,
                        fontweight='bold', color=text_color)

        ax.set_xticks(range(len(profiles)))
        ax.set_xticklabels(profiles_labels, fontsize=9)
        ax.set_yticks(range(len(compositions)))
        ax.set_yticklabels(compositions, fontsize=9)
        ax.set_title(f'{data["model"]} (Δscore={data["avg_delta_score"]:.1f})',
                     fontsize=12, fontweight='bold', color=color_base, pad=10)

    plt.tight_layout()
    path = OUTPUT_DIR / "06_personalization_heatmaps.png"
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


# ==================== 6. СРАВНЕНИЕ ТОКЕНОВ ====================

def plot_tokens_comparison():
    """Сравнение потребления токенов"""
    files = [
        "results/benchmark_yandexgpt_5_lite.json",
        "results/benchmark_yandexgpt_5.1_pro.json",
        "results/benchmark_deepseek_3.2.json",
        "results/benchmark_qwen3_235b.json",
    ]

    all_data = [load_json(f) for f in files]

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.suptitle('Среднее потребление токенов по моделям', fontsize=14, fontweight='bold')

    x = np.arange(len(MODEL_SHORT))
    width = 0.25

    for i, (data, label) in enumerate(zip(all_data, MODELS)):
        results = data['results']
        input_mean = np.mean([r['tokens'].get('input_tokens', 0) for r in results])
        output_mean = np.mean([r['tokens'].get('output_tokens', 0) for r in results])
        total_mean = input_mean + output_mean

        # Три столбца: input, output, total
        offset = (i - 1.5) * width * 3
        ax.bar(x[i] - width + offset, input_mean, width, color='#BBDEFB', edgecolor='white',
               alpha=0.9, label='Input' if i == 0 else '')
        ax.bar(x[i] + offset, output_mean, width, color='#64B5F6', edgecolor='white',
               alpha=0.9, label='Output' if i == 0 else '')
        ax.bar(x[i] + width + offset, total_mean, width, color=COLORS_MODEL[i], edgecolor='white',
               alpha=0.9, label=f'{label} (Total)')

        ax.text(x[i] + width + offset, total_mean + 30, f'{total_mean:.0f}',
                ha='center', fontsize=10, fontweight='bold', color=COLORS_MODEL[i])

    ax.set_xticks(x)
    ax.set_xticklabels(MODEL_SHORT, fontsize=10)
    ax.set_ylabel('Количество токенов', fontsize=12)
    ax.legend(fontsize=9, loc='upper left', ncol=2)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    path = OUTPUT_DIR / "07_tokens_comparison.png"
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


# ==================== 7. ИТОГОВЫЙ СВОДНЫЙ ДАШБОРД ====================

def plot_final_comparison_dashboard():
    """Один большой дашборд со всеми сравнениями для защиты"""
    files_benchmark = [
        "results/benchmark_yandexgpt_5_lite.json",
        "results/benchmark_yandexgpt_5.1_pro.json",
        "results/benchmark_deepseek_3.2.json",
        "results/benchmark_qwen3_235b.json",
    ]
    files_allergen = [
        "results/allergen_test_yandexgpt_5_lite.json",
        "results/allergen_test_yandexgpt_5.1_pro.json",
        "results/allergen_test_deepseek_3.2.json",
        "results/allergen_test_qwen3_235b.json",
    ]
    files_pers = [
        "results/personalization_yandexgpt_5_lite.json",
        "results/personalization_yandexgpt_5.1_pro.json",
        "results/personalization_deepseek_3.2.json",
        "results/personalization_qwen3_235b.json",
    ]

    bm_data = [load_json(f) for f in files_benchmark]
    al_data = [load_json(f) for f in files_allergen]
    pr_data = [load_json(f) for f in files_pers]

    fig = plt.figure(figsize=(20, 14))
    fig.suptitle('Итоговое сравнение LLM-моделей для персонализированной оценки косметических составов',
                 fontsize=17, fontweight='bold', y=0.99)

    gs = fig.add_gridspec(3, 4, hspace=0.45, wspace=0.4)

    # --- KPI карточки (верхний ряд) ---
    # Карточка 1: Allergen Detection Rate
    ax1 = fig.add_subplot(gs[0, 0])
    det_rates = [d['detection_rate'] for d in al_data]
    x = np.arange(len(MODEL_SHORT))
    bars = ax1.bar(x, det_rates, 0.6, color=COLORS_MODEL, edgecolor='white', alpha=0.9)
    for bar, val in zip(bars, det_rates):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                 f'{val:.0f}%', ha='center', fontsize=11, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(MODEL_SHORT, fontsize=7)
    ax1.set_title('Allergen Detection Rate', fontsize=11, fontweight='bold')
    ax1.set_ylim(0, 115)
    ax1.axhline(y=100, color='green', linestyle='--', alpha=0.3)
    ax1.grid(axis='y', alpha=0.2)

    # Карточка 2: JSON Valid
    ax2 = fig.add_subplot(gs[0, 1])
    json_rates = [sum(1 for r in d['results'] if r['json_valid']) / len(d['results']) * 100 for d in bm_data]
    bars = ax2.bar(x, json_rates, 0.6, color=COLORS_MODEL, edgecolor='white', alpha=0.9)
    for bar, val in zip(bars, json_rates):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 f'{val:.0f}%', ha='center', fontsize=11, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels(MODEL_SHORT, fontsize=7)
    ax2.set_title('JSON Valid Rate', fontsize=11, fontweight='bold')
    ax2.set_ylim(80, 108)
    ax2.grid(axis='y', alpha=0.2)

    # Карточка 3: Среднее время
    ax3 = fig.add_subplot(gs[0, 2])
    avg_times = [np.mean([r['response_time_ms'] for r in d['results']]) for d in bm_data]
    bars = ax3.bar(x, avg_times, 0.6, color=COLORS_MODEL, edgecolor='white', alpha=0.9)
    for bar, val in zip(bars, avg_times):
        ax3.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 100,
                 f'{val:.0f}мс', ha='center', fontsize=10, fontweight='bold')
    ax3.set_xticks(x)
    ax3.set_xticklabels(MODEL_SHORT, fontsize=7)
    ax3.set_title('Среднее время ответа', fontsize=11, fontweight='bold')
    ax3.grid(axis='y', alpha=0.2)

    # Карточка 4: Персонализация
    ax4 = fig.add_subplot(gs[0, 3])
    avg_deltas = [d['avg_delta_score'] for d in pr_data]
    bars = ax4.bar(x, avg_deltas, 0.6, color=COLORS_MODEL, edgecolor='white', alpha=0.9)
    for bar, val in zip(bars, avg_deltas):
        ax4.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.08,
                 f'{val:.1f}', ha='center', fontsize=12, fontweight='bold')
    ax4.set_xticks(x)
    ax4.set_xticklabels(MODEL_SHORT, fontsize=7)
    ax4.set_title('Персонализация (Δscore)', fontsize=11, fontweight='bold')
    ax4.set_ylim(0, max(avg_deltas) + 1)
    ax4.grid(axis='y', alpha=0.2)

    # --- Средний ряд: Score и Время по категориям ---
    ax5 = fig.add_subplot(gs[1, :2])
    categories = ['simple', 'medium', 'complex', 'provocative']
    cat_labels = ['Простые', 'Средние', 'Сложные', 'Провокационные']
    x5 = np.arange(len(cat_labels))
    width5 = 0.2

    for i, (data, color, label) in enumerate(zip(bm_data, COLORS_MODEL, MODELS)):
        results = data['results']
        means = [np.mean([r['score'] for r in results if r['category'] == cat and r['score'] is not None]) for cat in
                 categories]
        offset = (i - 1.5) * width5
        ax5.bar(x5 + offset, means, width5, color=color, edgecolor='white', alpha=0.9, label=label)

    ax5.set_xticks(x5)
    ax5.set_xticklabels(cat_labels, fontsize=11)
    ax5.set_ylabel('Средний Score', fontsize=11)
    ax5.set_title('Score по категориям сложности', fontsize=12, fontweight='bold')
    ax5.set_ylim(0, 11)
    ax5.legend(fontsize=8, ncol=2)
    ax5.grid(axis='y', alpha=0.2)

    ax6 = fig.add_subplot(gs[1, 2:])
    for i, (data, color, label) in enumerate(zip(bm_data, COLORS_MODEL, MODELS)):
        results = data['results']
        means = [np.mean([r['response_time_ms'] for r in results if r['category'] == cat]) for cat in categories]
        offset = (i - 1.5) * width5
        ax6.bar(x5 + offset, means, width5, color=color, edgecolor='white', alpha=0.9, label=label)

    ax6.set_xticks(x5)
    ax6.set_xticklabels(cat_labels, fontsize=11)
    ax6.set_ylabel('Время ответа (мс)', fontsize=11)
    ax6.set_title('Время ответа по категориям сложности', fontsize=12, fontweight='bold')
    ax6.legend(fontsize=8, ncol=2)
    ax6.grid(axis='y', alpha=0.2)

    # --- Нижний ряд: Тепловые карты персонализации (2 лучшие модели) ---
    # Выбираем 2 модели с лучшей персонализацией
    best_indices = np.argsort(avg_deltas)[-2:][::-1]  # индексы двух лучших

    for subplot_idx, data_idx in enumerate(best_indices):
        ax = fig.add_subplot(gs[2, subplot_idx * 2:(subplot_idx + 1) * 2])
        data = pr_data[data_idx]
        profiles = ['A', 'B', 'C', 'D', 'E']
        p_labels = ['A\nСух.', 'B\nЖир.', 'C\nЧув.', 'D\nКом.', 'E\nНор.']
        compositions = [d['composition'][:30] + '...' for d in data['details']]

        matrix = []
        for detail in data['details']:
            matrix.append([detail['scores'].get(p, 0) for p in profiles])

        im = ax.imshow(matrix, cmap='RdYlGn', aspect='auto', vmin=0, vmax=10)
        for i in range(len(compositions)):
            for j in range(len(profiles)):
                val = matrix[i][j]
                ax.text(j, i, val, ha='center', va='center', fontsize=11, fontweight='bold',
                        color='white' if val <= 4 or val >= 9 else 'black')

        ax.set_xticks(range(len(profiles)))
        ax.set_xticklabels(p_labels, fontsize=8)
        ax.set_yticks(range(len(compositions)))
        ax.set_yticklabels(compositions, fontsize=8)
        ax.set_title(f'{data["model"]} (Δscore={data["avg_delta_score"]:.1f})',
                     fontsize=12, fontweight='bold', color=COLORS_MODEL[data_idx])

    # Финальный вывод
    best_allergen = MODELS[det_rates.index(max(det_rates))]
    best_avg_delta = MODELS[avg_deltas.index(max(avg_deltas))]
    fastest = MODELS[avg_times.index(min(avg_times))]

    summary_text = (
        f"Выводы:\n"
        f"🏆 Лучшая детекция аллергенов: {best_allergen} ({max(det_rates):.0f}%)\n"
        f"👤 Лучшая персонализация: {best_avg_delta} (Δscore={max(avg_deltas):.1f})\n"
        f"⚡ Самый быстрый: {fastest} ({min(avg_times):.0f}мс)"
    )
    fig.text(0.5, -0.01, summary_text, ha='center', fontsize=13, fontweight='bold',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#E3F2FD', alpha=0.9),
             transform=fig.transFigure)

    path = OUTPUT_DIR / "00_final_comparison_dashboard.png"
    plt.savefig(path, dpi=250, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


if __name__ == "__main__":
    print("Генерация сравнительных графиков для 4 моделей...\n")

    plot_allergen_comparison()
    plot_benchmark_table()
    plot_scores_by_category()
    plot_time_by_category()
    plot_personalization_comparison()
    plot_personalization_heatmaps()
    plot_tokens_comparison()