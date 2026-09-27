"""Цикл агента на поддельном клиенте: проверяем протокол tool use без обращения к API."""
import io
from types import SimpleNamespace as NS

from poker_agent.agent import PokerAgent


def text(t):
    return NS(type="text", text=t)


def tool(id_, name, args):
    return NS(type="tool_use", id=id_, name=name, input=args)


def message(stop_reason, *blocks):
    return NS(stop_reason=stop_reason, content=list(blocks))


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for block in self.msg.content:
            if block.type == "text":
                yield NS(type="text", text=block.text)

    def get_final_message(self):
        return self.msg


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = NS(messages=NS(stream=self._stream))

    def _stream(self, **params):
        self.calls.append({**params, "messages": list(params["messages"])})
        return FakeStream(self.responses.pop(0))


def make_agent(client, model="claude-opus-5"):
    return PokerAgent(client=client, model=model, out=io.StringIO(), log=io.StringIO())


def test_tool_round_trip():
    client = FakeClient(
        message("tool_use", text("Считаю. "),
                tool("t1", "analyze_hand", {"hand": "AhKh", "board": "Qh7h2c"}),
                tool("t2", "pot_odds", {"pot": 150, "to_call": 50})),
        message("end_turn", text("Колл.")),
    )
    agent = make_agent(client)
    answer = agent.ask("AhKh на Qh7h2c, банк 100, ставка 50. Колл?")

    assert answer == "Считаю. Колл."
    roles = [m["role"] for m in agent.messages]
    assert roles == ["user", "assistant", "user", "assistant"]
    results = agent.messages[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]  # все результаты — в одном сообщении
    assert not any(r.get("is_error") for r in results)
    assert '"required_equity_pct": 25.0' in results[1]["content"]
    # второй запрос уже содержит результаты инструментов
    assert len(client.calls[1]["messages"]) == 3


def test_invalid_tool_input_is_returned_as_error():
    client = FakeClient(
        message("tool_use", tool("t1", "analyze_hand", {"hand": "AhXx"})),
        message("end_turn", text("Исправил.")),
    )
    agent = make_agent(client)
    agent.ask("?")
    result = agent.messages[2]["content"][0]
    assert result["is_error"] is True


def test_refusal_rolls_back_history():
    client = FakeClient(message("refusal"))
    agent = make_agent(client)
    assert agent.ask("?") == ""
    assert agent.messages == []


def test_fallbacks_only_for_supported_models():
    client = FakeClient(message("end_turn", text("ok")), message("end_turn", text("ok")))
    make_agent(client).ask("?")
    make_agent(client, model="claude-sonnet-5").ask("?")
    assert client.calls[0]["fallbacks"] == "default"
    assert "fallbacks" not in client.calls[1] and "betas" not in client.calls[1]
    assert client.calls[0]["thinking"] == {"type": "adaptive"}
