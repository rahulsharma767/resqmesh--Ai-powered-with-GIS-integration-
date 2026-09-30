"""
A fake LLMClient for tests, so the test suite runs without hitting a real API
or requiring LLM_API_KEY. Programmed with canned responses per prompt_version,
or a queue of responses for sequential calls.
"""
from __future__ import annotations

from typing import Callable, Optional, Union

from clients.llm_client import LLMCallResult


class FakeLLMClient:
    def __init__(self, responder: Union[Callable[[str, str, str], dict], dict, None] = None):
        """
        responder can be:
          - a dict mapping prompt_version -> parsed_json dict (static canned response)
          - a callable(system_prompt, user_prompt, prompt_version) -> dict
          - None (returns error results, to test fail-safe paths)
        """
        self.responder = responder
        self.calls = []
        self.model = "fake-model"

    def complete_json(self, system_prompt: str, user_prompt: str, prompt_version: str, max_tokens: int = 1500):
        self.calls.append((prompt_version, user_prompt))

        if self.responder is None:
            return LLMCallResult(
                raw_text="not json", parsed_json=None, model=self.model,
                prompt_version=prompt_version, latency_ms=1.0, error="simulated_failure",
            )

        if callable(self.responder):
            data = self.responder(system_prompt, user_prompt, prompt_version)
        else:
            data = self.responder.get(prompt_version)

        if data is None:
            return LLMCallResult(
                raw_text="{}", parsed_json=None, model=self.model,
                prompt_version=prompt_version, latency_ms=1.0, error="no_canned_response",
            )

        return LLMCallResult(
            raw_text="canned", parsed_json=data, model=self.model,
            prompt_version=prompt_version, latency_ms=1.0, input_tokens=10, output_tokens=10,
        )
