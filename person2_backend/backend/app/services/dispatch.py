"""
Part 12 foundation -- dispatch orchestration.

Combines the existing emergency input, nearest-node snapping,
ambulance selection, hospital selection, and A* routing services
into one reusable dispatch() function.

The HTTP layer can call this function without duplicating business logic.
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(_THIS_DIR, '..', 'models'))
sys.path.insert(0, os.path.join(_THIS_DIR, '..', 'routing'))

from emergency import (  # noqa: E402
    EmergencyInput,
    DispatchResponse,
    AmbulanceResult,
    HospitalResult,
    DecisionExplanation,
)

from nearest_node import nearest_node  # noqa: E402
from router import get_graph, find_route  # noqa: E402

from ambulance_selection import (  # noqa: E402
    select_ambulance,
    load_ambulances,
    required_min_type,
)

from hospital_selection import (  # noqa: E402
    select_hospital,
    load_hospital_data,
)


def dispatch(
    incident: EmergencyInput,
    G=None,
    ambulances=None,
    hospitals=None,
    state=None,
    nearest_lookup=None,
):
    """
    Compute a complete emergency dispatch.

    Returns a DispatchResponse containing:
      - selected ambulance
      - pickup/snapping information
      - selected hospital
      - ambulance->incident route
      - incident->hospital route
      - decision explanations
    """

    if G is None:
        G = get_graph()

    if ambulances is None:
        ambulances = load_ambulances()

    if hospitals is None or state is None or nearest_lookup is None:
        hospitals, state, nearest_lookup = load_hospital_data()

    # Snap incident coordinates onto the routable road graph.
    incident_node, snap_dist_m = nearest_node(
        incident.latitude,
        incident.longitude,
    )

    # ICU is required either explicitly or because another capability
    # implies the ICU minimum ambulance level.
    needs_icu = (
        'ICU' in incident.required_capabilities
        or required_min_type(incident.required_capabilities) == 'ICU'
    )

    # Select ambulance using availability, capability and real road ETA.
    amb, amb_reason, _ = select_ambulance(
        incident.latitude,
        incident.longitude,
        incident_node,
        incident.required_capabilities,
        incident.severity,
        ambulances=ambulances,
        G=G,
    )

    # Select hospital using availability, capabilities, specialty,
    # ICU requirement and real road ETA.
    hosp, hosp_reason, _ = select_hospital(
        incident.latitude,
        incident.longitude,
        incident_node,
        incident.required_capabilities,
        needs_icu,
        hospitals=hospitals,
        state=state,
        nearest=nearest_lookup,
        G=G,
    )

    # Route ambulance -> incident.
    ambulance_route = None

    if amb is not None:
        ambulance_route = find_route(
            amb.node,
            incident_node,
            G=G,
        )

    # Route incident -> hospital.
    hospital_route = None

    if hosp is not None:
        hospital_route = find_route(
            incident_node,
            hosp.node,
            G=G,
        )

    ambulance_result = None

    if amb is not None:
        ambulance_result = AmbulanceResult(
            ambulance_id=amb.ambulance_id,
            type=amb.ambulance_type,
            eta_minutes=(
                ambulance_route['duration_minutes']
                if ambulance_route and ambulance_route.get('found')
                else None
            ),
        )

    hospital_result = None

    if hosp is not None:
        hospital_result = HospitalResult(
            hospital_id=hosp.hospital_id,
            name=hosp.name,
            eta_minutes=(
                hospital_route['duration_minutes']
                if hospital_route and hospital_route.get('found')
                else None
            ),
        )

    return DispatchResponse(
        incident_id=incident.incident_id,

        ambulance=ambulance_result,

        pickup={
            'latitude': incident.latitude,
            'longitude': incident.longitude,
            'graph_node': incident_node,
            'snap_distance_m': round(snap_dist_m, 1),
        },

        hospital=hospital_result,

        routes={
            'ambulance_to_incident': ambulance_route,
            'incident_to_hospital': hospital_route,
        },

        decision=DecisionExplanation(
            ambulance_reason=amb_reason,
            hospital_reason=hosp_reason,
        ),
    )