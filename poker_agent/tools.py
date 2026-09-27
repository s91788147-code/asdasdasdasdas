"""Инструменты агента: JSON-схемы для Claude и их выполнение через poker_engine."""
from __future__ import annotations

import json
from typing import Any, Callable

from poker_engine import api

CARDS = "Карты: ранг (2-9, T, J, Q, K, A) + масть (s — пики, h — червы, d — бубны, c — трефы), например 'AhKh'."
RANGE = ("Диапазон в стандартной нотации: 'QQ+, AKs, AQo+, 99-66, A2s+, KTs+, JTs-54s, top15%', "
         "вес через двоеточие: 'AKo:0.5'. Конкретная рука — 'AhKh'.")
BOARD = "Борд: 0, 3, 4 или 5 карт подряд, например 'Qh7h2c'. Пустая строка — префлоп."


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


TOOLS: list[dict] = [
    _tool(
        "analyze_hand",
        "Разбор руки героя на текущей улице: комбинация и её класс (сет, топ-пара, оверпара...), дро "
        "(флеш-/стрит-дро, бэкдоры, оверкарты), ауты на улучшение и вероятность «доехать» к следующей "
        "карте и к риверу, сила руки против всех возможных рук и какие руки её бьют. На префлопе — место "
        "руки среди 169 стартовых и эквити против случайной руки. Вызывай в начале разбора любой руки и "
        "каждый раз, когда на борде появляется новая карта.",
        {
            "hand": {"type": "string", "description": "Две карты героя. " + CARDS},
            "board": {"type": "string", "description": BOARD},
        },
        ["hand"],
    ),
    _tool(
        "calculate_equity",
        "Эквити (доля банка к риверу) двух и более игроков. Каждый игрок — конкретная рука или диапазон; "
        "первый в списке — герой. Считает точным перебором, когда это быстро, иначе Монте-Карло (в ответе "
        "есть погрешность). Вызывай, когда нужно сравнить руку героя с диапазоном оппонента, решить, "
        "хватает ли эквити для колла, или оценить эквити при колле для полублефа.",
        {
            "players": {"type": "array", "items": {"type": "string"},
                        "description": "Руки/диапазоны игроков, первый — герой. " + RANGE},
            "board": {"type": "string", "description": BOARD},
            "dead": {"type": "string", "description": "Известные мёртвые карты (сброшенные/показанные), обычно пусто."},
            "iterations": {"type": "integer", "description": "Раздач для Монте-Карло (1000-200000), по умолчанию 30000."},
        },
        ["players"],
    ),
    _tool(
        "count_outs",
        "Ауты на следующую карту против конкретной руки или диапазона оппонента: какие карты выводят героя "
        "вперёд (а если герой уже впереди — какие карты для него опасны) и вероятность получить аут на "
        "следующей карте и к риверу, плюс оценка по правилу «4 и 2». Работает на флопе и терне. Вызывай "
        "на вопросы «сколько у меня аутов», «какой шанс доехать против его руки».",
        {
            "hand": {"type": "string", "description": "Две карты героя. " + CARDS},
            "villain": {"type": "string", "description": "Рука или диапазон оппонента. " + RANGE},
            "board": {"type": "string", "description": "Флоп (3 карты) или терн (4 карты)."},
        },
        ["hand", "villain", "board"],
    ),
    _tool(
        "range_breakdown",
        "Состав диапазона на борде: сколько комбинаций сетов, двух пар, топ-пар, дро, воздуха и доли групп "
        "«сильные/средние/слабые/дро/воздух». Если указана рука героя — сколько комбинаций бьют героя и "
        "проигрывают ему (на ривере это эквити колла) и какие комбинации рука героя блокирует. Главный "
        "инструмент для анализа блефа: какая часть линии оппонента — вэлью, а какая — блефы, и какая часть "
        "его диапазона сбросит на ставку героя. На префлопе — размер и состав диапазона.",
        {
            "range": {"type": "string", "description": RANGE},
            "board": {"type": "string", "description": BOARD},
            "hero_hand": {"type": "string", "description": "Рука героя для сравнения и блокеров (необязательно)."},
        },
        ["range"],
    ),
    _tool(
        "pot_odds",
        "Шансы банка для решения колл/фолд: сколько эквити нужно для безубыточного колла, EV колла при "
        "заданном эквити, сколько нужно дополнительно выиграть при попадании (implied odds), SPR после колла. "
        "pot — все фишки в банке сейчас, ВКЛЮЧАЯ ставку оппонента; to_call — сколько герою нужно доставить.",
        {
            "pot": {"type": "number", "description": "Банк сейчас, включая ставку/рейз оппонента."},
            "to_call": {"type": "number", "description": "Сколько нужно доставить для колла."},
            "equity_pct": {"type": "number", "description": "Эквити героя в процентах (0-100), если известно."},
            "effective_stack": {"type": "number", "description": "Эффективный стек до колла (необязательно)."},
        },
        ["pot", "to_call"],
    ),
    _tool(
        "bet_math",
        "Математика ставки или блефа с точки зрения ставящего: как часто оппонент должен сбрасывать, чтобы "
        "блеф окупился; MDF — минимальная частота защиты против этого сайзинга; сбалансированная доля "
        "блефов и соотношение вэлью:блеф; EV полублефа при заданной фолд-эквити и эквити при колле. "
        "Для анализа ставки оппонента подставляй его ставку как bet. pot — банк до ставки (при рейзе — "
        "включая ставку, которую рейзят); bet — размер ставки (при рейзе — «рейз до»).",
        {
            "pot": {"type": "number", "description": "Банк до этой ставки."},
            "bet": {"type": "number", "description": "Размер ставки (при рейзе — сумма «до»)."},
            "facing_bet": {"type": "number", "description": "Ставка оппонента, которую рейзят (0, если это первая ставка)."},
            "fold_equity_pct": {"type": "number", "description": "Как часто оппонент сбросит, % (для EV)."},
            "equity_when_called_pct": {"type": "number", "description": "Эквити ставящего при колле, % (для EV полублефа)."},
        },
        ["pot", "bet"],
    ),
]

_HANDLERS: dict[str, Callable[..., dict]] = {
    "analyze_hand": lambda hand, board="": api.analyze(hand, board),
    "calculate_equity": lambda players, board="", dead="", iterations=30_000: api.equity(
        players, board, dead, iterations),
    "count_outs": lambda hand, villain, board: api.outs(hand, villain, board),
    "range_breakdown": lambda range, board="", hero_hand="": api.breakdown(range, board, hero_hand),
    "pot_odds": lambda pot, to_call, equity_pct=None, effective_stack=None: api.pot_odds(
        pot, to_call, equity_pct, effective_stack),
    "bet_math": lambda pot, bet, facing_bet=0.0, fold_equity_pct=None, equity_when_called_pct=None: api.bet_math(
        pot, bet, facing_bet, fold_equity_pct, equity_when_called_pct),
}
_SCHEMAS = {t["name"]: t["input_schema"] for t in TOOLS}
_TYPES: dict[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer()),
    "array": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
}


def validate(name: str, args: Any) -> str | None:
    """Проверка входа по схеме. При потоковой передаче аргументов (eager_input_streaming)
    сервер их не валидирует, поэтому проверяем сами. Возвращает текст ошибки или None."""
    schema = _SCHEMAS.get(name)
    if schema is None:
        return f"Неизвестный инструмент {name!r}"
    if not isinstance(args, dict):
        return "Аргументы должны быть JSON-объектом"
    props = schema["properties"]
    for key in schema["required"]:
        if key not in args:
            return f"Не хватает обязательного параметра {key!r}"
    for key, value in args.items():
        if key not in props:
            return f"Неизвестный параметр {key!r}"
        if value is not None and not _TYPES[props[key]["type"]](value):
            return f"Параметр {key!r} должен иметь тип {props[key]['type']}"
    return None


def run_tool(name: str, args: Any) -> tuple[str, bool]:
    """Выполнить инструмент. Возвращает (текст результата, is_error)."""
    error = validate(name, args)
    if error:
        return json.dumps({"error": error, "received": args}, ensure_ascii=False, default=str), True
    try:
        result = _HANDLERS[name](**{k: v for k, v in args.items() if v is not None})
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False), True
    return json.dumps(result, ensure_ascii=False), False
