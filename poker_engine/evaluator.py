"""Оценка силы покерной руки (от 1 до 7 карт).

evaluate() возвращает целое число: чем больше, тем сильнее рука. Две руки сравниваются
обычным сравнением чисел. Устройство числа: категория << 20 | пять «полубайтов» рангов
(rank + 1, в порядке значимости: например, для двух пар — старшая пара, младшая, кикер).
"""
from __future__ import annotations

from itertools import combinations
from typing import Sequence

from .cards import RANK_GEN, RANK_GEN_PL, RANK_NOM, RANK_NOM_PL, RANKS

HIGH_CARD, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)

CATEGORY_NAMES = ["Старшая карта", "Пара", "Две пары", "Тройка", "Стрит", "Флеш",
                  "Фулл-хаус", "Каре", "Стрит-флеш"]

_WHEEL = (1 << 12) | 0b1111  # A-2-3-4-5


def _straight_high(mask: int) -> int:
    """Старший ранг самого сильного стрита в 13-битной маске рангов или -1."""
    for high in range(12, 3, -1):
        need = 0b11111 << (high - 4)
        if mask & need == need:
            return high
    if mask & _WHEEL == _WHEEL:
        return 3  # стрит до пятёрки («колесо»)
    return -1


def _pack_ranks(ranks: Sequence[int]) -> int:
    value = 0
    for r in ranks:
        value = (value << 4) | (r + 1)
    return value << (4 * (5 - len(ranks)))


def _pack(category: int, ranks: Sequence[int]) -> int:
    return (category << 20) | _pack_ranks(ranks)


# Таблицы на все 8192 маски рангов: старший ранг стрита и упакованные 5 старших рангов.
STRAIGHT_HIGH = [_straight_high(m) for m in range(1 << 13)]
_TOP5 = [_pack_ranks([r for r in range(12, -1, -1) if m >> r & 1][:5]) for m in range(1 << 13)]


def evaluate(cards: Sequence[int]) -> int:
    n = len(cards)
    if n > 7:
        raise ValueError("Можно оценивать не больше 7 карт")
    counts = [0] * 13
    suit_masks = [0, 0, 0, 0]
    for c in cards:
        r = c >> 2
        counts[r] += 1
        suit_masks[c & 3] |= 1 << r

    if n >= 5:
        for m in suit_masks:
            if m.bit_count() >= 5:
                high = STRAIGHT_HIGH[m]
                if high >= 0:
                    return (STRAIGHT_FLUSH << 20) | ((high + 1) << 16)
                # При флеше из 7 и менее карт каре и фулл-хаус невозможны.
                return (FLUSH << 20) | _TOP5[m]

    rank_mask = suit_masks[0] | suit_masks[1] | suit_masks[2] | suit_masks[3]
    if rank_mask.bit_count() == n:  # все ранги разные: стрит или старшая карта
        high = STRAIGHT_HIGH[rank_mask]
        if high >= 0:
            return (STRAIGHT << 20) | ((high + 1) << 16)
        return _TOP5[rank_mask]

    quad = -1
    trips: list[int] = []
    pairs: list[int] = []
    singles: list[int] = []
    for r in range(12, -1, -1):
        k = counts[r]
        if k == 1:
            singles.append(r)
        elif k == 2:
            pairs.append(r)
        elif k == 3:
            trips.append(r)
        elif k == 4:
            quad = r

    if quad >= 0:
        others = trips[:1] + pairs[:1] + singles[:1]
        return _pack(QUADS, [quad, max(others)] if others else [quad])
    if trips and (len(trips) > 1 or pairs):
        second = max(trips[1] if len(trips) > 1 else -1, pairs[0] if pairs else -1)
        return _pack(FULL_HOUSE, [trips[0], second])
    high = STRAIGHT_HIGH[rank_mask]
    if high >= 0:
        return (STRAIGHT << 20) | ((high + 1) << 16)
    if trips:
        return _pack(TRIPS, [trips[0]] + singles[:2])
    if len(pairs) >= 2:
        kickers = pairs[2:3] + singles[:1]
        return _pack(TWO_PAIR, [pairs[0], pairs[1]] + ([max(kickers)] if kickers else []))
    return _pack(PAIR, [pairs[0]] + singles[:3])


def category(score: int) -> int:
    return score >> 20


def score_ranks(score: int) -> list[int]:
    """Ранги из упакованного числа (без пустых позиций)."""
    ranks = []
    for shift in (16, 12, 8, 4, 0):
        nibble = (score >> shift) & 0xF
        if nibble:
            ranks.append(nibble - 1)
    return ranks


def hand_name(score: int) -> str:
    """Человекочитаемое описание комбинации, например 'Две пары: тузы и восьмёрки, кикер K'."""
    cat = category(score)
    r = score_ranks(score)

    def kick(ranks: list[int]) -> str:
        if not ranks:
            return ""
        return (", кикер " if len(ranks) == 1 else ", кикеры ") + " ".join(RANKS[x] for x in ranks)

    if cat == STRAIGHT_FLUSH:
        return "Роял-флеш" if r[0] == 12 else f"Стрит-флеш до {RANK_GEN[r[0]]}"
    if cat == QUADS:
        return f"Каре {RANK_GEN_PL[r[0]]}" + kick(r[1:])
    if cat == FULL_HOUSE:
        return f"Фулл-хаус: {RANK_NOM_PL[r[0]]} и {RANK_NOM_PL[r[1]]}"
    if cat == FLUSH:
        return f"Флеш от {RANK_GEN[r[0]]} ({' '.join(RANKS[x] for x in r)})"
    if cat == STRAIGHT:
        return f"Стрит до {RANK_GEN[r[0]]}"
    if cat == TRIPS:
        return f"Тройка {RANK_GEN_PL[r[0]]}" + kick(r[1:])
    if cat == TWO_PAIR:
        return f"Две пары: {RANK_NOM_PL[r[0]]} и {RANK_NOM_PL[r[1]]}" + kick(r[2:])
    if cat == PAIR:
        return f"Пара {RANK_GEN_PL[r[0]]}" + kick(r[1:])
    return f"Старшая карта: {RANK_NOM[r[0]]}" + kick(r[1:]) if r else "Нет карт"


def best_five(cards: Sequence[int]) -> list[int]:
    """Лучшие 5 карт из 5-7 (перебор 21 комбинации)."""
    if len(cards) <= 5:
        return sorted(cards, reverse=True)
    best = max(combinations(cards, 5), key=evaluate)
    return sorted(best, reverse=True)
