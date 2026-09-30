import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

APP_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(APP_DIR / "models"))
sys.path.insert(0, str(APP_DIR / "routing"))
sys.path.insert(0, str(APP_DIR / "services"))
sys.path.insert(0, str(APP_DIR / "../.."))

from emergency import EmergencyInput
from dispatch import dispatch
from road_closures import (
    close_edge,
    reopen_edge,
    list_closed_edges,
    clear_closures,
    reroute,
)
from ambulance_selection import load_ambulances
from hospital_selection import load_hospital_data
from ai_engine import analyze_incident, runtime_status


app = FastAPI(
    title="ResQMesh Emergency Dispatch API",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS -- this was the actual cause of "the HTTP requests from the frontend
# don't work": the frontend (Vite, http://localhost:5173) calls this API from
# the browser, and without CORS headers the browser blocks the response
# before the frontend ever sees it (it looks like a network failure, not a
# 4xx/5xx). Person 1's api.py already had this; this backend didn't.
# Configurable the same way Person 1's is, via CORS_ALLOWED_ORIGINS.
# ---------------------------------------------------------------------------
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_origins = os.environ.get("CORS_ALLOWED_ORIGINS", _default_origins).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory overlay for simulated hospital state updates (PATCH endpoint
# below). The underlying CSV (data/simulation/hospital_state.csv) is never
# rewritten -- this only overrides values for the lifetime of this process,
# and is merged on top of the CSV-loaded state before every dispatch/read so
# a PATCH actually affects subsequent dispatch decisions.
# ---------------------------------------------------------------------------
_hospital_state_overrides = {}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "resqmesh-backend",
    }


@app.get("/api/ai/status")
def ai_status():
    """Report the actual local AI runtime/provider; never fabricates NPU execution."""
    return runtime_status()


@app.post("/api/ai/analyze")
def ai_analyze(payload: dict):
    """Run the local emergency-risk model on structured incident state.

    This endpoint is advisory only. It does not select an ambulance, route, or
    hospital; those hard constraints remain in the deterministic dispatch/GIS layer.
    """
    try:
        return analyze_incident(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI inference failed: {exc}")


@app.post("/api/v1/emergency/dispatch")
def emergency_dispatch(incident: EmergencyInput):
    try:
        hospitals, state, nearest_lookup = load_hospital_data()
        # Apply any live PATCH /api/v1/hospitals/{id}/state overrides on top
        # of the CSV-loaded simulated state, so hospital-state changes made
        # through the API actually affect dispatch decisions.
        for hospital_id, override in _hospital_state_overrides.items():
            if hospital_id in state:
                state[hospital_id] = {**state[hospital_id], **override}

        result = dispatch(
            incident,
            hospitals=hospitals,
            state=state,
            nearest_lookup=nearest_lookup,
        )
        return result.to_dict()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/api/v1/ambulances")
def list_ambulances():
    """Real simulated ambulance fleet (150 units) -- authoritative source for
    the frontend's ambulance display. Simulated status is marked as such."""
    ambulances = load_ambulances()
    return {
        "ambulances": ambulances,
        "count": len(ambulances),
        "is_simulated": True,
    }


def _merged_hospital(hospital_id, hospitals, state, nearest_lookup):
    h = hospitals.get(hospital_id)
    if h is None:
        return None
    s = dict(state.get(hospital_id, {}))
    override = _hospital_state_overrides.get(hospital_id)
    if override:
        s.update(override)
    n = nearest_lookup.get(hospital_id, {})
    return {
        "hospital_id": hospital_id,
        "name": h.get("hospital_name"),
        "latitude": h.get("lat"),
        "longitude": h.get("lon"),
        "specialties": h.get("specialties"),
        "total_beds": h.get("total_beds"),
        "graph_node": n.get("nearest_graph_node"),
        "available_beds": s.get("available_beds"),
        "icu_available": s.get("icu_available"),
        "emergency_available": s.get("emergency_available"),
        "status": s.get("status"),
        "is_simulated": True,
    }


@app.get("/api/v1/hospitals")
def list_hospitals():
    """Real government hospital directory (921 usable-for-routing hospitals)
    merged with simulated live state -- authoritative source for the
    frontend's hospital display."""
    hospitals, state, nearest_lookup = load_hospital_data()
    # The static directory has ~1300 entries; only ones flagged
    # usable_for_routing (~921) have coordinates snapped onto the road graph
    # and simulated live state. Those are what the frontend/dispatch engine
    # actually treat as candidates, so that's what this endpoint returns.
    routable_ids = [
        hid for hid, h in hospitals.items()
        if str(h.get("usable_for_routing")).strip().lower() == "true"
    ]
    merged = [
        _merged_hospital(hid, hospitals, state, nearest_lookup)
        for hid in routable_ids
    ]
    return {"hospitals": merged, "count": len(merged), "is_simulated": True}


@app.get("/api/v1/hospitals/{hospital_id}")
def get_hospital(hospital_id: str):
    hospitals, state, nearest_lookup = load_hospital_data()
    result = _merged_hospital(hospital_id, hospitals, state, nearest_lookup)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown hospital_id: {hospital_id}")
    return result


@app.patch("/api/v1/hospitals/{hospital_id}/state")
def update_hospital_state(hospital_id: str, payload: dict):
    """Update simulated live hospital state (status/available_beds/
    icu_available/emergency_available). Held in memory for this process and
    applied on top of the CSV state for every subsequent read/dispatch call.
    The static government hospital directory itself is never modified."""
    hospitals, state, _ = load_hospital_data()
    if hospital_id not in hospitals:
        raise HTTPException(status_code=404, detail=f"Unknown hospital_id: {hospital_id}")

    allowed_fields = {"status", "available_beds", "icu_available", "emergency_available"}
    update = {k: v for k, v in payload.items() if k in allowed_fields}
    if not update:
        raise HTTPException(
            status_code=400,
            detail=f"No recognized fields in payload; allowed: {sorted(allowed_fields)}",
        )

    _hospital_state_overrides.setdefault(hospital_id, {}).update(update)

    return {
        "status": "updated",
        "hospital_id": hospital_id,
        "applied": update,
        "is_simulated": True,
    }


@app.post("/api/v1/roads/closures")
def create_road_closure(payload: dict):
    try:
        u = int(payload["u"])
        v = int(payload["v"])

        edge = close_edge(u, v)

        return {
            "status": "closed",
            "edge": {
                "u": edge[0],
                "v": edge[1],
            },
            "closed_edges": list_closed_edges(),
        }

    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid road edge: {exc}",
        )


@app.post("/api/v1/roads/reopen")
def reopen_road(payload: dict):
    try:
        u = int(payload["u"])
        v = int(payload["v"])

        edge = reopen_edge(u, v)

        return {
            "status": "open",
            "edge": {
                "u": edge[0],
                "v": edge[1],
            },
            "closed_edges": list_closed_edges(),
        }

    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid road edge: {exc}",
        )


@app.get("/api/v1/roads/closures")
def get_road_closures():
    return {
        "closed_edges": list_closed_edges(),
        "count": len(list_closed_edges()),
    }


@app.delete("/api/v1/roads/closures")
def delete_all_road_closures():
    clear_closures()

    return {
        "status": "cleared",
        "closed_edges": [],
        "count": 0,
    }


@app.post("/api/v1/roads/reroute")
def road_reroute(payload: dict):
    try:
        origin_node = int(payload["origin_node"])
        destination_node = int(payload["destination_node"])

        result = reroute(
            origin_node,
            destination_node,
        )

        return result

    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid routing request: {exc}",
        )