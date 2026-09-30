"""
PART 3 — Human Clarification Interface.

NOT a frontend. This is the backend-independent function Person 3's UI (or Person 2's
API layer) calls to merge a human's answer into the IncidentState. Kept intentionally
simple: pass a dict of {field_name: confirmed_value} and get back an updated IncidentState
with that field cleared from missing_decision_critical_fields.

Example:
    incident = extract_incident("There are around 5 people injured.")
    # ambiguity gate flags patient_count as uncertain
    # human confirms: "4"
    updated = apply_human_clarification(incident, {"patient_count": 4})
"""
from __future__ import annotations

from typing import Any, Dict

from schemas.models import IncidentState

# Fields on IncidentState that a human clarification is allowed to set directly.
ALLOWED_CLARIFICATION_FIELDS = {
    "patient_count",
    "incident_type",
    "reported_time",
    "equipment_requirements",
    "observed_conditions",
}


def apply_human_clarification(incident: IncidentState, answers: Dict[str, Any]) -> IncidentState:
    """
    Merges human-confirmed answers into an IncidentState.

    - Only whitelisted fields can be set this way (prevents a UI bug/typo from
      overwriting fields like severity_cues that should stay LLM-derived + evidenced).
    - Location text updates go through `location.text` explicitly since it's nested.
    - Clears the corresponding entry from missing_decision_critical_fields.
    - Lowers uncertainty slightly per confirmed field (simple heuristic; Person 2's
      deterministic layer should not depend heavily on this number anyway).
    """
    updated = incident.model_copy(deep=True)

    for field_name, value in answers.items():
        if field_name == "location_text":
            updated.location.text = value
            field_key = "location"
        elif field_name in ALLOWED_CLARIFICATION_FIELDS:
            setattr(updated, field_name, value)
            field_key = field_name
        else:
            raise ValueError(
                f"Field '{field_name}' is not allowed to be set via human clarification. "
                f"Allowed: {sorted(ALLOWED_CLARIFICATION_FIELDS)} + 'location_text'"
            )

        if field_key in updated.missing_decision_critical_fields:
            updated.missing_decision_critical_fields.remove(field_key)

    if answers:
        updated.uncertainty = max(0.0, updated.uncertainty - 0.1 * len(answers))

    return updated
