"""
Deterministic, offline heuristic responses used when PERSON1_MODE=mock (the
default mode). This mirrors the same keyword-based demo logic Person 3's
frontend already uses (mockAIService() in ResQMesh.jsx), so the two "mock"
layers behave consistently and the whole pipeline runs end-to-end with ZERO
outbound API calls / zero Gemini quota usage.

This is intentionally simple keyword matching, NOT a language model. It exists
only so PERSON1_MODE=mock produces plausible, reproducible IncidentState /
AmbiguityResult output for local development and demos without hitting the
Gemini free-tier quota (GenerateRequestsPerDayPerProjectPerModel-FreeTier).

Switch to PERSON1_MODE=real (with LLM_API_KEY set) for actual LLM-backed
extraction via clients/llm_client.py.
"""
from __future__ import annotations

import json
import re
from typing import Optional

# Kept in sync (by name) with LOCATION_KEYWORDS in ResQMesh.jsx so a mock
# extraction and the frontend's own local fallback resolve to the same places.
LOCATION_KEYWORDS = [
    ("bandra station", "Bandra Station"), ("bandra", "Bandra"), ("khar", "Khar"),
    ("santacruz", "Santacruz"), ("vile parle", "Vile Parle"), ("andheri", "Andheri"),
    ("jogeshwari", "Jogeshwari"), ("powai", "Powai"), ("ghatkopar", "Ghatkopar"),
    ("kurla", "Kurla"), ("sion", "Sion"), ("dadar", "Dadar"), ("worli", "Worli"),
    ("lower parel", "Lower Parel"), ("mahim", "Mahim"), ("chembur", "Chembur"),
    ("vikhroli", "Vikhroli"), ("malad", "Malad"), ("goregaon", "Goregaon"),
    ("bhandup", "Bhandup"), ("dharavi", "Dharavi"), ("byculla", "Byculla"),
]

CRITICAL_CONDITIONS = [
    "unconscious", "severe bleeding", "cardiac arrest", "not breathing",
    "chest pain", "head injury",
]
CONDITION_KEYWORDS = [
    "unconscious", "severe bleeding", "bleeding", "fracture", "broken leg", "broken arm",
    "chest pain", "difficulty breathing", "not breathing", "cardiac arrest", "burn",
    "trapped", "seizure", "head injury", "fall",
]
WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
VAGUE_QUANTITY_WORDS = ["several", "multiple", "many", "some", "a few"]

# Same INTENT as the frontend's INJECTION_PATTERNS: flag suspicious embedded
# instructions as text EVIDENCE only. Never used to set location/equipment/
# priority/dispatch — IncidentState has no dispatch field to set (PART 12).
INJECTION_PATTERNS = [
    re.compile(r"ignore (the |all )?(system|previous|above)", re.I),
    re.compile(r"you must (dispatch|send)", re.I),
    re.compile(r"dispatch\s+amb-\d+", re.I),
    re.compile(r"disregard (the |all )?(system|rules|previous)", re.I),
    re.compile(r"override (the )?(system|protocol|rules)", re.I),
    re.compile(r"system prompt", re.I),
    re.compile(r"send\s+ambulance\s+\d+", re.I),
]


def _extract_marked_block(user_prompt: str) -> str:
    """Every prompt template wraps its variable payload in '---' markers."""
    match = re.search(r"---\n(.*?)\n---", user_prompt, re.DOTALL)
    return match.group(1).strip() if match else user_prompt


def mock_incident_extractor(user_prompt: str) -> dict:
    raw_text = _extract_marked_block(user_prompt)
    lower = raw_text.lower()

    loc_match = next((kw for kw in LOCATION_KEYWORDS if kw[0] in lower), None)
    location_text = loc_match[1] if loc_match else None

    patient_count = None
    num_match = re.search(r"(\d+)\s*(people|patients|persons|injured)", lower)
    if num_match:
        patient_count = int(num_match.group(1))
    if patient_count is None:
        for word, n in WORD_NUMBERS.items():
            if re.search(rf"\b{word}\b", lower):
                patient_count = n
                break
    vague_hit = next((w for w in VAGUE_QUANTITY_WORDS if w in lower), None)

    conditions = [c for c in CONDITION_KEYWORDS if c in lower]
    severity_cues = [c for c in conditions if c in CRITICAL_CONDITIONS]
    equipment_requirements = ["ALS"] if severity_cues else (["BLS"] if conditions or patient_count else [])

    missing = []
    if not location_text:
        missing.append("location")
    if patient_count is None:
        missing.append("patient_count")
    uncertainty = 0.8 if len(missing) >= 2 else (0.5 if len(missing) == 1 else 0.15)

    evidence = []
    if location_text:
        evidence.append({"field": "location", "quote": loc_match[0], "confidence": 0.7})
    if patient_count is not None:
        evidence.append({
            "field": "patient_count",
            "quote": (num_match.group(0) if num_match else (vague_hit or "")),
            "confidence": 0.7,
        })
    for c in conditions:
        evidence.append({"field": "observed_conditions", "quote": c, "confidence": 0.6})

    injection_hit = next((p for p in INJECTION_PATTERNS if p.search(raw_text)), None)
    if injection_hit:
        m = injection_hit.search(raw_text)
        # Recorded as evidence of a suspicious embedded instruction ONLY. It is
        # NEVER used to set location/equipment/priority/dispatch (PART 12) —
        # IncidentState has no field that could authorize dispatch anyway.
        evidence.append({"field": "observed_conditions", "quote": m.group(0), "confidence": 0.9})

    return {
        "incident_id": None,
        "location": {"text": location_text, "normalized": None},
        "patient_count": patient_count,
        "observed_conditions": conditions,
        "equipment_requirements": equipment_requirements,
        "reported_time": None,
        "incident_type": None,
        "severity_cues": severity_cues,
        "uncertainty": uncertainty,
        "missing_decision_critical_fields": missing,
        "evidence": evidence,
    }


def mock_ambiguity_gate(user_prompt: str) -> dict:
    block = _extract_marked_block(user_prompt)
    try:
        incident = json.loads(block)
    except Exception:
        incident = {}
    missing = incident.get("missing_decision_critical_fields") or []
    if not missing:
        return {"needs_clarification": False, "questions": []}

    questions = []
    if "location" in missing:
        questions.append({
            "question": "What is the exact location of the incident?",
            "why_it_matters": "Ambulance dispatch and routing require a known location.",
            "possible_decision_change": "Which ambulance and hospital are selected.",
            "priority": "HIGH",
        })
    if "patient_count" in missing:
        questions.append({
            "question": "How many patients are involved?",
            "why_it_matters": "Affects ambulance capacity and whether multiple units are needed.",
            "possible_decision_change": "Number/type of ambulances dispatched.",
            "priority": "MEDIUM",
        })
    return {"needs_clarification": True, "questions": questions}


def mock_priority_cues(user_prompt: str) -> dict:
    block = _extract_marked_block(user_prompt)
    try:
        incident = json.loads(block)
    except Exception:
        incident = {}
    severity_cues = incident.get("severity_cues") or []
    if severity_cues:
        urgency = "CRITICAL" if len(severity_cues) > 1 else "HIGH"
    elif incident.get("observed_conditions"):
        urgency = "MEDIUM"
    else:
        urgency = "LOW"
    priority_features = [c.replace(" ", "_") for c in severity_cues]
    return {
        "severity_cues": severity_cues,
        "priority_features": priority_features,
        "priority_cues": {
            "urgency": urgency,
            "reason": "Heuristic cue only (mock mode) — not a dispatch authorization.",
        },
        "uncertainty": incident.get("uncertainty", 0.3),
    }


def mock_adversarial_reviewer(user_prompt: str) -> dict:
    # Conservative default: no challenge. Person 2's deterministic verifier
    # still makes the final call either way.
    return {
        "challenge_found": False,
        "evidence": None,
        "affected_constraint": None,
        "severity": None,
        "recommended_recheck": None,
    }


def mock_explanation_generator(user_prompt: str) -> dict:
    return {
        "what_we_know": "Summary unavailable in mock mode — refer to the verified plan data directly.",
        "why_this_ambulance": "Mock mode: no LLM call was made for this explanation.",
        "why_this_hospital": "Mock mode: no LLM call was made for this explanation.",
        "uncertainty_note": "This is a MOCK explanation (PERSON1_MODE=mock).",
        "what_changed": None,
    }


MOCK_HANDLERS = {
    "incident_extractor_v1": mock_incident_extractor,
    "ambiguity_gate_v1": mock_ambiguity_gate,
    "priority_cues_v1": mock_priority_cues,
    "adversarial_reviewer_v1": mock_adversarial_reviewer,
    "explanation_generator_v1": mock_explanation_generator,
}


def mock_complete(user_prompt: str, prompt_version: str) -> Optional[dict]:
    handler = MOCK_HANDLERS.get(prompt_version)
    if handler is None:
        return None
    return handler(user_prompt)
