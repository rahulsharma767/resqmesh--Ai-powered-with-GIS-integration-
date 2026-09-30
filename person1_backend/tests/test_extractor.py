import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.extractor import extract_incident
from tests.fake_client import FakeLLMClient


def test_valid_extraction():
    canned = {
        "incident_extractor_v1": {
            "incident_id": None,
            "location": {"text": "Bandra station", "normalized": None},
            "patient_count": 4,
            "observed_conditions": ["injured", "unconscious", "severe bleeding"],
            "equipment_requirements": [],
            "reported_time": None,
            "incident_type": "accident",
            "severity_cues": ["unconscious", "severe bleeding"],
            "uncertainty": 0.2,
            "missing_decision_critical_fields": [],
            "evidence": [
                {"field": "patient_count", "quote": "4 people injured", "confidence": 0.8}
            ],
        }
    }
    client = FakeLLMClient(canned)
    incident = extract_incident("There are around 4 people injured near Bandra station.", client=client)
    assert incident.patient_count == 4
    assert incident.location.text == "Bandra station"
    assert incident.uncertainty == 0.2
    assert incident.raw_text is not None


def test_missing_fields_flagged():
    canned = {
        "incident_extractor_v1": {
            "location": {"text": None, "normalized": None},
            "patient_count": None,
            "observed_conditions": ["injured"],
            "uncertainty": 0.7,
            "missing_decision_critical_fields": ["location", "patient_count"],
            "evidence": [],
        }
    }
    client = FakeLLMClient(canned)
    incident = extract_incident("Someone got hurt, send help.", client=client)
    assert "location" in incident.missing_decision_critical_fields
    assert "patient_count" in incident.missing_decision_critical_fields


def test_llm_failure_fails_safe():
    client = FakeLLMClient(None)  # simulates failure
    incident = extract_incident("Some emergency text", incident_id="INC-99", client=client)
    assert incident.uncertainty == 1.0
    assert incident.incident_id == "INC-99"
    assert incident.patient_count is None
    assert incident.raw_text == "Some emergency text"


def test_malformed_llm_output_fails_safe():
    client = FakeLLMClient({"incident_extractor_v1": {"patient_count": "not_a_number_but_a_dict_would_break_it"}})
    incident = extract_incident("text", client=client)
    # Should still return a valid IncidentState, not raise
    assert incident.uncertainty >= 0.0


if __name__ == "__main__":
    test_valid_extraction()
    test_missing_fields_flagged()
    test_llm_failure_fails_safe()
    test_malformed_llm_output_fails_safe()
    print("test_extractor.py: all tests passed")
