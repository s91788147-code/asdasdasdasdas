"""Покерный агент в терминале.

  python -m poker_agent "У меня AhKh на Qh7h2c, банк 100, оппонент ставит 50. Колл?"
  python -m poker_agent            # интерактивный режим с историей (уточняющие вопросы)

Нужен ключ API: export ANTHROPIC_API_KEY=...
"""
from __future__ import annotations

import argparse
import sys

import anthropic

from .agent import DEFAULT_MODEL, PokerAgent


def ask(agent: PokerAgent, question: str) -> bool:
    """Задать вопрос; при ошибке API напечатать понятное сообщение и вернуть False."""
    try:
        agent.ask(question)
        return True
    except TypeError as e:
        # SDK бросает TypeError, если не нашёл ни ключа, ни профиля `ant auth login`.
        if "authentication" not in str(e):
            raise
        message = "Не найдены учётные данные: задайте ANTHROPIC_API_KEY или выполните `ant auth login`."
    except anthropic.AuthenticationError:
        message = "Ошибка авторизации: проверьте ANTHROPIC_API_KEY."
    except anthropic.RateLimitError:
        message = "Превышен лимит запросов, попробуйте позже."
    except anthropic.APIStatusError as e:
        message = f"Ошибка API ({e.status_code}): {e.message}"
    except anthropic.APIConnectionError:
        message = "Нет соединения с API."
    print(message, file=sys.stderr)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m poker_agent", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", nargs="*", help="вопрос; без него — интерактивный режим")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("-v", "--verbose", action="store_true", help="печатать результаты инструментов")
    args = parser.parse_args(argv)

    agent = PokerAgent(model=args.model, effort=args.effort, verbose=args.verbose)
    if args.question:
        return 0 if ask(agent, " ".join(args.question)) else 1

    print("Покерный агент. Опиши раздачу или задай вопрос (пустая строка — выход).")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if not question:
            return 0
        ask(agent, question)


if __name__ == "__main__":
    sys.exit(main())
