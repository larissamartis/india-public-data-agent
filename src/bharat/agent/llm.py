"""One small client for free-tier LLMs that speak the OpenAI chat format (Gemini and Groq).

Every call asks for JSON at temperature 0 with a fixed model per provider. If the first
provider fails (no key, rate limit, server error, timeout or unreadable JSON), the next one
is tried and the fallback is recorded, so the evaluation can report how often it happened.
Tests use FakeLLM, which replays scripted replies and never touches the network.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    model: str
    key_env: str


PROVIDERS = (
    Provider(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
        "GEMINI_API_KEY",
    ),
    Provider(
        "groq",
        "https://api.groq.com/openai/v1",
        os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
        "GROQ_API_KEY",
    ),
)


class LLMError(RuntimeError):
    pass


@dataclass
class CallRecord:
    step: str
    provider: str
    seconds: float
    fallback: bool


@dataclass
class LLMBase:
    calls: list[CallRecord] = field(default_factory=list)

    def complete_json(self, step: str, system: str, user: str) -> dict:
        raise NotImplementedError


class OpenAICompatibleLLM(LLMBase):
    def __init__(
        self,
        providers: tuple[Provider, ...] = PROVIDERS,
        http: httpx.Client | None = None,
        timeout: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        """Free tiers limit requests per minute. LLM_MIN_INTERVAL spaces calls to each
        provider; LLM_RETRY_ROUNDS retries the whole provider list after a wait when every
        provider failed (for example all rate-limited)."""
        super().__init__()
        self.providers = providers
        self.http = http or httpx.Client(timeout=timeout)
        self.sleep = sleep
        self.min_interval = float(os.environ.get("LLM_MIN_INTERVAL", "0"))
        self.rounds = max(1, int(os.environ.get("LLM_RETRY_ROUNDS", "1")))
        self._last_call: dict[str, float] = {}

    def complete_json(self, step: str, system: str, user: str) -> dict:
        errors: list[str] = []
        for round_number in range(self.rounds):
            if round_number:
                self.sleep(20.0 * round_number)
            result = self._try_providers(step, system, user, errors)
            if result is not None:
                return result
        raise LLMError("; ".join(errors) or "no providers")

    def _try_providers(self, step: str, system: str, user: str, errors: list[str]) -> dict | None:
        for index, provider in enumerate(self.providers):
            key = os.environ.get(provider.key_env)
            if not key:
                errors.append(f"{provider.name}: no {provider.key_env}")
                continue
            wait = self.min_interval - (time.monotonic() - self._last_call.get(provider.name, -1e9))
            if wait > 0:
                self.sleep(wait)
            self._last_call[provider.name] = time.monotonic()
            started = time.monotonic()
            try:
                response = self.http.post(
                    f"{provider.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": provider.model,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    },
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                result = parse_json(content)
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
                errors.append(f"{provider.name}: {type(error).__name__}: {error}")
                log.warning("%s failed on %s: %s", provider.name, step, error)
                continue
            self.calls.append(
                CallRecord(step, provider.name, time.monotonic() - started, fallback=index > 0)
            )
            return result
        return None


def parse_json(text: str) -> dict:
    """Parse a JSON object, tolerating a ```json fence around it."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("{") :]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the reply")
    value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("the reply is not a JSON object")
    return value


class FakeLLM(LLMBase):
    """Replays replies for tests. `script` maps a step name to a list of replies (used in
    order) or to a function of the user prompt."""

    def __init__(self, script: dict[str, list[dict] | Callable[[str], dict]]):
        super().__init__()
        self.script = {k: (list(v) if isinstance(v, list) else v) for k, v in script.items()}
        self.prompts: list[tuple[str, str]] = []

    def complete_json(self, step: str, system: str, user: str) -> dict:
        self.prompts.append((step, user))
        entry = self.script.get(step)
        if entry is None:
            raise LLMError(f"fake LLM has no reply for step {step!r}")
        if callable(entry):
            reply = entry(user)
        elif entry:
            reply = entry.pop(0)
        else:
            raise LLMError(f"fake LLM ran out of replies for step {step!r}")
        self.calls.append(CallRecord(step, "fake", 0.0, fallback=False))
        return reply
