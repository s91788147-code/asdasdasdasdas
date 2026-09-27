"""Высокоуровневый API со строковыми входами и JSON-совместимыми ответами.

Его используют и CLI (python -m poker_engine), и инструменты LLM-агента.
"""
from __future__ import annotations

from . import analysis, odds
from .analysis import STREETS
from .cards import cards_str, parse_cards
from .equity import calc_equity
from .ranges import parse_hand_or_range


def analyze(hand: str, board: str = "") -> dict:
    return analysis.analyze_hand(parse_cards(hand), parse_cards(board))


def equity(players: list[str], board: str = "", dead: str = "", iterations: int = 30_000,
           seed: int | None = None) -> dict:
    if not isinstance(players, list) or len(players) < 2:
        raise ValueError("players: нужен список минимум из двух рук/диапазонов (первый — герой)")
    ranges = [parse_hand_or_range(p) for p in players]
    board_cards, dead_cards = parse_cards(board), parse_cards(dead)
    iterations = min(max(int(iterations), 1_000), 200_000)
    res = calc_equity(ranges, board_cards, dead_cards, iterations=iterations, seed=seed)

    def live_combos(i: int) -> float:
        # Карты борда, мёртвые карты и конкретные руки других игроков убирают комбинации.
        known = board_cards + dead_cards
        for j, other in enumerate(ranges):
            if j != i and other.is_single():
                known += list(next(iter(other.combos)))
        return round(ranges[i].without(known).total(), 2)

    result: dict = {
        "street": STREETS.get(len(board_cards), "?"),
        "board": cards_str(board_cards),
        "method": "точный перебор" if res.exact else "Монте-Карло",
        "samples": res.samples,
        "players": [
            {
                "player": "герой" if i == 0 else f"оппонент {i}",
                "input": players[i],
                "live_combos": live_combos(i),
                "equity_pct": round(100 * res.equity[i], 2),
                "win_pct": round(100 * res.win[i], 2),
                "tie_pct": round(100 * res.tie[i], 2),
            }
            for i, r in enumerate(ranges)
        ],
    }
    if not res.exact:
        result["hero_margin_of_error_pct"] = round(100 * 1.96 * res.stderr, 2)
    return result


def outs(hand: str, villain: str, board: str) -> dict:
    return analysis.count_outs(parse_cards(hand), parse_hand_or_range(villain), parse_cards(board))


def breakdown(range_text: str, board: str = "", hero_hand: str = "") -> dict:
    hero = parse_cards(hero_hand) if hero_hand else None
    if hero is not None and len(hero) != 2:
        raise ValueError("hero_hand: нужны ровно две карты")
    return analysis.range_breakdown(parse_hand_or_range(range_text), parse_cards(board), hero)


pot_odds = odds.pot_odds
bet_math = odds.bet_math
