"""
Records every LLM call (PART 9) to a JSONL log for auditability/debugging.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from schemas.models import LLMCallRecord

LOG_DIR = os.environ.get("LLM_LOG_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"))
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "llm_calls.jsonl")


def log_call(model: str, prompt_version: str, input_data: dict, output_data: dict | None,
             latency_ms: float | None, input_tokens: int | None = None,
             output_tokens: int | None = None, error: str | None = None) -> None:
    record = LLMCallRecord(
        model=model,
        prompt_version=prompt_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        input=input_data,
        output=output_data,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error=error,
    )
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")
