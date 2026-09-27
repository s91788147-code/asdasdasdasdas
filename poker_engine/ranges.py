"""Диапазоны рук в стандартной нотации.

Примеры: 'QQ+, AKs, AQo+, 99-66, A2s+, KTs+, JTs-54s, AhKh, top15%, AKo:0.5'
  QQ+       — QQ, KK, AA
  A2s+      — A2s ... AKs (кикер растёт до ранга на единицу ниже старшей карты)
  99-66     — 99, 88, 77, 66
  A5s-A2s   — A5s, A4s, A3s, A2s
  JTs-54s   — одномастные коннекторы JTs, T9s, ..., 54s
  AK        — AKs + AKo (16 комбинаций)
  AhKh      — конкретная комбинация
  top15%    — 15% лучших стартовых рук (по эквити против случайной руки)
  any       — все 1326 комбинаций
  :0.5      — вес (частота), с которой рука входит в диапазон
Если рука встречается несколько раз, действует последнее указание (удобно для весов).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations

from .cards import RANKS, card_str, make_card, parse_cards, rank_of, suit_of

Combo = tuple[int, int]  # (старшая карта, младшая карта) по коду карты

TOTAL_COMBOS = 1326

_R = "[2-9TJQKA]"
_COMBO_RE = re.compile(rf"^({_R}[shdc])({_R}[shdc])$", re.IGNORECASE)
_CLASS_RE = re.compile(rf"^({_R})({_R})([so]?)(\+?)$", re.IGNORECASE)
_SPAN_RE = re.compile(rf"^({_R})({_R})([so]?)-({_R})({_R})([so]?)$", re.IGNORECASE)
_TOP_RE = re.compile(r"^(?:top)?(\d+(?:\.\d+)?)%$", re.IGNORECASE)


def combo_key(a: int, b: int) -> Combo:
    return (a, b) if a > b else (b, a)


def hand_label(combo: Combo) -> str:
    """(Ah, Kh) -> 'AKs', (Ah, Kd) -> 'AKo', (Ah, Ad) -> 'AA'."""
    a, b = combo
    ra, rb = rank_of(a), rank_of(b)
    if ra < rb:
        ra, rb = rb, ra
    if ra == rb:
        return RANKS[ra] * 2
    return RANKS[ra] + RANKS[rb] + ("s" if suit_of(a) == suit_of(b) else "o")


def label_combos(label: str) -> list[Combo]:
    """'AA' -> 6 комбинаций, 'AKs' -> 4, 'AKo' -> 12, 'AK' -> 16."""
    r1, r2 = RANKS.index(label[0]), RANKS.index(label[1])
    kind = label[2:3]
    if r1 == r2:
        return [combo_key(make_card(r1, s1), make_card(r1, s2)) for s1, s2 in combinations(range(4), 2)]
    result = []
    for s1 in range(4):
        for s2 in range(4):
            if (kind == "s" and s1 != s2) or (kind == "o" and s1 == s2):
                continue
            result.append(combo_key(make_card(r1, s1), make_card(r2, s2)))
    return result


def all_labels() -> list[str]:
    """Все 169 классов стартовых рук."""
    labels = []
    for r1 in range(12, -1, -1):
        for r2 in range(r1, -1, -1):
            if r1 == r2:
                labels.append(RANKS[r1] * 2)
            else:
                labels.append(RANKS[r1] + RANKS[r2] + "s")
                labels.append(RANKS[r1] + RANKS[r2] + "o")
    return labels


def _labels(r1: int, r2: int, kind: str) -> list[str]:
    if r1 < r2:
        r1, r2 = r2, r1
    if r1 == r2:
        return [RANKS[r1] * 2]
    base = RANKS[r1] + RANKS[r2]
    return [base + k for k in ("s", "o") if not kind or k == kind]


def top_percent_labels(percent: float) -> list[str]:
    """Лучшие percent% стартовых рук (по числу комбинаций)."""
    from .preflop_table import PREFLOP_RANKING

    target = TOTAL_COMBOS * percent / 100
    chosen: list[str] = []
    total = 0
    for label, _equity in PREFLOP_RANKING:
        size = 6 if len(label) == 2 else (4 if label[2] == "s" else 12)
        # берём руку, если с ней ближе к цели, чем без неё
        if abs(total + size - target) > abs(total - target):
            break
        chosen.append(label)
        total += size
    return chosen


def _parse_token(token: str) -> tuple[list[Combo], float]:
    weight = 1.0
    if ":" in token:
        token, w = token.split(":", 1)
        w = w.strip()
        weight = float(w[:-1]) / 100 if w.endswith("%") else float(w)
        if not 0 <= weight <= 1:
            raise ValueError(f"Вес должен быть от 0 до 1: {w!r}")
    token = re.sub(r"(?<![\d.])10(?![\d.%])", "T", token)  # 'A10s' -> 'ATs', но не 'top10%'

    if token.lower() in ("any", "all", "random", "100%"):
        return [combo_key(a, b) for a, b in combinations(range(52), 2)], weight

    if m := _TOP_RE.match(token):
        labels = top_percent_labels(float(m.group(1)))
        return [c for lab in labels for c in label_combos(lab)], weight

    if m := _COMBO_RE.match(token):
        a, b = parse_cards(token)
        return [combo_key(a, b)], weight

    if m := _CLASS_RE.match(token):
        r1, r2 = RANKS.index(m.group(1).upper()), RANKS.index(m.group(2).upper())
        kind, plus = m.group(3).lower(), m.group(4)
        if r1 < r2:
            r1, r2 = r2, r1
        if r1 == r2 and kind:
            raise ValueError(f"У пары не бывает одномастности: {token!r}")
        labels: list[str] = []
        if not plus:
            labels = _labels(r1, r2, kind)
        elif r1 == r2:
            for r in range(r1, 13):
                labels += _labels(r, r, "")
        else:
            for k in range(r2, r1):
                labels += _labels(r1, k, kind)
        return [c for lab in labels for c in label_combos(lab)], weight

    if m := _SPAN_RE.match(token):
        a1, a2 = RANKS.index(m.group(1).upper()), RANKS.index(m.group(2).upper())
        b1, b2 = RANKS.index(m.group(4).upper()), RANKS.index(m.group(5).upper())
        kind_a, kind_b = m.group(3).lower(), m.group(6).lower()
        if kind_a != kind_b:
            raise ValueError(f"Разная одномастность в диапазоне {token!r}")
        a1, a2 = max(a1, a2), min(a1, a2)
        b1, b2 = max(b1, b2), min(b1, b2)
        labels = []
        if a1 == a2 and b1 == b2:  # 99-66
            for r in range(min(a1, b1), max(a1, b1) + 1):
                labels += _labels(r, r, "")
        elif a1 == b1:  # A5s-A2s
            for k in range(min(a2, b2), max(a2, b2) + 1):
                if k != a1:
                    labels += _labels(a1, k, kind_a)
        elif a1 - a2 == b1 - b2:  # JTs-54s
            lo = min(a2, b2)
            for d in range(abs(a1 - b1) + 1):
                labels += _labels(lo + d + (a1 - a2), lo + d, kind_a)
        else:
            raise ValueError(f"Не понимаю диапазон {token!r}")
        return [c for lab in labels for c in label_combos(lab)], weight

    raise ValueError(f"Не понимаю обозначение {token!r}")


@dataclass
class Range:
    """Диапазон: комбинация -> вес (0..1)."""

    combos: dict[Combo, float]

    @classmethod
    def parse(cls, text: str) -> "Range":
        combos: dict[Combo, float] = {}
        tokens = [t for t in re.split(r"[,;\n]+", text) if t.strip()]
        if not tokens:
            raise ValueError("Пустой диапазон")
        for raw in tokens:
            token = "".join(raw.split())
            found, weight = _parse_token(token)
            for combo in found:
                combos[combo] = weight
        combos = {c: w for c, w in combos.items() if w > 0}
        if not combos:
            raise ValueError(f"Диапазон {text!r} пуст")
        return cls(combos)

    @classmethod
    def from_cards(cls, cards: list[int]) -> "Range":
        if len(cards) != 2:
            raise ValueError("Рука должна состоять из двух карт")
        return cls({combo_key(cards[0], cards[1]): 1.0})

    def without(self, dead) -> "Range":
        dead = set(dead)
        return Range({c: w for c, w in self.combos.items() if c[0] not in dead and c[1] not in dead})

    def total(self) -> float:
        """Взвешенное число комбинаций."""
        return sum(self.combos.values())

    def is_single(self) -> bool:
        return len(self.combos) == 1

    def label_weights(self) -> dict[str, float]:
        """Взвешенное число комбинаций по классам рук ('AKs' -> 4.0 ...)."""
        result: dict[str, float] = {}
        for combo, w in self.combos.items():
            lab = hand_label(combo)
            result[lab] = result.get(lab, 0.0) + w
        return result

    def __len__(self) -> int:
        return len(self.combos)

    def __str__(self) -> str:
        if self.is_single():
            (a, b), = self.combos
            return card_str(a) + card_str(b)
        return f"диапазон из {self.total():g} комбинаций"


def parse_hand_or_range(text: str) -> Range:
    """'AhKh' -> одна комбинация; всё остальное разбирается как диапазон."""
    cleaned = "".join(text.split())
    if _COMBO_RE.match(cleaned.replace("10", "T")):
        return Range.from_cards(parse_cards(cleaned))
    return Range.parse(text)
