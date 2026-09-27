import pytest

from poker_engine.odds import bet_math, pot_odds


def test_pot_odds_half_pot_bet():
    # Банк 100, ставка 50: в банке 150, доставить 50 -> нужно 25% эквити.
    res = pot_odds(150, 50, equity_pct=35)
    assert res["required_equity_pct"] == 25.0
    assert res["ev_call"] == pytest.approx(0.35 * 200 - 50)


def test_implied_odds_needed():
    res = pot_odds(150, 50, equity_pct=20)
    # EV(колл) = 0.2*(150+X) - 0.8*50 >= 0  ->  X >= 50
    assert res["implied_odds_needed"] == pytest.approx(50)


@pytest.mark.parametrize("bet, alpha, mdf, bluffs", [
    (50, 33.33, 66.67, 25.0),     # полбанка
    (100, 50.0, 50.0, 33.33),     # банк
    (200, 66.67, 33.33, 40.0),    # овербет 2x
])
def test_bet_math_standard_sizings(bet, alpha, mdf, bluffs):
    res = bet_math(100, bet)
    assert res["bluff_breakeven_fold_pct"] == alpha
    assert res["mdf_pct"] == mdf
    assert res["optimal_bluff_share_pct"] == bluffs


def test_semi_bluff_ev_and_breakeven():
    res = bet_math(100, 75, fold_equity_pct=40, equity_when_called_pct=30)
    assert res["ev_bet"] == pytest.approx(0.4 * 100 + 0.6 * (0.3 * 250 - 75))
    res = bet_math(100, 100, fold_equity_pct=0, equity_when_called_pct=0)
    assert res["breakeven_fold_equity_pct"] == 50.0


def test_raise_math():
    # Банк 100, оппонент ставит 50 (в банке 150), герой рейзит до 150: оппоненту доставлять 100.
    res = bet_math(150, 150, facing_bet=50)
    assert res["villain_required_equity_to_call_pct"] == pytest.approx(100 / 400 * 100)


def test_validation():
    with pytest.raises(ValueError):
        pot_odds(0, 10)
    with pytest.raises(ValueError):
        bet_math(100, 50, facing_bet=60)
