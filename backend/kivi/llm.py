"""Model adapter.

Three call sites in the product need a model. Both backends implement all
three with identical signatures, so the evaluation, the traces and the UI do
not change when you switch.

    local      deterministic, no network, no key. The default.
    anthropic  a hosted model, used when KIVI_LLM=anthropic and a key is set.

Every call returns a Usage record so cost and latency are measurable rather
than asserted.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from . import local_model as lm
from .config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, LLM_BACKEND

# USD per million tokens. Only used to price the anthropic backend.
PRICE_IN = 3.0
PRICE_OUT = 15.0


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    backend: str = "local"
    notes: list[str] = field(default_factory=list)

    def add(self, other: "Usage") -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cost_usd += other.cost_usd
        self.notes.extend(other.notes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls, "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens, "cost_usd": round(self.cost_usd, 6),
            "backend": self.backend,
        }


class LocalBackend:
    name = "local"

    def classify_intent(self, text: str) -> tuple[dict[str, Any], Usage]:
        intent, conf, scores = lm.classify_intent(text)
        return {"intent": intent, "confidence": conf, "scores": scores}, Usage(backend="local")

    def extract(self, record: dict[str, Any]) -> tuple[dict[str, Any], Usage]:
        cands, ignored = lm.extract(record)
        return {"candidates": [c.as_dict() for c in cands], "ignored": ignored}, Usage(backend="local")

    def reshape(self, text: str, rules: list[dict], instruction: str = "") -> tuple[dict[str, Any], Usage]:
        out, applied = lm.reshape(text, rules, instruction)
        return {"text": out, "applied": applied}, Usage(backend="local")


class AnthropicBackend:
    """Uses the Messages API over plain HTTP so the SDK is not a dependency."""

    name = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def _call(self, system: str, user: str, max_tokens: int = 900) -> tuple[str, Usage]:
        import requests  # imported here so the local backend needs nothing

        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        started = time.time()
        resp = requests.post(
            self.URL,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        u = data.get("usage", {})
        usage = Usage(
            calls=1,
            input_tokens=u.get("input_tokens", 0),
            output_tokens=u.get("output_tokens", 0),
            cost_usd=(u.get("input_tokens", 0) / 1e6) * PRICE_IN
            + (u.get("output_tokens", 0) / 1e6) * PRICE_OUT,
            backend="anthropic",
            notes=[f"{int((time.time() - started) * 1000)}ms"],
        )
        return text, usage

    @staticmethod
    def _json(text: str) -> Any:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            text = text[4:] if text.lower().startswith("json") else text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise

    def classify_intent(self, text: str) -> tuple[dict[str, Any], Usage]:
        system = (
            "Classify a spoken request to a voice layer into exactly one intent: "
            "find_dictation, reshape, recall, draft_message, remember, forget. "
            "Reply with only JSON: {\"intent\":...,\"confidence\":0..1,\"scores\":{intent:score}}. "
            "Set confidence below 0.3 if the request is ambiguous."
        )
        raw, usage = self._call(system, text, max_tokens=300)
        try:
            data = self._json(raw)
        except Exception:
            return LocalBackend().classify_intent(text)[0], usage
        return data, usage

    def extract(self, record: dict[str, Any]) -> tuple[dict[str, Any], Usage]:
        # Refusals stay deterministic. A model is not allowed to decide that a
        # password is safe to store.
        blocked = lm.sensitivity(record.get("raw_asr", "")) or lm.sensitivity(record.get("formatted", ""))
        if blocked or record.get("private"):
            return LocalBackend().extract(record)
        system = (
            "You decide what a voice product should remember about its user. "
            "Kinds: fact (a word/name spelling or expansion the user corrected), "
            "preference (a durable rule about how output should be written), "
            "episode (this dictation, recallable later). "
            "Never store the content of what the user said as a fact about the world. "
            "Reply only JSON: {\"candidates\":[{\"kind\",\"subject\",\"body\",\"confidence\",\"origin\",\"reason\",\"payload\",\"scope_app\"}],"
            "\"ignored\":[{\"what\",\"reason\"}]}"
        )
        raw, usage = self._call(system, json.dumps(record, ensure_ascii=False), max_tokens=1200)
        try:
            data = self._json(raw)
        except Exception:
            return LocalBackend().extract(record)[0], usage
        # Compile rule payloads locally so execution stays deterministic.
        for c in data.get("candidates", []):
            if c.get("kind") == "preference":
                c["payload"] = lm._compile_rule(c.get("body", ""))
        return data, usage

    def reshape(self, text: str, rules: list[dict], instruction: str = "") -> tuple[dict[str, Any], Usage]:
        rule_lines = "\n".join(f"- {r.get('source_text', json.dumps(r))}" for r in rules) or "- none"
        system = (
            "Rewrite the user's text. Obey the standing rules exactly. Change wording only as "
            "the rules and instruction require; never add facts. Reply only JSON: "
            "{\"text\":\"...\",\"applied\":[\"rule that changed something\"]}"
        )
        user = f"Standing rules:\n{rule_lines}\n\nInstruction: {instruction or '(none)'}\n\nText:\n{text}"
        raw, usage = self._call(system, user, max_tokens=1200)
        try:
            data = self._json(raw)
        except Exception:
            return LocalBackend().reshape(text, rules, instruction)[0], usage
        return data, usage


def get_backend(name: str | None = None):
    name = (name or LLM_BACKEND or "local").lower()
    if name == "anthropic":
        key = ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            return LocalBackend()
        return AnthropicBackend(key, ANTHROPIC_MODEL)
    return LocalBackend()
