"""Математика ставок: шансы банка, EV колла, MDF, безубыточность блефа, доля блефов.

Во всех функциях pot — все фишки в банке в момент решения, ДО того как игрок что-то
добавит (ставка/рейз оппонента, если она была, уже включена в pot).
"""
from __future__ import annotations


def _pct(x: float) -> float:
    return round(100 * x, 2)


def _positive(name: str, value: float) -> None:
    if value is None or value <= 0:
        raise ValueError(f"{name} должен быть положительным числом")


def pot_odds(pot: float, to_call: float, equity_pct: float | None = None,
             effective_stack: float | None = None) -> dict:
    """Решение «колл или фолд» с точки зрения отвечающего игрока."""
    _positive("pot", pot)
    _positive("to_call", to_call)
    required = to_call / (pot + to_call)
    result: dict = {
        "required_equity_pct": _pct(required),
        "pot_odds": f"{pot / to_call:.2f} : 1",
        "formula": f"to_call / (pot + to_call) = {to_call:g} / ({pot:g} + {to_call:g}) = {_pct(required)}%",
    }
    if equity_pct is not None:
        if not 0 <= equity_pct <= 100:
            raise ValueError("equity_pct задаётся в процентах от 0 до 100")
        eq = equity_pct / 100
        ev = eq * (pot + to_call) - to_call
        result["ev_call"] = round(ev, 2)
        result["ev_formula"] = (f"equity * (pot + to_call) - to_call = {eq:.4f} * {pot + to_call:g} "
                                f"- {to_call:g} = {ev:.2f}")
        result["decision_by_pot_odds"] = "колл выгоден" if ev >= 0 else "колл невыгоден"
        if ev < 0 and eq > 0:
            # Сколько нужно дополнительно выиграть на следующих улицах при попадании (implied odds).
            result["implied_odds_needed"] = round(to_call * (1 - eq) / eq - pot, 2)
    if effective_stack is not None:
        _positive("effective_stack", effective_stack)
        behind = effective_stack - to_call
        result["stack_behind_after_call"] = round(max(behind, 0), 2)
        result["spr_after_call"] = round(max(behind, 0) / (pot + to_call), 2)
    result["note"] = ("Сравнение с шансами банка точно, когда дальше ставок не будет (ривер или олл-ин). "
                      "На флопе/терне учитывай implied odds (дополнительный выигрыш при попадании) "
                      "и reverse implied odds (проигрыш, когда доехал, но всё равно хуже).")
    return result


def bet_math(pot: float, bet: float, facing_bet: float = 0.0, fold_equity_pct: float | None = None,
             equity_when_called_pct: float | None = None) -> dict:
    """Ставка/рейз с точки зрения агрессора: блеф, MDF, доля блефов, EV полублефа.

    bet — сколько фишек игрок вносит сейчас (при рейзе — размер рейза «до»),
    facing_bet — ставка оппонента, которую игрок рейзит (0, если это первая ставка).
    """
    _positive("pot", pot)
    _positive("bet", bet)
    if facing_bet < 0 or facing_bet >= bet:
        raise ValueError("facing_bet должен быть неотрицательным и меньше bet")
    villain_call = bet - facing_bet
    final_pot = pot + bet + villain_call
    alpha = bet / (pot + bet)
    villain_required = villain_call / final_pot
    result: dict = {
        "bet_size_pct_of_pot": _pct(bet / pot),
        "bluff_breakeven_fold_pct": _pct(alpha),
        "bluff_breakeven_formula": f"bet / (pot + bet) = {bet:g} / ({pot:g} + {bet:g}) = {_pct(alpha)}%",
        "mdf_pct": _pct(1 - alpha),
        "villain_required_equity_to_call_pct": _pct(villain_required),
        "optimal_bluff_share_pct": _pct(villain_required),
        "value_to_bluff_ratio": f"{(1 - villain_required) / villain_required:.2f} : 1",
        "explanation": (
            "bluff_breakeven_fold_pct — как часто оппонент должен сбрасывать, чтобы чистый блеф был в ноль. "
            "mdf_pct — минимальная доля диапазона, которой оппонент должен продолжать, чтобы блеф "
            "игрока не был прибыльным автоматически. optimal_bluff_share_pct — доля блефов в "
            "поляризованном диапазоне ставки на ривере, при которой оппоненту всё равно, коллировать или нет; "
            "value_to_bluff_ratio — соответствующее соотношение вэлью к блефам."),
    }
    if fold_equity_pct is not None:
        if not 0 <= fold_equity_pct <= 100:
            raise ValueError("fold_equity_pct задаётся в процентах от 0 до 100")
        fe = fold_equity_pct / 100
        eq = (equity_when_called_pct or 0.0) / 100
        ev_called = eq * final_pot - bet
        ev = fe * pot + (1 - fe) * ev_called
        result["ev_bet"] = round(ev, 2)
        result["ev_formula"] = (f"FE * pot + (1 - FE) * (equity * final_pot - bet) = {fe:.3f} * {pot:g} + "
                                f"{1 - fe:.3f} * ({eq:.3f} * {final_pot:g} - {bet:g}) = {ev:.2f}")
        result["ev_when_called"] = round(ev_called, 2)
        if ev_called < 0:
            result["breakeven_fold_equity_pct"] = _pct(-ev_called / (pot - ev_called))
        result["note"] = "Модель без ререйза оппонента: он либо сбрасывает, либо коллирует."
    return result
