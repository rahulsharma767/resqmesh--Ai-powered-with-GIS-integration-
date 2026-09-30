"""
Part 10 -- Hospital selection algorithm.

Does NOT pick the nearest hospital. Ranking considers:
  1. emergency capability (state layer's emergency_available flag)
  2. required specialty match (against the static directory's Specialties text)
  3. current simulated availability (available_beds / status)
  4. ICU availability when the incident needs it
  5. real road travel time (incident -> hospital, via the A* routing engine)

hospital_score = capability_score + availability_score + specialty_score - travel_time_penalty

All weights configurable in SCORING_WEIGHTS below -- not a black box.
"""
import csv
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_THIS_DIR, '..', 'routing'))
sys.path.insert(0, os.path.join(_THIS_DIR, '..', '..', '..', 'scripts'))
from router import find_route, get_graph, haversine_km  # noqa: E402
from paths import (MUMBAI_HOSPITALS_CSV as HOSPITALS_CSV, HOSPITAL_STATE_CSV as STATE_CSV,
                    HOSPITAL_NEAREST_NODE_CSV as NEAREST_NODE_CSV)  # noqa: E402

SCORING_WEIGHTS = {
    'capability': 3.0,     # emergency_available flag
    'icu_bonus': 2.0,      # icu_available, only counted if the incident needs ICU
    'specialty': 2.0,      # keyword overlap between required_capabilities and Specialties text
    'availability': 2.0,   # scaled by available_beds, capped
    'travel_time_penalty_per_min': 0.15,  # subtracted per minute of ETA
}

AVAILABLE_BEDS_CAP_FOR_SCORING = 20  # beds beyond this don't add extra score
CANDIDATE_POOL_SIZE = 15  # nearest capability-eligible hospitals routed for real ETA


def load_hospital_data():
    with open(HOSPITALS_CSV) as f:
        hospitals = {r['hospital_id']: r for r in csv.DictReader(f)}
    with open(STATE_CSV) as f:
        state = {r['hospital_id']: r for r in csv.DictReader(f)}
    with open(NEAREST_NODE_CSV) as f:
        nearest = {r['hospital_id']: r for r in csv.DictReader(f)}
    return hospitals, state, nearest


@dataclass
class HospitalCandidate:
    hospital_id: str
    name: str
    node: int
    lat: float
    lon: float
    distance_km_straight_line: float
    emergency_available: bool
    icu_available: bool
    available_beds: int
    specialty_match: bool
    travel_time_min: Optional[float] = None
    route_distance_km: Optional[float] = None
    score: Optional[float] = None
    disqualified_reason: Optional[str] = None


def specialty_matches(specialties_text, required_capabilities):
    if not specialties_text or not required_capabilities:
        return False
    text = specialties_text.lower()
    return any(cap.lower() in text for cap in required_capabilities)


def select_hospital(incident_lat, incident_lon, incident_node, required_capabilities,
                     needs_icu, hospitals=None, state=None, nearest=None, G=None,
                     pool_size=CANDIDATE_POOL_SIZE):
    """
    Returns (selected: dict | None, reasoning: str, all_candidates: List[HospitalCandidate])
    """
    if hospitals is None or state is None or nearest is None:
        hospitals, state, nearest = load_hospital_data()
    if G is None:
        G = get_graph()

    candidates = []
    for hid, h in hospitals.items():
        if h['usable_for_routing'] != 'True':
            continue  # can't route to it -- never a candidate, regardless of quality
        st = state.get(hid)
        if st is None:
            continue
        if st['status'] == 'FULL':
            continue  # hard filter: no point sending an ambulance to a full hospital

        nn = nearest.get(hid)
        if nn is None:
            continue

        lat, lon = float(nn['latitude']), float(nn['longitude'])
        straight_km = haversine_km(incident_lat, incident_lon, lat, lon)

        candidates.append(HospitalCandidate(
            hospital_id=hid, name=h['hospital_name'], node=int(nn['nearest_graph_node']),
            lat=lat, lon=lon, distance_km_straight_line=round(straight_km, 3),
            emergency_available=(st['emergency_available'] == 'True'),
            icu_available=(st['icu_available'] == 'True'),
            available_beds=int(st['available_beds']),
            specialty_match=specialty_matches(h['specialties'], required_capabilities),
        ))

    if not candidates:
        return None, "No hospital is usable-for-routing and not FULL in the simulated state.", []

    candidates.sort(key=lambda c: c.distance_km_straight_line)
    pool = candidates[:pool_size]

    for cand in pool:
        route = find_route(incident_node, cand.node, G=G)
        if not route['found']:
            cand.disqualified_reason = 'no_road_route_found'
            continue
        cand.travel_time_min = route['duration_minutes']
        cand.route_distance_km = route['distance_km']

    routed = [c for c in pool if c.travel_time_min is not None]
    if not routed:
        return None, "Nearest candidate hospitals have no road route from the incident.", pool

    for c in routed:
        capability_score = SCORING_WEIGHTS['capability'] if c.emergency_available else 0.0
        icu_score = SCORING_WEIGHTS['icu_bonus'] if (needs_icu and c.icu_available) else 0.0
        specialty_score = SCORING_WEIGHTS['specialty'] if c.specialty_match else 0.0
        availability_score = SCORING_WEIGHTS['availability'] * min(
            c.available_beds, AVAILABLE_BEDS_CAP_FOR_SCORING
        ) / AVAILABLE_BEDS_CAP_FOR_SCORING
        travel_penalty = SCORING_WEIGHTS['travel_time_penalty_per_min'] * c.travel_time_min

        c.score = round(
            capability_score + icu_score + specialty_score + availability_score - travel_penalty, 3
        )

    routed.sort(key=lambda c: -c.score)
    best = routed[0]

    reasoning = (
        f"Selected {best.name} ({best.hospital_id}): score={best.score} "
        f"[emergency_available={best.emergency_available}, icu_available={best.icu_available} "
        f"(needed={needs_icu}), specialty_match={best.specialty_match}, "
        f"available_beds={best.available_beds}, eta={best.travel_time_min:.1f} min]. "
        f"Best of {len(routed)} routed candidates "
        f"(pool pre-filtered to {len(pool)} nearest of {len(candidates)} eligible non-full hospitals)."
    )

    return best, reasoning, routed
