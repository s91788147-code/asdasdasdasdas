"""CLI движка без LLM — удобно проверять расчёты руками.

  python -m poker_engine hand AhKh --board Qh7h2c
  python -m poker_engine equity AhKh "QQ+, AKs, 77" --board Qh7h2c
  python -m poker_engine outs AhKh QcQd --board Qh7h2c
  python -m poker_engine range "QQ+, AQ, KQs, T9s" --board Qh7h2c --hero AhKh
  python -m poker_engine odds --pot 150 --call 50 --equity 35
  python -m poker_engine bet --pot 100 --bet 75 --fold-equity 40 --equity 30
"""
from __future__ import annotations

import argparse
import json
import sys

from . import api


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m poker_engine", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("hand", help="разбор руки: комбинация, дро, ауты, сила")
    p.add_argument("hand")
    p.add_argument("--board", default="")

    p = sub.add_parser("equity", help="эквити героя против рук/диапазонов")
    p.add_argument("players", nargs="+", help="первый — герой; рука 'AhKh' или диапазон 'QQ+,AKs'")
    p.add_argument("--board", default="")
    p.add_argument("--dead", default="")
    p.add_argument("--iterations", type=int, default=30_000)

    p = sub.add_parser("outs", help="ауты против руки/диапазона (флоп, терн)")
    p.add_argument("hand")
    p.add_argument("villain")
    p.add_argument("--board", required=True)

    p = sub.add_parser("range", help="состав диапазона на борде, блокеры")
    p.add_argument("range")
    p.add_argument("--board", default="")
    p.add_argument("--hero", default="")

    p = sub.add_parser("odds", help="шансы банка для колла")
    p.add_argument("--pot", type=float, required=True, help="банк сейчас, включая ставку оппонента")
    p.add_argument("--call", type=float, required=True, help="сколько доставить")
    p.add_argument("--equity", type=float, help="эквити героя, %%")
    p.add_argument("--stack", type=float, help="эффективный стек")

    p = sub.add_parser("bet", help="математика ставки/блефа")
    p.add_argument("--pot", type=float, required=True, help="банк до ставки героя")
    p.add_argument("--bet", type=float, required=True)
    p.add_argument("--facing-bet", type=float, default=0.0, help="ставка оппонента, если герой рейзит")
    p.add_argument("--fold-equity", type=float, help="как часто оппонент сбросит, %%")
    p.add_argument("--equity", type=float, help="эквити героя при колле, %%")

    args = parser.parse_args(argv)
    try:
        if args.command == "hand":
            result = api.analyze(args.hand, args.board)
        elif args.command == "equity":
            if len(args.players) < 2:
                parser.error("нужны минимум два игрока")
            result = api.equity(args.players, args.board, args.dead, args.iterations)
        elif args.command == "outs":
            result = api.outs(args.hand, args.villain, args.board)
        elif args.command == "range":
            result = api.breakdown(args.range, args.board, args.hero)
        elif args.command == "odds":
            result = api.pot_odds(args.pot, args.call, args.equity, args.stack)
        else:
            result = api.bet_math(args.pot, args.bet, args.facing_bet, args.fold_equity, args.equity)
    except ValueError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
