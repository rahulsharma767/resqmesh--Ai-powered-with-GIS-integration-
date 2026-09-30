import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.reviewer import review_plan
from schemas.models import IncidentState
from tests.fake_client import FakeLLMClient


def test_challenge_found():
    canned = {
        "adversarial_reviewer_v1": {
            "challenge_found": True,
            "evidence": "Ambulance A-2 has no spinal board but incident requires one.",
            "affected_constraint": "equipment_requirements",
            "severity": "HIGH",
            "recommended_recheck": "Verify ambulance equipment before dispatch.",
        }
    }
    client = FakeLLMClient(canned)
    incident = IncidentState(patient_count=1, equipment_requirements=["spinal board"])
    result = review_plan(
        incident=incident, fleet_state={"A-2": {"equipment": []}}, road_state={},
        hospital_state={}, proposed_plan={"ambulance": "A-2"}, client=client,
    )
    assert result.challenge_found is True
    assert result.severity == "HIGH"


def test_no_challenge():
    canned = {"adversarial_reviewer_v1": {"challenge_found": False}}
    client = FakeLLMClient(canned)
    incident = IncidentState(patient_count=1)
    result = review_plan(
        incident=incident, fleet_state={}, road_state={}, hospital_state={},
        proposed_plan={"ambulance": "A-1"}, client=client,
    )
    assert result.challenge_found is False


def test_reviewer_failure_fails_safe_as_challenge():
    client = FakeLLMClient(None)
    incident = IncidentState(patient_count=1)
    result = review_plan(
        incident=incident, fleet_state={}, road_state={}, hospital_state={},
        proposed_plan={"ambulance": "A-1"}, client=client,
    )
    # Fail-safe: reviewer failure must NOT be silently treated as "plan is fine"
    assert result.challenge_found is True
    assert result.severity == "HIGH"


if __name__ == "__main__":
    test_challenge_found()
    test_no_challenge()
    test_reviewer_failure_fails_safe_as_challenge()
    print("test_reviewer.py: all tests passed")
