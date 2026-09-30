"""
PART 6 — Adversarial Reviewer.

Receives Person 2's proposed plan + supporting state, and tries to find a flaw.
NEVER replaces the plan — only raises a ReviewResult challenge for Person 2's
deterministic verifier to act on.
"""
from __future__ import annotations

from typing import Optional

from clients.llm_client import LLMClient, load_prompt
from nodes.logger import log_call
from schemas.models import IncidentState, ReviewRequest, ReviewResult

PROMPT_VERSION = "adversarial_reviewer_v1"


def review_plan(
    incident: IncidentState,
    fleet_state: dict,
    road_state: dict,
    hospital_state: dict,
    proposed_plan: dict,
    client: Optional[LLMClient] = None,
) -> ReviewResult:
    client = client or LLMClient()
    request = ReviewRequest(
        incident=incident, fleet_state=fleet_state, road_state=road_state,
        hospital_state=hospital_state, proposed_plan=proposed_plan,
    )

    template = load_prompt(f"{PROMPT_VERSION}.txt")
    prompt = template.replace("{{REVIEW_REQUEST_JSON}}", request.model_dump_json(indent=2))

    system = (
        "You are an independent, skeptical safety reviewer. You only report challenges; "
        "you never repair or replace the plan yourself."
    )

    result = client.complete_json(system_prompt=system, user_prompt=prompt, prompt_version=PROMPT_VERSION)

    log_call(
        model=result.model, prompt_version=PROMPT_VERSION,
        input_data=request.model_dump(), output_data=result.parsed_json,
        latency_ms=result.latency_ms, input_tokens=result.input_tokens,
        output_tokens=result.output_tokens, error=result.error,
    )

    if result.error or result.parsed_json is None:
        # Fail safe: if the reviewer itself fails, surface that as a HIGH-severity
        # challenge so Person 2's verifier does NOT treat silence as "plan is fine".
        return ReviewResult(
            challenge_found=True,
            evidence="Adversarial reviewer LLM call failed or returned invalid output.",
            affected_constraint="review_process_integrity",
            severity="HIGH",
            recommended_recheck="Manual review required; automated adversarial review unavailable.",
        )

    try:
        return ReviewResult(**result.parsed_json)
    except Exception:
        return ReviewResult(
            challenge_found=True,
            evidence="Adversarial reviewer output failed schema validation.",
            affected_constraint="review_process_integrity",
            severity="HIGH",
            recommended_recheck="Manual review required; automated adversarial review output was malformed.",
        )
