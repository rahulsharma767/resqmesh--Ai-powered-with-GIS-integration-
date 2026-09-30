import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.ambiguity import detect_ambiguity
from schemas.models import IncidentState
from tests.fake_client import FakeLLMClient


def test_no_clarification_needed():
    canned = {"ambiguity_gate_v1": {"needs_clarification": False, "questions": []}}
    client = FakeLLMClient(canned)
    incident = IncidentState(patient_count=4, location={"text": "Bandra station"})
    result = detect_ambiguity(incident, client=client)
    assert result.needs_clarification is False
    assert result.questions == []


def test_clarification_needed_with_priority():
    canned = {
        "ambiguity_gate_v1": {
            "needs_clarification": True,
            "questions": [{
                "question": "How many patients are confirmed?",
                "why_it_matters": "Affects ambulance capacity.",
                "possible_decision_change": "May need a second ambulance.",
                "priority": "HIGH",
            }],
        }
    }
    client = FakeLLMClient(canned)
    incident = IncidentState(patient_count=None)
    result = detect_ambiguity(incident, client=client)
    assert result.needs_clarification is True
    assert result.questions[0].priority == "HIGH"


def test_failure_defaults_to_needing_clarification():
    client = FakeLLMClient(None)
    incident = IncidentState(patient_count=3)
    result = detect_ambiguity(incident, client=client)
    # Fail-safe: on failure we should NOT silently assume everything is fine.
    assert result.needs_clarification is True


if __name__ == "__main__":
    test_no_clarification_needed()
    test_clarification_needed_with_priority()
    test_failure_defaults_to_needing_clarification()
    print("test_ambiguity.py: all tests passed")
