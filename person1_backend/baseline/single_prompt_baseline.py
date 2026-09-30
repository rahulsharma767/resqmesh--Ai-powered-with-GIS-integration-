"""
PART 10 — Single-Prompt Baseline.

For comparison ONLY. This intentionally violates the "LLM never dispatches" rule by
asking one big prompt to recommend ambulance/route/hospital directly. It exists so we
can show, empirically, why the staged ResQMesh pipeline (extraction -> deterministic
optimization -> adversarial review -> verification -> explanation) is safer and more
reliable than a single end-to-end LLM call.

DO NOT wire this into the real dispatch flow. It is an evaluation artifact.
"""
from __future__ import annotations

from typing import Optional

from clients.llm_client import LLMClient
from nodes.logger import log_call

PROMPT_VERSION = "single_prompt_baseline_v1"

BASELINE_SYSTEM = (
    "You are an emergency dispatch assistant. This is a synthetic hackathon exercise, "
    "not a real dispatch system. Analyze the emergency and recommend the ambulance, "
    "route, and hospital. Return ONLY valid JSON, no markdown fences, no commentary, "
    "matching this shape: "
    '{"recommended_ambulance": "...", "recommended_route": "...", '
    '"recommended_hospital": "...", "reasoning": "...", "confidence": 0.0}'
)


def run_baseline(raw_emergency_text: str, fleet_state: Optional[dict] = None,
                  hospital_state: Optional[dict] = None, client: Optional[LLMClient] = None) -> dict:
    """
    Single call, single prompt, no staged pipeline, no deterministic verification.
    Returns the raw parsed JSON (or an error dict) for direct comparison against
    the ResQMesh pipeline's final output.
    """
    client = client or LLMClient()

    context_bits = [f"Emergency report:\n{raw_emergency_text}"]
    if fleet_state is not None:
        context_bits.append(f"Available fleet state:\n{fleet_state}")
    if hospital_state is not None:
        context_bits.append(f"Available hospital state:\n{hospital_state}")
    user_prompt = "\n\n".join(context_bits)

    result = client.complete_json(system_prompt=BASELINE_SYSTEM, user_prompt=user_prompt,
                                   prompt_version=PROMPT_VERSION)

    log_call(
        model=result.model, prompt_version=PROMPT_VERSION,
        input_data={"raw_text": raw_emergency_text, "fleet_state": fleet_state, "hospital_state": hospital_state},
        output_data=result.parsed_json, latency_ms=result.latency_ms,
        input_tokens=result.input_tokens, output_tokens=result.output_tokens, error=result.error,
    )

    if result.error or result.parsed_json is None:
        return {"error": result.error or "invalid_json", "raw_text": result.raw_text}

    return result.parsed_json
