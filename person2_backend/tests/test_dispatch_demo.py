"""
End-to-end demo proving Parts 8-11 actually work together: takes an
EmergencyInput, selects an ambulance, routes it to the incident, selects a
hospital, routes incident->hospital, and prints the full reasoning trail.

This is NOT the Part 12 HTTP dispatch endpoint (no FastAPI available in this
sandbox -- see README) -- it's a plain-function pipeline test that exercises
the exact same services/routing code the eventual endpoint will call.
"""
import os
import sys
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, 'backend', 'app', 'models'))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, 'backend', 'app', 'routing'))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, 'backend', 'app', 'services'))

from emergency import EmergencyInput
from router import get_graph, find_route
from nearest_node import nearest_node
from ambulance_selection import select_ambulance, load_ambulances, required_min_type
from hospital_selection import select_hospital, load_hospital_data
import time


def run_dispatch(incident: EmergencyInput, G, ambulances, hospitals, state, nearest_lookup):
    incident_node, snap_dist_m = nearest_node(incident.latitude, incident.longitude)

    needs_icu = 'ICU' in incident.required_capabilities or required_min_type(incident.required_capabilities) == 'ICU'

    amb, amb_reason, amb_candidates = select_ambulance(
        incident.latitude, incident.longitude, incident_node,
        incident.required_capabilities, incident.severity,
        ambulances=ambulances, G=G,
    )
    hosp, hosp_reason, hosp_candidates = select_hospital(
        incident.latitude, incident.longitude, incident_node,
        incident.required_capabilities, needs_icu,
        hospitals=hospitals, state=state, nearest=nearest_lookup, G=G,
    )

    print(f"\n{'='*70}")
    print(f"INCIDENT {incident.incident_id}  severity={incident.severity}  "
          f"condition={incident.patient_condition}  required={incident.required_capabilities}")
    print(f"Location: ({incident.latitude}, {incident.longitude}) -> snapped to graph node "
          f"{incident_node} ({snap_dist_m:.0f}m away)")
    print('-' * 70)

    if amb is None:
        print(f"AMBULANCE: NONE SELECTED. Reason: {amb_reason}")
    else:
        route_to_incident = find_route(amb.node, incident_node, G=G)
        print(f"AMBULANCE: {amb.ambulance_id} ({amb.ambulance_type})")
        print(f"  Reason: {amb_reason}")
        print(f"  Route ambulance->incident: {route_to_incident['distance_km']} km, "
              f"{route_to_incident['duration_minutes']} min, {route_to_incident['edge_count']} edges")

    if hosp is None:
        print(f"HOSPITAL: NONE SELECTED. Reason: {hosp_reason}")
    else:
        route_to_hospital = find_route(incident_node, hosp.node, G=G)
        print(f"HOSPITAL: {hosp.name} ({hosp.hospital_id})")
        print(f"  Reason: {hosp_reason}")
        print(f"  Route incident->hospital: {route_to_hospital['distance_km']} km, "
              f"{route_to_hospital['duration_minutes']} min, {route_to_hospital['edge_count']} edges")

    print('=' * 70)
    return amb, hosp


if __name__ == '__main__':
    t0 = time.time()
    G = get_graph()
    ambulances = load_ambulances()
    hospitals, state, nearest_lookup = load_hospital_data()
    print(f"Loaded all data in {time.time()-t0:.1f}s")

    # Real Mumbai coordinates for test incidents
    test_incidents = [
        EmergencyInput(
            incident_id="INC-001", latitude=19.0596, longitude=72.8295,  # Bandra
            severity="critical", patient_condition="cardiac",
            required_capabilities=["ALS", "CARDIAC"],
        ),
        EmergencyInput(
            incident_id="INC-002", latitude=19.1197, longitude=72.8468,  # Andheri
            severity="low", patient_condition="minor laceration",
            required_capabilities=["BASIC"],
        ),
        EmergencyInput(
            incident_id="INC-003", latitude=18.9388, longitude=72.8354,  # Colaba
            severity="critical", patient_condition="severe trauma, head injury",
            required_capabilities=["ICU", "TRAUMA", "NEURO"],
        ),
    ]

    for incident in test_incidents:
        t1 = time.time()
        run_dispatch(incident, G, ambulances, hospitals, state, nearest_lookup)
        print(f"(dispatch computed in {time.time()-t1:.2f}s)")
