"""
Part 8 -- Emergency input contract.

LIMITATION (documented): neither `pydantic` nor `fastapi` is installed in
this sandbox, and there is no network access to install them. This module
therefore implements the same contract using stdlib `dataclasses` with
manual validation in `__post_init__`, matching pydantic's behavior
(construction raises ValueError on bad input) and using the exact same
field names/types as the intended pydantic version. Swapping this for a
real `pydantic.BaseModel` later (once pip/network is available) is a
mechanical find-and-replace, not a redesign -- every field, type, and
validation rule below is written so that swap is drop-in.

This is the ONLY thing Person 1's AI layer needs to know about: send a JSON
body shaped like EmergencyInput to POST /api/v1/emergency/dispatch (Part 12,
wired up as a plain-Python dispatch() function in services/dispatch.py since
there's no FastAPI to expose an HTTP route with in this sandbox -- see
README "Integration with Person 1" for how to wire this to a real FastAPI
app once dependencies are installable).
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional

# Configurable vocab -- change here, not in scattered business logic
SEVERITY_LEVELS = ['low', 'moderate', 'critical']
CAPABILITY_TAGS = [
    'BASIC', 'ALS', 'ICU',            # ambulance-type-level capabilities
    'CARDIAC', 'TRAUMA', 'BURNS', 'PEDIATRIC', 'MATERNITY',
    'NEURO', 'RESPIRATORY', 'PSYCHIATRIC', 'POISONING',
]


@dataclass
class EmergencyInput:
    incident_id: str
    latitude: float
    longitude: float
    severity: str
    patient_condition: str
    required_capabilities: List[str] = field(default_factory=list)
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"latitude out of range: {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"longitude out of range: {self.longitude}")
        if self.severity.lower() not in SEVERITY_LEVELS:
            raise ValueError(f"severity must be one of {SEVERITY_LEVELS}, got '{self.severity}'")
        self.severity = self.severity.lower()
        if not self.incident_id:
            raise ValueError("incident_id is required")
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            incident_id=d['incident_id'],
            latitude=float(d['latitude']),
            longitude=float(d['longitude']),
            severity=d['severity'],
            patient_condition=d['patient_condition'],
            required_capabilities=d.get('required_capabilities', []),
            timestamp=d.get('timestamp'),
        )

    def to_dict(self):
        d = asdict(self)
        if isinstance(d.get('timestamp'), datetime):
            d['timestamp'] = d['timestamp'].isoformat()
        return d


EXAMPLE_EMERGENCY_INPUT = {
    "incident_id": "INC-001",
    "latitude": 19.0760,
    "longitude": 72.8777,
    "severity": "critical",
    "patient_condition": "cardiac",
    "required_capabilities": ["ALS", "CARDIAC"],
    "timestamp": "2026-08-23T10:00:00Z",
}


@dataclass
class RouteResult:
    distance_km: Optional[float]
    duration_minutes: Optional[float]
    coordinates: List[List[float]] = field(default_factory=list)


@dataclass
class AmbulanceResult:
    ambulance_id: str
    type: str
    eta_minutes: Optional[float]


@dataclass
class HospitalResult:
    hospital_id: str
    name: str
    eta_minutes: Optional[float]


@dataclass
class DecisionExplanation:
    ambulance_reason: str
    hospital_reason: str


@dataclass
class DispatchResponse:
    incident_id: str
    ambulance: Optional[AmbulanceResult]
    pickup: dict
    hospital: Optional[HospitalResult]
    routes: dict
    decision: DecisionExplanation

    def to_dict(self):
        return {
            'incident_id': self.incident_id,
            'ambulance': asdict(self.ambulance) if self.ambulance else None,
            'pickup': self.pickup,
            'hospital': asdict(self.hospital) if self.hospital else None,
            'routes': self.routes,
            'decision': asdict(self.decision),
        }
