"""Карты: разбор строк и форматирование.

Карта кодируется целым числом 0..51: rank * 4 + suit, где
rank 0 = двойка ... 12 = туз, suit 0..3 = s, h, d, c (пики, червы, бубны, трефы).
"""
from __future__ import annotations

from typing import Iterable

RANKS = "23456789TJQKA"
SUITS = "shdc"

_SUIT_ALIASES = {"♠": "s", "♥": "h", "♦": "d", "♣": "c"}
_SEPARATORS = " ,;|/-_[]()\t\n"

# Названия рангов для человекочитаемых описаний.
RANK_NOM = ["двойка", "тройка", "четвёрка", "пятёрка", "шестёрка", "семёрка", "восьмёрка",
            "девятка", "десятка", "валет", "дама", "король", "туз"]
RANK_GEN = ["двойки", "тройки", "четвёрки", "пятёрки", "шестёрки", "семёрки", "восьмёрки",
            "девятки", "десятки", "валета", "дамы", "короля", "туза"]
RANK_NOM_PL = ["двойки", "тройки", "четвёрки", "пятёрки", "шестёрки", "семёрки", "восьмёрки",
               "девятки", "десятки", "валеты", "дамы", "короли", "тузы"]
RANK_GEN_PL = ["двоек", "троек", "четвёрок", "пятёрок", "шестёрок", "семёрок", "восьмёрок",
               "девяток", "десяток", "валетов", "дам", "королей", "тузов"]
SUIT_NAMES = ["пики", "червы", "бубны", "трефы"]


def rank_of(card: int) -> int:
    return card >> 2


def suit_of(card: int) -> int:
    return card & 3


def make_card(rank: int, suit: int) -> int:
    return rank * 4 + suit


def parse_card(text: str) -> int:
    """'Ah' -> int. Принимает также '10h' и символы мастей ♠♥♦♣."""
    s = text.strip()
    if s.startswith("10"):
        s = "T" + s[2:]
    if len(s) != 2:
        raise ValueError(f"Некорректная карта: {text!r}")
    rank = RANKS.find(s[0].upper())
    suit = SUITS.find(_SUIT_ALIASES.get(s[1], s[1]).lower())
    if rank < 0 or suit < 0:
        raise ValueError(f"Некорректная карта: {text!r} (формат: ранг 2-9/T/J/Q/K/A + масть s/h/d/c)")
    return make_card(rank, suit)


def parse_cards(text: str | Iterable[int] | None) -> list[int]:
    """'AhKh', 'Ah Kh', 'Ah,Kh', 'A♥K♥', '10h9h' -> список карт. Повторы запрещены."""
    if text is None:
        return []
    if not isinstance(text, str):
        cards = list(text)
    else:
        s = text
        for sym, letter in _SUIT_ALIASES.items():
            s = s.replace(sym, letter)
        s = s.replace("10", "T")
        for sep in _SEPARATORS:
            s = s.replace(sep, "")
        if len(s) % 2:
            raise ValueError(f"Не удалось разобрать карты: {text!r}")
        cards = [parse_card(s[i:i + 2]) for i in range(0, len(s), 2)]
    if len(set(cards)) != len(cards):
        raise ValueError(f"Повторяющиеся карты: {text!r}")
    return cards


def card_str(card: int) -> str:
    return RANKS[rank_of(card)] + SUITS[suit_of(card)]


def cards_str(cards: Iterable[int]) -> str:
    return " ".join(card_str(c) for c in cards)


def check_disjoint(*groups: Iterable[int]) -> None:
    """Бросает ValueError, если одна и та же карта встречается в разных группах."""
    seen: set[int] = set()
    for group in groups:
        for c in group:
            if c in seen:
                raise ValueError(f"Карта {card_str(c)} указана дважды (например, и в руке, и на борде)")
            seen.add(c)
