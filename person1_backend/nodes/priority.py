"""
PART 4 — Severity / Priority Cue Extraction.

Extracts evidence/cues only. Does NOT make an autonomous dispatch or triage decision —
Person 2's deterministic rules own the final priority.
"""
from __future__ import annotations

from typing import Optional

from clients.llm_client import LLMClient, load_prompt
from nodes.logger import log_call
from schemas.models import IncidentState

PROMPT_VERSION = "priority_cues_v1"


def extract_priority_cues(incident: IncidentState, client: Optional[LLMClient] = None) -> IncidentState:
    """
    Returns a NEW IncidentState with severity_cues / priority_features / priority_cues /
    uncertainty populated (merged onto the existing incident, never overwriting other fields).
    """
    client = client or LLMClient()
    template = load_prompt(f"{PROMPT_VERSION}.txt")
    prompt = template.replace("{{INCIDENT_STATE_JSON}}", incident.model_dump_json(indent=2))

    system = (
        "You extract priority-related cues only. You do not perform real medical triage "
        "and you do not make the final dispatch decision. This is a synthetic hackathon system."
    )

    result = client.complete_json(system_prompt=system, user_prompt=prompt, prompt_version=PROMPT_VERSION)

    log_call(
        model=result.model, prompt_version=PROMPT_VERSION,
        input_data=incident.model_dump(), output_data=result.parsed_json,
        latency_ms=result.latency_ms, input_tokens=result.input_tokens,
        output_tokens=result.output_tokens, error=result.error,
    )

    updated = incident.model_copy(deep=True)

    if result.error or result.parsed_json is None:
        # Fail safe: leave priority fields empty / max uncertainty rather than guessing.
        updated.uncertainty = max(updated.uncertainty, 0.8)
        return updated

    data = result.parsed_json
    updated.severity_cues = data.get("severity_cues", updated.severity_cues)
    updated.priority_features = data.get("priority_features", updated.priority_features)
    updated.priority_cues = data.get("priority_cues", updated.priority_cues)
    if "uncertainty" in data:
        updated.uncertainty = max(updated.uncertainty, float(data["uncertainty"]))
    return updated
