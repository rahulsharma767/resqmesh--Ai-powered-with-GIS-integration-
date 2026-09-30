"""
Canonical data contracts for ResQMesh — Person 1 (AI/LLM) <-> Person 2 (Deterministic Engine).

DO NOT change field names/types without bumping incident_schema_version and
notifying Person 2. Additive, backward-compatible changes only during the hackathon.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

INCIDENT_SCHEMA_VERSION = "1.0"


# --------------------------------------------------------------------------
# Shared enums
# --------------------------------------------------------------------------

class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# --------------------------------------------------------------------------
# PART 1 — Incident Extraction output
# --------------------------------------------------------------------------

class Location(BaseModel):
    text: Optional[str] = None          # exactly as reported
    normalized: Optional[str] = None    # left for Person 2 / geocoder to fill; LLM should not invent this


class EvidenceItem(BaseModel):
    field: str
    quote: str
    confidence: float = Field(ge=0.0, le=1.0)


class IncidentState(BaseModel):
    """
    THE CONTRACT. This is what Person 1's pipeline hands to Person 2.
    """
    incident_schema_version: str = INCIDENT_SCHEMA_VERSION
    incident_id: Optional[str] = None

    location: Location = Field(default_factory=Location)
    patient_count: Optional[int] = None
    observed_conditions: List[str] = Field(default_factory=list)
    equipment_requirements: List[str] = Field(default_factory=list)
    reported_time: Optional[str] = None
    incident_type: Optional[str] = None

    severity_cues: List[str] = Field(default_factory=list)
    priority_features: List[str] = Field(default_factory=list)
    priority_cues: Optional[dict] = None   # {"urgency": "HIGH", "reason": "..."}

    uncertainty: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_decision_critical_fields: List[str] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)

    raw_text: Optional[str] = None  # original untrusted input, kept for audit trail

    @field_validator("patient_count")
    @classmethod
    def non_negative_patient_count(cls, v):
        if v is not None and v < 0:
            raise ValueError("patient_count cannot be negative")
        return v


# --------------------------------------------------------------------------
# PART 2 — Ambiguity Gate output
# --------------------------------------------------------------------------

class ClarificationQuestion(BaseModel):
    question: str
    why_it_matters: str
    possible_decision_change: str
    priority: Priority


class AmbiguityResult(BaseModel):
    needs_clarification: bool
    questions: List[ClarificationQuestion] = Field(default_factory=list)


# --------------------------------------------------------------------------
# PART 6 — Adversarial Reviewer output
# --------------------------------------------------------------------------

class ReviewResult(BaseModel):
    """
    THE CONTRACT (Person 1 -> Person 2's verifier).
    The reviewer NEVER modifies or replaces the plan; it only raises challenges.
    """
    challenge_found: bool
    evidence: Optional[str] = None
    affected_constraint: Optional[str] = None
    severity: Optional[Severity] = None
    recommended_recheck: Optional[str] = None


# --------------------------------------------------------------------------
# PART 7 — Explanation Generator output
# --------------------------------------------------------------------------

class Explanation(BaseModel):
    """
    THE CONTRACT (Person 1 -> dispatcher / Person 3 UI).
    """
    what_we_know: str
    why_this_ambulance: str
    why_this_hospital: str
    uncertainty_note: Optional[str] = None
    what_changed: Optional[str] = None


# --------------------------------------------------------------------------
# Inputs Person 2 sends back to the reviewer (for PART 6)
# --------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    incident: IncidentState
    fleet_state: dict
    road_state: dict
    hospital_state: dict
    proposed_plan: dict


# --------------------------------------------------------------------------
# Logging / observability wrapper (PART 9)
# --------------------------------------------------------------------------

class LLMCallRecord(BaseModel):
    model: str
    prompt_version: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    input: dict
    output: Optional[dict] = None
    latency_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    error: Optional[str] = None
