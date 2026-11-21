"""Provider-agnostic LLM client returning validated JSON.

Supported providers (pick with LLM_PROVIDER in .env):
  gemini             Google Gemini API (has a free tier)
  anthropic          Anthropic Messages API
  openai             OpenAI Chat Completions
  openai_compatible  Any OpenAI-compatible endpoint (Ollama, Groq, OpenRouter, LM Studio...)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger("rota.llm")
T = TypeVar("T", bound=BaseModel)

DEFAULT_MODELS = {
    "gemini": "gemini-3.8-flash",
    "anthropic": "claude-haiku-5-5",
    "openai": "gpt-5-mini",
    "openai_compatible": "qwen3:8b",
}
KEY_ENV = {
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai_compatible": "LLM_API_KEY",
}


class LLMError(RuntimeError):
    pass


class LLMNotConfigured(LLMError):
    pass


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key: str
    base_url: str = ""
    min_interval: float = 0.0
    timeout: float = 120.0


def config_from_env() -> LLMConfig:
    provider = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()
    if provider not in DEFAULT_MODELS:
        raise LLMNotConfigured(f"Unknown LLM_PROVIDER '{provider}'. Use one of: {', '.join(DEFAULT_MODELS)}")
    key = os.environ.get(KEY_ENV[provider], "").strip()
    if not key and provider != "openai_compatible":
        raise LLMNotConfigured(
            f"No API key: set {KEY_ENV[provider]} in .env (LLM_PROVIDER={provider})."
        )
    default_interval = "4" if provider == "gemini" else "0"
    return LLMConfig(
        provider=provider,
        model=os.environ.get("LLM_MODEL", "").strip() or DEFAULT_MODELS[provider],
        api_key=key or "none",
        base_url=os.environ.get("LLM_BASE_URL", "").strip(),
        min_interval=float(os.environ.get("LLM_MIN_INTERVAL", default_interval)),
    )


# ----------------------------------------------------------------------------- providers
class Provider:
    def __init__(self, cfg: LLMConfig, transport: httpx.BaseTransport | None = None):
        self.cfg = cfg
        self.http = httpx.Client(timeout=cfg.timeout, transport=transport)

    def complete(self, system: str, user: str, max_tokens: int = 8192) -> str:
        raise NotImplementedError

    def _post_tolerant(self, url: str, headers: dict, body: dict, temp_path: tuple[str, ...]) -> dict:
        """Some newer models reject a custom temperature: retry once without it."""
        try:
            return self._post(url, headers, body)
        except LLMError as e:
            if "temperature" not in str(e).lower():
                raise
            node = body
            for k in temp_path[:-1]:
                node = node.get(k, {})
            node.pop(temp_path[-1], None)
            return self._post(url, headers, body)

    def _post(self, url: str, headers: dict, body: dict) -> dict:
        for attempt in range(5):
            try:
                r = self.http.post(url, headers=headers, json=body)
            except httpx.TransportError as e:
                log.warning("LLM network error (%s), retry %d", e, attempt + 1)
                time.sleep(2 ** attempt)
                continue
            if r.status_code in (429, 500, 502, 503, 504, 529):
                wait = float(r.headers.get("retry-after", 0) or 2 ** (attempt + 2))
                log.warning("LLM HTTP %s, waiting %.0fs", r.status_code, wait)
                time.sleep(min(wait, 90))
                continue
            if r.status_code >= 400:
                raise LLMError(f"{self.cfg.provider} HTTP {r.status_code}: {r.text[:500]}")
            return r.json()
        raise LLMError(f"{self.cfg.provider}: too many retries")


class Gemini(Provider):
    def complete(self, system, user, max_tokens=8192):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.cfg.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0,
                                 "maxOutputTokens": max_tokens},
        }
        data = self._post_tolerant(url, {"x-goog-api-key": self.cfg.api_key}, body, ("generationConfig", "temperature"))
        try:
            cand = data["candidates"][0]
            parts = cand["content"]["parts"]
        except (KeyError, IndexError):
            raise LLMError(f"gemini: unexpected response {str(data)[:300]}")
        if cand.get("finishReason") == "MAX_TOKENS":
            log.warning("gemini: output hit max tokens; the JSON may be truncated")
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))


class Anthropic(Provider):
    def complete(self, system, user, max_tokens=8192):
        body = {"model": self.cfg.model, "max_tokens": max_tokens, "system": system,
                "messages": [{"role": "user", "content": user}], "temperature": 0}
        data = self._post_tolerant("https://api.anthropic.com/v1/messages",
                                   {"x-api-key": self.cfg.api_key, "anthropic-version": "2023-06-01"}, body,
                                   ("temperature",))
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


class OpenAICompatible(Provider):
    def complete(self, system, user, max_tokens=8192):
        base = (self.cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        body: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        if self.cfg.provider == "openai_compatible":
            body["temperature"] = 0  # some OpenAI reasoning models reject non-default temperature
        data = self._post_tolerant(f"{base}/chat/completions", {"Authorization": f"Bearer {self.cfg.api_key}"},
                                   body, ("temperature",))
        return data["choices"][0]["message"].get("content") or ""


PROVIDERS = {"gemini": Gemini, "anthropic": Anthropic, "openai": OpenAICompatible,
             "openai_compatible": OpenAICompatible}


# ----------------------------------------------------------------------------- JSON client
def parse_json_loose(text: str) -> Any:
    """Parse JSON even if wrapped in ```json fences or surrounded by prose."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            return json.loads(t[start : end + 1])
        raise


class LLMClient:
    """complete_model(): call the provider, parse + validate JSON, cache by content."""

    def __init__(self, provider: Provider, cache_get: Optional[Callable[[str], Optional[str]]] = None,
                 cache_put: Optional[Callable[[str, str], None]] = None):
        self.provider = provider
        self.cache_get, self.cache_put = cache_get, cache_put
        self._last_call = 0.0
        self.calls = 0
        self.cache_hits = 0

    @property
    def model_id(self) -> str:
        return f"{self.provider.cfg.provider}/{self.provider.cfg.model}"

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last_call
        if gap < self.provider.cfg.min_interval:
            time.sleep(self.provider.cfg.min_interval - gap)
        self._last_call = time.monotonic()

    def complete_model(self, system: str, user: str, schema: type[T], *, cache_tag: str = "",
                       max_tokens: int = 8192) -> T:
        key = hashlib.sha256(f"{self.model_id}|{cache_tag}|{system}|{user}".encode()).hexdigest()
        if self.cache_get:
            hit = self.cache_get(key)
            if hit:
                try:
                    self.cache_hits += 1
                    return schema.model_validate(json.loads(hit))
                except (ValidationError, json.JSONDecodeError):
                    pass
        prompt = user
        last_err: Exception | None = None
        for _ in range(2):
            self._throttle()
            self.calls += 1
            raw = self.provider.complete(system, prompt, max_tokens=max_tokens)
            try:
                obj = schema.model_validate(parse_json_loose(raw))
                if self.cache_put:
                    self.cache_put(key, obj.model_dump_json())
                return obj
            except (ValidationError, json.JSONDecodeError, ValueError) as e:
                last_err = e
                prompt = (f"{user}\n\nYour previous answer was not valid JSON for the schema "
                          f"({str(e)[:300]}). Answer again with ONLY the JSON object.")
        raise LLMError(f"Invalid JSON from model after retry: {last_err}")


def make_client(db=None, transport: httpx.BaseTransport | None = None, cfg: LLMConfig | None = None) -> LLMClient:
    cfg = cfg or config_from_env()
    provider = PROVIDERS[cfg.provider](cfg, transport=transport)
    if db is not None:
        return LLMClient(provider, db.cache_get, db.cache_put)
    return LLMClient(provider)
