import json

import pytest

from poker_agent.tools import TOOLS, run_tool

VALID_CALLS = {
    "analyze_hand": {"hand": "AhKh", "board": "Qh7h2c"},
    "calculate_equity": {"players": ["AhKh", "QQ+, AKs"], "board": "Qh7h2c", "iterations": 2000},
    "count_outs": {"hand": "AhKh", "villain": "QcQd", "board": "Qh7h2c"},
    "range_breakdown": {"range": "QQ+, AQ", "board": "Qh7h2c", "hero_hand": "AhKh"},
    "pot_odds": {"pot": 150, "to_call": 50, "equity_pct": 35},
    "bet_math": {"pot": 100, "bet": 75, "fold_equity_pct": 40, "equity_when_called_pct": 30},
}


def test_every_tool_has_a_valid_example():
    assert {t["name"] for t in TOOLS} == set(VALID_CALLS)


@pytest.mark.parametrize("name", list(VALID_CALLS))
def test_valid_calls(name):
    content, is_error = run_tool(name, VALID_CALLS[name])
    assert not is_error, content
    assert isinstance(json.loads(content), dict)


@pytest.mark.parametrize("name, args, fragment", [
    ("analyze_hand", {}, "hand"),
    ("analyze_hand", {"hand": 123}, "string"),
    ("analyze_hand", {"hand": "AhKh", "extra": 1}, "extra"),
    ("analyze_hand", {"hand": "AhXx"}, "карта"),
    ("calculate_equity", {"players": "AhKh"}, "array"),
    ("pot_odds", {"pot": "100", "to_call": 50}, "number"),
    ("no_such_tool", {}, "no_such_tool"),
])
def test_errors_are_reported(name, args, fragment):
    content, is_error = run_tool(name, args)
    assert is_error
    assert fragment in json.loads(content)["error"]


def test_schemas_are_closed_objects():
    for tool in TOOLS:
        schema = tool["input_schema"]
        assert schema["type"] == "object" and schema["additionalProperties"] is False
        assert set(schema["required"]) <= set(schema["properties"])
