"""Строит poker_engine/preflop_table.py: 169 стартовых рук, упорядоченных по эквити
против одной случайной руки (all-in префлоп). Используется для диапазонов вида 'top15%'.

Запуск: python scripts/build_preflop_ranking.py [--iterations 200000]
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from poker_engine.evaluator import evaluate  # noqa: E402
from poker_engine.ranges import all_labels, label_combos  # noqa: E402


def equity_vs_random(args: tuple[str, int, int]) -> tuple[str, float]:
    label, iterations, seed = args
    rng = random.Random(seed)
    # Эквити одинаково для всех комбинаций класса (симметрия мастей), берём первую.
    hero = list(label_combos(label)[0])
    deck = [c for c in range(52) if c not in hero]
    total = 0.0
    for _ in range(iterations):
        cards = rng.sample(deck, 7)  # 2 карты оппонента + 5 карт борда
        board = cards[2:]
        h, v = evaluate(hero + board), evaluate(cards[:2] + board)
        total += 1.0 if h > v else 0.5 if h == v else 0.0
    return label, 100 * total / iterations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=200_000)
    args = parser.parse_args()

    jobs = [(label, args.iterations, i) for i, label in enumerate(all_labels())]
    with Pool() as pool:
        results = pool.map(equity_vs_random, jobs)
    results.sort(key=lambda item: -item[1])

    lines = [
        '"""Сгенерировано scripts/build_preflop_ranking.py — не редактировать вручную.',
        "",
        "169 классов стартовых рук, отсортированных по эквити (%) против одной случайной руки",
        f"(all-in префлоп, Монте-Карло, {args.iterations} раздач на руку).",
        '"""',
        "",
        "PREFLOP_RANKING: list[tuple[str, float]] = [",
    ]
    lines += [f'    ("{label}", {equity:.1f}),' for label, equity in results]
    lines.append("]")
    path = os.path.join(ROOT, "poker_engine", "preflop_table.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Записано {len(results)} рук в {path}")


if __name__ == "__main__":
    main()
