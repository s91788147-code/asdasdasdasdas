"""Покерный агент: Claude рассуждает, движок poker_engine считает (tool use)."""
from __future__ import annotations

import json
import os
import sys
from typing import TextIO

import anthropic

from .prompts import SYSTEM_PROMPT
from .tools import TOOLS, run_tool

DEFAULT_MODEL = os.environ.get("POKER_AGENT_MODEL", "claude-opus-5")
# Модели, для которых включаем серверный fallback при отказе классификаторов безопасности.
FALLBACK_MODELS = {"claude-opus-5", "claude-fable-5-1"}
MAX_STEPS = 25


class PokerAgent:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = DEFAULT_MODEL,
                 effort: str = "high", verbose: bool = False,
                 out: TextIO = sys.stdout, log: TextIO = sys.stderr):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.verbose = verbose
        self.out = out
        self.log = log
        self.messages: list[dict] = []  # история диалога — для уточняющих вопросов

    def _request_params(self) -> dict:
        params: dict = {
            "model": self.model,
            "max_tokens": 64_000,
            "system": SYSTEM_PROMPT,
            "tools": TOOLS,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.effort},
            "cache_control": {"type": "ephemeral"},
            "messages": self.messages,
        }
        if self.model in FALLBACK_MODELS:
            params["betas"] = ["server-side-fallback-2026-07-01"]
            params["fallbacks"] = "default"
        return params

    def ask(self, question: str) -> str:
        """Задать вопрос; ответ печатается потоково в self.out и возвращается строкой."""
        start = len(self.messages)
        self.messages.append({"role": "user", "content": question})
        texts: list[str] = []
        json_retries = 0
        for _ in range(MAX_STEPS):
            try:
                with self.client.beta.messages.stream(**self._request_params()) as stream:
                    for event in stream:
                        if event.type == "text":
                            self.out.write(event.text)
                            self.out.flush()
                    response = stream.get_final_message()
            except ValueError:
                # SDK не смог разобрать JSON аргументов инструмента (потоковая передача):
                # tool_use_id ещё нет, поэтому просто повторяем ход.
                json_retries += 1
                if json_retries > 2:
                    raise
                continue
            json_retries = 0

            if response.stop_reason == "refusal":
                del self.messages[start:]  # частичный ответ не сохраняем в истории
                self.out.write("\n[Модель отказалась отвечать на этот запрос.]\n")
                return ""

            self.messages.append({"role": "assistant", "content": response.content})
            texts += [b.text for b in response.content if b.type == "text"]
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                self.out.write("\n")
                return "".join(texts)
            if response.stop_reason == "max_tokens":
                raise RuntimeError("Ответ обрезан по max_tokens посреди вызова инструмента")

            results = []
            for block in tool_uses:
                content, is_error = run_tool(block.name, block.input)
                self._log_call(block.name, block.input, content, is_error)
                result = {"type": "tool_result", "tool_use_id": block.id, "content": content}
                if is_error:
                    result["is_error"] = True
                results.append(result)
            self.messages.append({"role": "user", "content": results})
        raise RuntimeError(f"Агент не закончил за {MAX_STEPS} шагов")

    def _log_call(self, name: str, args, content: str, is_error: bool) -> None:
        shown = ", ".join(f"{k}={v!r}" for k, v in args.items()) if isinstance(args, dict) else repr(args)
        mark = "✗" if is_error else "⚙"
        print(f"\n  {mark} {name}({shown})", file=self.log, flush=True)
        if self.verbose or is_error:
            print("    " + json.dumps(json.loads(content), ensure_ascii=False, indent=2).replace("\n", "\n    "),
                  file=self.log, flush=True)
