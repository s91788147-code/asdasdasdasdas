import pytest

from poker_engine.analysis import analyze_hand, classify, count_outs, find_draws, range_breakdown
from poker_engine.cards import parse_cards as c
from poker_engine.ranges import parse_hand_or_range as hr


@pytest.mark.parametrize("hole, board, expected", [
    ("KsKd", "Qh7h2c", "overpair"),
    ("AsQd", "Qh7h2c", "top_pair"),
    ("As7d", "Qh7h2c", "second_pair"),
    ("9s9d", "Qh7h2c", "second_pair"),
    ("As2d", "Qh7h2c", "weak_pair"),
    ("5s5d", "Qh7h2c", "weak_pair"),
    ("7s7d", "Qh7h2c", "set"),
    ("As7d", "Qh7s7c", "trips"),
    ("Qs7d", "Qh7h2c", "two_pair"),
    ("AsKd", "Qh7h2c", "no_pair"),
    ("AhKh", "Qh7h2h", "flush"),
    ("9s8d", "Th7h6c", "straight"),
    ("2s3d", "9h8c7dTsJh", "board"),
    ("7s2d", "KhKc7d", "second_pair"),
])
def test_classify(hole, board, expected):
    assert classify(c(hole), c(board)) == expected


@pytest.mark.parametrize("hole, board, draw", [
    ("AhKh", "Qh7h2c", "nut_flush_draw"),
    ("Th9h", "Qh7h2c", "flush_draw"),
    ("9s8d", "Th7c2h", "oesd"),
    ("Js9d", "Qh8c2d", "gutshot"),
    ("As3d", "5h4c9d", "gutshot"),
    ("AsKd", "Qh7h2c", "two_overcards"),
    ("AsKs", "Qs7h2c", "backdoor_flush_draw"),
])
def test_draws(hole, board, draw):
    assert draw in find_draws(c(hole), c(board))


def test_analyze_flush_draw_outs():
    res = analyze_hand(c("AhKh"), c("Qh7h2c"))
    assert res["draw_completion"]["outs"] == 9
    assert res["draw_completion"]["by_river_pct"] == 35.0
    assert res["any_improvement"]["outs"] == 15  # 9 червей + 6 карт до топ-пары


def test_board_straight_is_not_an_out():
    # Терн 9 8 7 T: J или 6 дают стрит всем — у 2-3 это «играет борд», а не аут.
    res = analyze_hand(c("2s3d"), c("9h8c7dTs"))
    assert "Стрит" not in res["outs_to_improve"]


def test_analyze_preflop():
    res = analyze_hand(c("AsAd"), [])
    assert res["hand_class"] == "AA" and res["rank_of_169"] == 1


def test_outs_vs_set_exclude_board_pairing_cards():
    # Против сета спаривающая борд черва даёт оппоненту фулл-хаус: 8 аутов, а не 9.
    res = count_outs(c("AhKh"), hr("7c7d"), c("Qh7h2c"))
    assert res["outs"]["outs"] == 8
    assert "2h" not in res["outs"]["cards"]


def test_outs_when_ahead_lists_danger_cards():
    res = count_outs(c("QcQd"), hr("AhKh"), c("2h7hTc3s"))
    assert res["hero_ahead_now"] and res["danger_cards"]["outs"] == 15


def test_range_breakdown_counts_and_blockers():
    rng = hr("QQ+, AQ, KQs, 77, 22, T9s, J9s, A5s-A2s")
    res = range_breakdown(rng, c("Qh7h2c"), c("AhKh"))
    classes = {x["class"]: x["combos"] for x in res["classes"]}
    assert res["range_combos"] == 46
    assert classes["Сет"] == 9 and classes["Оверпара"] == 6 and classes["Топ-пара"] == 12
    assert res["vs_hero"]["combos_beating_hero"] == 29
    assert res["blocked_by_hero"]["combos"] == 13
    assert sum(classes.values()) == res["range_combos"]


def test_range_breakdown_preflop():
    res = range_breakdown(hr("QQ+, AKs"), [], None)
    assert res["range_combos"] == 22 and res["pairs_pct"] == pytest.approx(81.8, abs=0.1)
