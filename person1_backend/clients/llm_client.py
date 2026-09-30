"""
Reusable LLM client for ResQMesh (Person 1's AI/LLM workflow).

- Provider/model are configured via environment variables (never hardcoded).
- Every call is retried on transient failure, validated as JSON, and logged
  with model/prompt_version/timestamp/latency/token usage (PART 9).
- Fails SAFE: if the LLM cannot produce valid JSON after retries, callers get
  a clearly-flagged error result instead of a silent guess (PART 13).
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")  # "anthropic" or "gemini"
# Default model depends on provider: Anthropic needs a paid key; Gemini has a free tier.
_DEFAULT_MODELS = {"anthropic": "claude-sonnet-4-6", "gemini": "gemini-2.5-flash"}
LLM_MODEL = os.environ.get("LLM_MODEL") or _DEFAULT_MODELS.get(LLM_PROVIDER, "claude-sonnet-4-6")
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "2"))
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "30"))

# PERSON1_MODE=mock (the default) never makes an outbound LLM call — it uses
# clients/mock_client.py's deterministic heuristics instead. This exists so
# development/demos don't burn the Gemini free-tier quota
# (GenerateRequestsPerDayPerProjectPerModel-FreeTier) and so the frontend keeps
# working even when no LLM_API_KEY is configured at all. Set PERSON1_MODE=real
# (with LLM_API_KEY set) to call the actual provider.
PERSON1_MODE = os.environ.get("PERSON1_MODE", "mock").lower()


class LLMError(Exception):
    """Raised when the LLM call fails safely after retries."""


@dataclass
class LLMCallResult:
    raw_text: str
    parsed_json: Optional[dict]
    model: str
    prompt_version: str
    latency_ms: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    attempts: int = 1
    error: Optional[str] = None


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json(text: str) -> dict:
    """Best-effort extraction of a JSON object from model output."""
    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fallback: grab the first {...} block (handles stray preamble text)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No valid JSON object found in model output")


class LLMClient:
    """
    Thin wrapper so the rest of the pipeline never talks to a specific SDK directly.
    Swap providers by setting LLM_PROVIDER=anthropic or LLM_PROVIDER=gemini in .env
    (Gemini has a free, no-credit-card tier via Google AI Studio — good for hackathons
    that don't want to spend money on Anthropic credits).
    """

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None,
                 provider: Optional[str] = None, mode: Optional[str] = None):
        self.provider = (provider or LLM_PROVIDER).lower()
        self.model = model or LLM_MODEL
        self.api_key = api_key or LLM_API_KEY
        self.mode = (mode or PERSON1_MODE).lower()
        self._client = None

    # ---- Anthropic ----
    def _get_anthropic_client(self):
        if self._client is None:
            import anthropic  # imported lazily so tests can run without the package installed
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _call_anthropic(self, system: str, user: str, max_tokens: int) -> tuple[str, Optional[int], Optional[int]]:
        client = self._get_anthropic_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text_parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        text = "\n".join(text_parts)
        usage = getattr(response, "usage", None)
        in_tok = getattr(usage, "input_tokens", None) if usage else None
        out_tok = getattr(usage, "output_tokens", None) if usage else None
        return text, in_tok, out_tok

    # ---- Google Gemini (free tier via Google AI Studio, no credit card needed) ----
    def _call_gemini(self, system: str, user: str, max_tokens: int) -> tuple[str, Optional[int], Optional[int]]:
        import requests  # imported lazily so tests/anthropic-only setups don't need it

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
        response = requests.post(
            url,
            params={"key": self.api_key},
            json=payload,
            timeout=LLM_TIMEOUT_S,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Gemini API error {response.status_code}: {response.text}")

        data = response.json()
        try:
            text = "".join(
                part.get("text", "")
                for part in data["candidates"][0]["content"]["parts"]
            )
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Unexpected Gemini response shape: {data}") from e

        usage = data.get("usageMetadata", {})
        in_tok = usage.get("promptTokenCount")
        out_tok = usage.get("candidatesTokenCount")
        return text, in_tok, out_tok

    def _call_provider(self, system: str, user: str, max_tokens: int) -> tuple[str, Optional[int], Optional[int]]:
        if self.provider == "gemini":
            return self._call_gemini(system, user, max_tokens)
        return self._call_anthropic(system, user, max_tokens)

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        prompt_version: str,
        max_tokens: int = 1500,
    ) -> LLMCallResult:
        """
        Calls the LLM expecting a strict JSON response. Retries on transient errors
        or invalid JSON. Never raises for a "bad but recoverable" result — instead
        returns an LLMCallResult with parsed_json=None and .error set, so callers
        can fail safely (PART 13).
        """
        if self.mode == "mock":
            # No network call at all — deterministic offline heuristic instead.
            from clients.mock_client import mock_complete  # lazy: avoid import cost when unused
            start = time.time()
            data = mock_complete(user_prompt, prompt_version)
            latency_ms = (time.time() - start) * 1000
            if data is None:
                return LLMCallResult(
                    raw_text="", parsed_json=None, model="mock-heuristic",
                    prompt_version=prompt_version, latency_ms=latency_ms,
                    attempts=1, error=f"no_mock_handler_for:{prompt_version}",
                )
            return LLMCallResult(
                raw_text=json.dumps(data), parsed_json=data, model="mock-heuristic",
                prompt_version=prompt_version, latency_ms=latency_ms, attempts=1, error=None,
            )

        last_error = None
        attempts = 0
        for attempt in range(1, LLM_MAX_RETRIES + 2):
            attempts = attempt
            start = time.time()
            try:
                text, in_tok, out_tok = self._call_provider(system_prompt, user_prompt, max_tokens)
                latency_ms = (time.time() - start) * 1000
                try:
                    parsed = _extract_json(text)
                except (json.JSONDecodeError, ValueError) as e:
                    last_error = f"invalid_json: {e}"
                    if attempt <= LLM_MAX_RETRIES:
                        # ask again more strictly next loop iteration
                        user_prompt = user_prompt + "\n\nYour previous response was not valid JSON. Return ONLY a valid JSON object, nothing else."
                        continue
                    return LLMCallResult(
                        raw_text=text, parsed_json=None, model=self.model,
                        prompt_version=prompt_version, latency_ms=latency_ms,
                        input_tokens=in_tok, output_tokens=out_tok,
                        attempts=attempts, error=last_error,
                    )
                return LLMCallResult(
                    raw_text=text, parsed_json=parsed, model=self.model,
                    prompt_version=prompt_version, latency_ms=latency_ms,
                    input_tokens=in_tok, output_tokens=out_tok,
                    attempts=attempts, error=None,
                )
            except Exception as e:  # network/timeout/provider errors
                last_error = f"provider_error: {e}"
                latency_ms = (time.time() - start) * 1000
                if attempt <= LLM_MAX_RETRIES:
                    time.sleep(min(2 ** attempt, 5))
                    continue
                return LLMCallResult(
                    raw_text="", parsed_json=None, model=self.model,
                    prompt_version=prompt_version, latency_ms=latency_ms,
                    attempts=attempts, error=last_error,
                )
        # Should not reach here, but fail safe just in case
        return LLMCallResult(
            raw_text="", parsed_json=None, model=self.model,
            prompt_version=prompt_version, latency_ms=0.0,
            attempts=attempts, error=last_error or "unknown_error",
        )


def load_prompt(name: str) -> str:
    """Loads a prompt template from the prompts/ directory."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base_dir, "prompts", name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
