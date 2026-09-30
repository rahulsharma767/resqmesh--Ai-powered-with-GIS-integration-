import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError

from schemas.models import IncidentState

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


def test_valid_example_passes():
    with open(os.path.join(EXAMPLES_DIR, "valid_input.json")) as f:
        data = json.load(f)
    incident = IncidentState(**data["expected_incident_state"])
    assert incident.patient_count == 4


def test_ambiguous_example_passes_but_flags_missing_fields():
    with open(os.path.join(EXAMPLES_DIR, "ambiguous_input.json")) as f:
        data = json.load(f)
    incident = IncidentState(**data["expected_incident_state"])
    assert "location" in incident.missing_decision_critical_fields
    assert incident.uncertainty > 0.5


def test_invalid_examples_all_fail_validation():
    with open(os.path.join(EXAMPLES_DIR, "invalid_input.json")) as f:
        data = json.load(f)
    for case in data["invalid_examples"]:
        raised = False
        try:
            IncidentState(**case["incident_state"])
        except ValidationError:
            raised = True
        assert raised, f"Expected ValidationError for case: {case['reason']}"


def test_schema_version_default():
    incident = IncidentState()
    assert incident.incident_schema_version == "1.0"


if __name__ == "__main__":
    test_valid_example_passes()
    test_ambiguous_example_passes_but_flags_missing_fields()
    test_invalid_examples_all_fail_validation()
    test_schema_version_default()
    print("test_schema.py: all tests passed")
