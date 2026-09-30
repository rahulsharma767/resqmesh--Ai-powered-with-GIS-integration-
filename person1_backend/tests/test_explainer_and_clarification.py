import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.clarification import apply_human_clarification
from nodes.explainer import generate_explanation
from schemas.models import IncidentState
from tests.fake_client import FakeLLMClient


def test_apply_human_clarification_merges_and_clears_missing():
    incident = IncidentState(
        patient_count=None,
        missing_decision_critical_fields=["patient_count", "location"],
        uncertainty=0.6,
    )
    updated = apply_human_clarification(incident, {"patient_count": 4})
    assert updated.patient_count == 4
    assert "patient_count" not in updated.missing_decision_critical_fields
    assert "location" in updated.missing_decision_critical_fields  # untouched
    assert updated.uncertainty < 0.6


def test_apply_human_clarification_rejects_disallowed_field():
    incident = IncidentState()
    raised = False
    try:
        apply_human_clarification(incident, {"severity_cues": ["fake"]})
    except ValueError:
        raised = True
    assert raised


def test_explanation_generation_grounded():
    canned = {
        "explanation_generator_v1": {
            "what_we_know": "4 patients reported near Bandra station, one unconscious.",
            "why_this_ambulance": "A-2 was closest with required equipment.",
            "why_this_hospital": "City General has capacity and trauma care.",
            "uncertainty_note": "Patient count was approximate.",
            "what_changed": None,
        }
    }
    client = FakeLLMClient(canned)
    explanation = generate_explanation(
        verified_facts={"patients": 4}, assignment={"ambulance": "A-2"},
        route={"eta_min": 6}, hospital={"name": "City General"}, uncertainty=0.2,
        client=client,
    )
    assert "A-2" in explanation.why_this_ambulance
    assert explanation.uncertainty_note is not None


def test_explanation_fails_safe_on_error():
    client = FakeLLMClient(None)
    explanation = generate_explanation(
        verified_facts={}, assignment={}, route={}, hospital={}, uncertainty=0.5, client=client,
    )
    assert "failed" in explanation.what_we_know.lower() or "unavailable" in explanation.why_this_ambulance.lower()


if __name__ == "__main__":
    test_apply_human_clarification_merges_and_clears_missing()
    test_apply_human_clarification_rejects_disallowed_field()
    test_explanation_generation_grounded()
    test_explanation_fails_safe_on_error()
    print("test_explainer_and_clarification.py: all tests passed")
