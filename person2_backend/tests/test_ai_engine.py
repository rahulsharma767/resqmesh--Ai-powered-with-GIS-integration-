"""Offline checks for the checked-in local AI risk model."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ai_engine import analyze_incident, runtime_status

critical = analyze_incident({
    "incident": {
        "patient_count": 4,
        "patient_condition": "major trauma, severe bleeding, two unconscious, two critical, cardiac arrest",
        "severity": "critical",
        "label": "Bandra",
    },
    "traffic": "RED",
})
assert critical["priority"] == "CRITICAL"
assert 0 <= critical["risk_score"] <= 1
assert 0 <= critical["confidence"] <= 1
assert critical["model_name"]
assert "inference_provider" in critical
status = runtime_status()
assert status["target_device"] == "Qualcomm QNN / Snapdragon NPU"
print("AI model test passed:", critical["priority"], critical["risk_percent"], critical["inference_provider"])
print("Runtime:", status)
