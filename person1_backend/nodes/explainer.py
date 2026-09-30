"""
PART 7 — Explanation Generator.

Produces a short, dispatcher-readable explanation from ALREADY-VERIFIED facts.
Never adds medical facts that aren't present in the input.
"""
from __future__ import annotations

from typing import Optional

from clients.llm_client import LLMClient, load_prompt
from nodes.logger import log_call
from schemas.models import Explanation

PROMPT_VERSION = "explanation_generator_v1"


def generate_explanation(
    verified_facts: dict,
    assignment: dict,
    route: dict,
    hospital: dict,
    uncertainty: float,
    what_changed: Optional[str] = None,
    client: Optional[LLMClient] = None,
) -> Explanation:
    client = client or LLMClient()

    payload = {
        "verified_facts": verified_facts,
        "assignment": assignment,
        "route": route,
        "hospital": hospital,
        "uncertainty": uncertainty,
        "what_changed": what_changed,
    }

    template = load_prompt(f"{PROMPT_VERSION}.txt")
    import json
    prompt = template.replace("{{EXPLANATION_INPUT_JSON}}", json.dumps(payload, indent=2))

    system = (
        "You explain an already-verified emergency response plan to a dispatcher, briefly "
        "and only using the facts given. You never invent medical facts."
    )

    result = client.complete_json(system_prompt=system, user_prompt=prompt, prompt_version=PROMPT_VERSION)

    log_call(
        model=result.model, prompt_version=PROMPT_VERSION,
        input_data=payload, output_data=result.parsed_json,
        latency_ms=result.latency_ms, input_tokens=result.input_tokens,
        output_tokens=result.output_tokens, error=result.error,
    )

    if result.error or result.parsed_json is None:
        # Fail safe: return a minimal, honest explanation instead of inventing prose.
        return Explanation(
            what_we_know="Explanation generation failed. Refer to the verified plan data directly.",
            why_this_ambulance="Unavailable — explanation generator error.",
            why_this_hospital="Unavailable — explanation generator error.",
            uncertainty_note="Automated explanation could not be generated; please review manually.",
        )

    try:
        return Explanation(**result.parsed_json)
    except Exception:
        return Explanation(
            what_we_know="Explanation generation returned malformed output.",
            why_this_ambulance="Unavailable — schema validation error.",
            why_this_hospital="Unavailable — schema validation error.",
            uncertainty_note="Automated explanation could not be validated; please review manually.",
        )
