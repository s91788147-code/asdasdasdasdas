import pytest

from poker_engine.cards import parse_cards
from poker_engine.equity import calc_equity
from poker_engine.ranges import parse_hand_or_range as hr


def eq(players, board="", **kw):
    return calc_equity([hr(p) for p in players], parse_cards(board), seed=42, **kw)


def test_turn_exact_fifteen_outs():
    # AhKh против QQ, терн: 9 червей + 3 туза + 3 короля = 15 аутов из 44 карт.
    res = eq(["AhKh", "QcQd"], "2h7hTc3s")
    assert res.exact
    assert res.equity[0] == pytest.approx(15 / 44)


def test_river_is_deterministic():
    res = eq(["AhAd", "KhKd"], "2c7s9dTh3c")
    assert res.exact and res.equity == [1.0, 0.0]


def test_split_pot():
    res = eq(["AhKd", "AsKc"], "2c7s9dTh3c")
    assert res.equity == [0.5, 0.5] and res.tie == [1.0, 1.0]


def test_preflop_classics():
    aa_kk = eq(["AhAs", "KdKc"], iterations=40_000)
    assert aa_kk.equity[0] == pytest.approx(0.82, abs=0.012)
    ak_qq = eq(["AhKd", "QsQc"], iterations=40_000)
    assert ak_qq.equity[0] == pytest.approx(0.4284, abs=0.012)  # точное значение 42.84%


def test_equities_sum_to_one_multiway():
    res = eq(["AhAs", "KdKc", "QQ, JJ"], iterations=5_000)
    assert sum(res.equity) == pytest.approx(1.0)
    assert res.equity[0] > res.equity[1]


def test_range_vs_range_symmetry():
    res = eq(["QQ+", "QQ+"], iterations=10_000)
    assert res.equity[0] == pytest.approx(0.5, abs=0.02)


def test_blocked_range_raises():
    with pytest.raises(ValueError):
        eq(["AhKh", "AA"], "AdAsAc")


def test_board_validation():
    with pytest.raises(ValueError):
        eq(["AhKh", "QQ"], "2c7s")
