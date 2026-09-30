"""
ResQMesh AI pipeline orchestrator (Person 1's side only).

    raw text -> extract_incident -> detect_ambiguity -> (optional human merge)
             -> extract_priority_cues -> IncidentState  ==>  handed to Person 2

    Person 2's proposed_plan  -> review_plan -> ReviewResult  ==>  handed to Person 2's verifier

    Person 2's verified plan  -> generate_explanation -> Explanation ==> dispatcher UI

This file does NOT talk to Person 2's code directly — it just shows how my nodes
compose. Person 2 calls into this (or reimplements the same JSON contract) from
their own process/service.
"""
from __future__ import annotations

from typing import Optional

from clients.llm_client import LLMClient
from nodes.ambiguity import detect_ambiguity
from nodes.explainer import generate_explanation
from nodes.extractor import extract_incident
from nodes.priority import extract_priority_cues
from nodes.reviewer import review_plan
from schemas.models import AmbiguityResult, IncidentState


def build_incident_state(raw_text: str, incident_id: Optional[str] = None,
                          client: Optional[LLMClient] = None) -> tuple[IncidentState, AmbiguityResult]:
    """
    Runs Parts 1, 2, and 4 in sequence. Returns the IncidentState ready to hand to
    Person 2, plus the AmbiguityResult so the caller (or Person 3's UI) can decide
    whether to block on human clarification before dispatching.
    """
    client = client or LLMClient()
    incident = extract_incident(raw_text, incident_id=incident_id, client=client)
    ambiguity = detect_ambiguity(incident, client=client)
    incident = extract_priority_cues(incident, client=client)
    return incident, ambiguity


__all__ = [
    "build_incident_state",
    "extract_incident",
    "detect_ambiguity",
    "extract_priority_cues",
    "review_plan",
    "generate_explanation",
]
