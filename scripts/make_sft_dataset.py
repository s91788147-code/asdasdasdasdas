"""Генератор обучающего датасета (SFT) для дообучения open-source LLM на покерных спотах.

Каждый пример — диалог в формате chat ("messages"): описание спота -> разбор с цифрами.
Все цифры (эквити, ауты, шансы банка, EV) считает движок, поэтому они точные;
текст ответа собирается по шаблону. Решение принимается по прямым шансам банка,
поэтому на флопе и терне это упрощение (без implied odds и будущих ставок).

Запуск:
  python scripts/make_sft_dataset.py --n 500 --out data/poker_sft.jsonl
Формат подходит для TRL SFTTrainer / Unsloth (поле "messages").
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from poker_engine.analysis import STREETS, analyze_hand  # noqa: E402
from poker_engine.cards import cards_str  # noqa: E402
from poker_engine.equity import calc_equity  # noqa: E402
from poker_engine.odds import pot_odds  # noqa: E402
from poker_engine.ranges import Range  # noqa: E402

SYSTEM = ("Ты — покерный тренер. Разбирай спот по шагам: рука и дро, эквити против диапазона, "
          "шансы банка, EV и решение.")
VILLAIN_RANGES = [
    ("тайтовый (топ-8%)", "top8%"),
    ("стандартный (топ-20%)", "top20%"),
    ("широкий (топ-40%)", "top40%"),
    ("сильный", "TT+, AQs+, AKo"),
    ("колл-диапазон BB", "22-99, A2s-AJs, K9s+, Q9s+, J9s+, T8s+, 97s+, 86s+, 75s+, 64s+, 54s, "
                         "ATo-AJo, KTo+, QTo+, JTo"),
]
BET_FRACTIONS = [0.33, 0.5, 0.75, 1.0, 1.5]
POTS = [6, 10, 20, 40, 60, 100]


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def make_example(seed: int) -> dict | None:
    rng = random.Random(seed)
    board_len = rng.choice([3, 3, 4, 5])
    deck = list(range(52))
    rng.shuffle(deck)
    hero, board = deck[:2], deck[2:2 + board_len]
    range_name, range_text = rng.choice(VILLAIN_RANGES)
    villain = Range.parse(range_text)
    if not villain.without(hero + board).combos:
        return None
    pot = rng.choice(POTS)
    bet = round(pot * rng.choice(BET_FRACTIONS), 1)
    street = STREETS[board_len]

    info = analyze_hand(hero, board)
    res = calc_equity([Range.from_cards(hero), villain], board, iterations=4_000, seed=seed)
    equity = 100 * res.equity[0]
    odds = pot_odds(pot + bet, bet, equity_pct=equity)
    required, ev = odds["required_equity_pct"], odds["ev_call"]

    user = (f"{street.capitalize()}. Мои карты: {cards_str(hero)}. Борд: {cards_str(board)}. "
            f"В банке {pot:g} bb, оппонент ставит {bet:g} bb. Его диапазон — {range_name}: {range_text}. "
            f"Колл или фолд?")
    lines = [f"Рука: {_lower_first(info['made_hand'])} ({_lower_first(info['hand_class'])})."]
    if info.get("draws"):
        lines.append("Дро: " + ", ".join(_lower_first(d) for d in info["draws"]) + ".")
    if "draw_completion" in info:
        d = info["draw_completion"]
        chance = f"на следующей карте {d['next_card_pct']}%"
        if "by_river_pct" in d:
            chance += f", к риверу {d['by_river_pct']}%"
        lines.append(f"Аутов на стрит/флеш: {d['outs']}; шанс доехать {chance}.")
    lines.append(f"Эквити против диапазона оппонента: {equity:.1f}%.")
    lines.append(f"Шансы банка: в банке {pot + bet:g} bb, доставить {bet:g} bb — нужно "
                 f"{bet:g} / ({pot + bet:g} + {bet:g}) = {required}% эквити.")
    lines.append(f"EV колла: {ev:+.1f} bb.")
    if equity >= required:
        lines.append(f"Решение: колл — эквити {equity:.1f}% выше требуемых {required}%.")
    else:
        lines.append(f"Решение: фолд — эквити {equity:.1f}% ниже требуемых {required}%.")
    if board_len < 5:
        lines.append("Это решение по прямым шансам банка; implied odds и ставки на следующих улицах "
                     "могут его сдвинуть.")
    return {"messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
        {"role": "assistant", "content": "\n".join(lines)},
    ]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=200, help="сколько примеров")
    parser.add_argument("--out", default=os.path.join(ROOT, "data", "poker_sft.jsonl"))
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    written = calls = 0
    seeds = iter(range(args.seed, args.seed + 10 * args.n))
    with Pool() as pool, open(args.out, "w", encoding="utf-8") as f:
        while written < args.n:
            batch = [next(seeds) for _ in range(args.n - written)]
            for example in pool.map(make_example, batch):
                if example and written < args.n:
                    f.write(json.dumps(example, ensure_ascii=False) + "\n")
                    written += 1
                    calls += example["messages"][2]["content"].count("Решение: колл")
    print(f"Записано {written} примеров в {args.out} (колл: {calls}, фолд: {written - calls})")


if __name__ == "__main__":
    main()
