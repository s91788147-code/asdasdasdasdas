"""Эквити — доля банка, которую рука (или диапазон) забирает в среднем к риверу.

Если перебор всех вариантов дешёвый (терн, флоп с конкретными руками), считаем точно;
иначе — методом Монте-Карло.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from itertools import accumulate, combinations, product
from typing import Sequence

from .evaluator import evaluate
from .ranges import Range


@dataclass
class EquityResult:
    equity: list[float]  # доля банка 0..1 (при дележе банк делится поровну)
    win: list[float]     # доля единоличных побед
    tie: list[float]     # доля раздач с дележом банка
    samples: int         # число перебранных или сыгранных раздач
    exact: bool
    stderr: float        # стандартная ошибка эквити первого игрока (0 при точном переборе)


def calc_equity(
    ranges: Sequence[Range],
    board: Sequence[int] = (),
    dead: Sequence[int] = (),
    iterations: int = 20_000,
    seed: int | None = None,
    exact_limit: int = 400_000,
) -> EquityResult:
    """Эквити двух и более игроков; каждый задан диапазоном (конкретная рука — диапазон из 1 комбинации)."""
    if len(ranges) < 2:
        raise ValueError("Нужно минимум два игрока")
    if len(board) not in (0, 3, 4, 5):
        raise ValueError("На борде должно быть 0, 3, 4 или 5 карт")
    known = set(board) | set(dead)
    if len(known) != len(board) + len(dead):
        raise ValueError("Карты борда и мёртвые карты пересекаются")

    live = []
    for i, r in enumerate(ranges):
        lr = r.without(known)
        if not lr.combos:
            raise ValueError(f"У игрока {i + 1} не осталось возможных рук: все заблокированы картами борда")
        live.append(lr)

    to_deal = 5 - len(board)
    deck_left = 52 - len(known) - 2 * len(live)
    work = math.prod(len(r.combos) for r in live) * math.comb(deck_left, to_deal) * len(live)
    if work <= exact_limit:
        return _exact(live, list(board), known, to_deal)
    return _monte_carlo(live, list(board), known, to_deal, iterations, random.Random(seed))


def _score_showdown(scores, weight, eq, win, tie) -> float:
    """Раскладывает результат одной раздачи; возвращает долю банка первого игрока."""
    best = max(scores)
    winners = [i for i, s in enumerate(scores) if s == best]
    if len(winners) == 1:
        eq[winners[0]] += weight
        win[winners[0]] += weight
    else:
        share = weight / len(winners)
        for i in winners:
            eq[i] += share
            tie[i] += weight
    return (1.0 / len(winners)) if 0 in winners else 0.0


def _exact(live, board, known, to_deal) -> EquityResult:
    n = len(live)
    eq, win, tie = [0.0] * n, [0.0] * n, [0.0] * n
    total, samples = 0.0, 0
    base = [c for c in range(52) if c not in known]
    for hands in product(*(list(r.combos.items()) for r in live)):
        used: set[int] = set()
        weight = 1.0
        for (a, b), w in hands:
            if a in used or b in used:
                break
            used.update((a, b))
            weight *= w
        else:
            holes = [list(combo) for combo, _ in hands]
            deck = [c for c in base if c not in used]
            for extra in combinations(deck, to_deal):
                full = board + list(extra)
                _score_showdown([evaluate(h + full) for h in holes], weight, eq, win, tie)
                total += weight
                samples += 1
    if total == 0:
        raise ValueError("Руки игроков пересекаются: нет ни одной допустимой раздачи")
    return EquityResult([x / total for x in eq], [x / total for x in win], [x / total for x in tie],
                        samples, True, 0.0)


def _monte_carlo(live, board, known, to_deal, iterations, rng: random.Random) -> EquityResult:
    n = len(live)
    combos = [list(r.combos) for r in live]
    cum_weights = [list(accumulate(r.combos.values())) for r in live]
    uniform = [len(set(r.combos.values())) == 1 for r in live]
    base = [c for c in range(52) if c not in known]
    eq, win, tie = [0.0] * n, [0.0] * n, [0.0] * n
    s1 = s2 = 0.0

    def draw(i: int):
        if len(combos[i]) == 1:
            return combos[i][0]
        if uniform[i]:
            return rng.choice(combos[i])
        return rng.choices(combos[i], cum_weights=cum_weights[i])[0]

    for _ in range(iterations):
        # Выбираем руки всех игроков заново, пока они не перестанут пересекаться:
        # так сохраняется правильное совместное распределение (card removal).
        for _attempt in range(1000):
            hands = [draw(i) for i in range(n)]
            flat = [c for h in hands for c in h]
            if len(set(flat)) == len(flat):
                break
        else:
            raise ValueError("Не удалось раздать непересекающиеся руки: диапазоны блокируют друг друга")
        used = set(flat)
        full = board + rng.sample([c for c in base if c not in used], to_deal)
        x = _score_showdown([evaluate(list(h) + full) for h in hands], 1.0, eq, win, tie)
        s1 += x
        s2 += x * x

    mean = s1 / iterations
    stderr = math.sqrt(max(s2 / iterations - mean * mean, 0.0) / iterations)
    return EquityResult([x / iterations for x in eq], [x / iterations for x in win],
                        [x / iterations for x in tie], iterations, False, stderr)
