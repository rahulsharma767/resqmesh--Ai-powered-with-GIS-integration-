"""Local emergency-risk inference for ResQMesh AI.

The production path is deliberately small and portable:
  structured incident -> trained tabular classifier -> risk/priority/confidence

A NumPy implementation is always available from the checked-in model artifact.
When ONNX Runtime is installed, the same model can be loaded locally. When the
Qualcomm QNN Execution Provider is available, it is preferred automatically.
No Snapdragon/NPU execution is claimed unless the runtime reports it.

Training data is synthetic simulation data and is NOT clinical/real-world data.
This model is decision support only; deterministic dispatch/routing remains
outside the model.
"""
from __future__ import annotations

import json
import math
import platform
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "emergency_risk_model.npz"
ONNX_PATH = MODEL_DIR / "emergency_risk_model.onnx"
META_PATH = ROOT / "model_metadata.json"

FEATURES = [
    "number_of_patients", "unconscious_count", "critical_count", "injury_severity",
    "fire_present", "accident_type", "traffic_level", "road_block_probability",
    "distance_to_nearest_ambulance", "hospital_capacity", "icu_availability",
    "emergency_availability", "time_of_day", "location_context", "route_eta_minutes",
]
CLASSES = ["LOW", "HIGH", "CRITICAL"]
TRAFFIC_MAP = {"GREEN": 0.0, "YELLOW": 1.0, "ORANGE": 2.0, "RED": 3.0}
ACCIDENT_MAP = {"general": 0.0, "trauma": 1.0, "cardiac": 2.0, "fire": 3.0}

_model_cache: dict[str, Any] | None = None
_ort_cache: Any = None
_runtime_cache: dict[str, Any] | None = None


def _load_numpy_model() -> dict[str, Any]:
    global _model_cache
    if _model_cache is None:
        data = np.load(MODEL_PATH)
        _model_cache = {
            "mean": data["mean"].astype(np.float32),
            "scale": data["scale"].astype(np.float32),
            "coef": data["coef"].astype(np.float32),
            "intercept": data["intercept"].astype(np.float32),
            "classes": data["classes"].astype(np.int64),
        }
    return _model_cache


def _try_onnx_runtime():
    global _ort_cache
    if _ort_cache is not None:
        return _ort_cache
    try:
        import onnxruntime as ort  # optional dependency
        available = list(ort.get_available_providers())
        preferred = "QNNExecutionProvider" if "QNNExecutionProvider" in available else "CPUExecutionProvider"
        providers = [preferred]
        if preferred != "CPUExecutionProvider" and "CPUExecutionProvider" in available:
            providers.append("CPUExecutionProvider")
        session = ort.InferenceSession(str(ONNX_PATH), providers=providers)
        _ort_cache = (ort, session, preferred, available)
        return _ort_cache
    except Exception:
        _ort_cache = False
        return None


def runtime_status() -> dict[str, Any]:
    global _runtime_cache
    if _runtime_cache is not None:
        return dict(_runtime_cache)
    target = "Qualcomm QNN / Snapdragon NPU"
    ort_info = _try_onnx_runtime()
    if ort_info:
        _, session, provider, available = ort_info
        active = session.get_providers()[0] if session.get_providers() else provider
        _runtime_cache = {
            "model": "emergency_risk_model",
            "model_format": "ONNX",
            "runtime": "ONNX Runtime",
            "provider": active,
            "qnn_available": "QNNExecutionProvider" in available,
            "available_providers": available,
            "target_device": target,
            "verified_on_current_device": "QNNExecutionProvider" in available and active == "QNNExecutionProvider",
            "platform": platform.platform(),
        }
    else:
        _runtime_cache = {
            "model": "emergency_risk_model",
            "model_format": "NPZ + NumPy fallback",
            "runtime": "Local NumPy fallback",
            "provider": "NUMPY_LOCAL_FALLBACK",
            "qnn_available": False,
            "available_providers": [],
            "target_device": target,
            "verified_on_current_device": False,
            "platform": platform.platform(),
        }
    return dict(_runtime_cache)


def _condition_features(condition: str) -> dict[str, float]:
    text = (condition or "").lower()
    word_counts = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
    unconscious = 0
    for word, count in word_counts.items():
        if f"{word} unconscious" in text or f"{word} unresponsive" in text:
            unconscious = max(unconscious, count)
    if unconscious == 0 and any(k in text for k in ("unconscious", "unresponsive", "not responding")):
        unconscious = 1
    critical = 0
    for word, count in word_counts.items():
        if f"{word} critical" in text:
            critical = max(critical, count)
    if critical == 0 and any(k in text for k in ("cardiac arrest", "not breathing", "severe bleeding", "major trauma", "critical")):
        critical = 1
    fire = 1 if "fire" in text or "burn" in text else 0
    if any(k in text for k in ("cardiac", "chest pain")):
        accident = "cardiac"
    elif fire:
        accident = "fire"
    elif any(k in text for k in ("accident", "trauma", "fracture", "injury", "bleeding")):
        accident = "trauma"
    else:
        accident = "general"
    severity = 1.0 if critical or unconscious else (0.65 if "severe" in text else 0.35)
    return {
        "unconscious_count": float(unconscious),
        "critical_count": float(critical),
        "fire_present": float(fire),
        "accident_type": ACCIDENT_MAP[accident],
        "injury_severity": severity,
    }


def build_features(payload: dict[str, Any]) -> tuple[np.ndarray, dict[str, float]]:
    incident = payload.get("incident") or payload
    traffic_name = str(payload.get("traffic") or incident.get("traffic") or "GREEN").upper()
    condition = str(incident.get("patient_condition") or incident.get("condition") or "")
    cf = _condition_features(condition)
    patients = float(incident.get("patient_count") or incident.get("number_of_patients") or 1)
    severity = str(incident.get("severity") or "moderate").lower()
    if severity == "critical":
        cf["injury_severity"] = max(cf["injury_severity"], 0.9)
    elif severity == "moderate":
        cf["injury_severity"] = max(cf["injury_severity"], 0.6)

    fleet = payload.get("fleet") or []
    hospitals = payload.get("hospitals") or []
    ambulance_distance = float(payload.get("distance_to_nearest_ambulance") or 5.0)
    if fleet:
        vals = []
        lat = incident.get("latitude"); lon = incident.get("longitude")
        if lat is not None and lon is not None:
            for a in fleet[:30]:
                if a.get("latitude") is not None and a.get("longitude") is not None:
                    dlat = float(a["latitude"]) - float(lat); dlon = float(a["longitude"]) - float(lon)
                    vals.append(math.sqrt(dlat*dlat + dlon*dlon) * 111.0)
        if vals:
            ambulance_distance = min(vals)

    beds = [float(h.get("available_beds")) for h in hospitals if h.get("available_beds") is not None]
    hospital_capacity = 100.0 - min(float(np.mean(beds)) if beds else 90.0, 100.0)
    icu = 1.0 if any(h.get("icu_available") in (True, "True", "true") for h in hospitals) else 0.0
    emergency = 1.0 if any(h.get("emergency_available") in (True, "True", "true") for h in hospitals) else 0.0
    route_eta = float(payload.get("route_eta_minutes") or 8.0)
    location = str(incident.get("label") or incident.get("location") or "Mumbai").lower()
    location_context = 1.0 if any(k in location for k in ("bandra", "dadar", "worli", "sion", "andheri", "mumbai")) else 0.0
    road_block = float(payload.get("road_block_probability") if payload.get("road_block_probability") is not None else (0.85 if traffic_name == "RED" else 0.45 if traffic_name == "ORANGE" else 0.2 if traffic_name == "YELLOW" else 0.08))
    values = {
        "number_of_patients": min(max(patients, 1), 10),
        **cf,
        "traffic_level": TRAFFIC_MAP.get(traffic_name, 0.0),
        "road_block_probability": min(max(road_block, 0), 1),
        "distance_to_nearest_ambulance": min(max(ambulance_distance, 0), 50),
        "hospital_capacity": min(max(hospital_capacity, 0), 100),
        "icu_availability": icu,
        "emergency_availability": emergency,
        "time_of_day": float(payload.get("time_of_day", 14)),
        "location_context": location_context,
        "route_eta_minutes": min(max(route_eta, 0), 60),
    }
    x = np.array([[values[f] for f in FEATURES]], dtype=np.float32)
    return x, values


def _numpy_predict(x: np.ndarray):
    m = _load_numpy_model()
    xs = (x - m["mean"]) / np.where(m["scale"] == 0, 1, m["scale"])
    logits = xs @ m["coef"].T + m["intercept"]
    logits = logits - np.max(logits, axis=1, keepdims=True)
    p = np.exp(logits); p /= np.sum(p, axis=1, keepdims=True)
    return p[0]


def _predict(x: np.ndarray):
    ort_info = _try_onnx_runtime()
    if ort_info:
        _, session, provider, _ = ort_info
        try:
            out = session.run(None, {session.get_inputs()[0].name: x})[0][0]
            return np.asarray(out, dtype=np.float32), provider
        except Exception:
            pass
    return _numpy_predict(x), "NUMPY_LOCAL_FALLBACK"


def analyze_incident(payload: dict[str, Any]) -> dict[str, Any]:
    x, values = build_features(payload)
    probabilities, provider = _predict(x)
    probabilities = np.asarray(probabilities, dtype=np.float32)
    probabilities = probabilities / max(float(probabilities.sum()), 1e-8)
    idx = int(np.argmax(probabilities))
    priority = CLASSES[idx]
    risk_score = float(np.clip(probabilities[1] * 0.55 + probabilities[2] * 1.0, 0, 1))
    confidence = float(np.max(probabilities))

    # Explain using the learned critical-class weights, not a hardcoded phrase list.
    m = _load_numpy_model()
    scaled = (x[0] - m["mean"]) / np.where(m["scale"] == 0, 1, m["scale"])
    critical_idx = int(np.where(m["classes"] == 2)[0][0]) if 2 in m["classes"] else -1
    contrib = []
    if critical_idx >= 0:
        for i, name in enumerate(FEATURES):
            c = float(scaled[i] * m["coef"][critical_idx, i])
            contrib.append((abs(c), c, name, float(values[name])))
    contrib.sort(reverse=True)
    factors = []
    labels = {
        "number_of_patients": "multiple casualties",
        "unconscious_count": "unconscious patient signal",
        "critical_count": "critical-condition signal",
        "injury_severity": "high injury-severity signal",
        "fire_present": "fire/burn hazard signal",
        "traffic_level": "elevated traffic",
        "road_block_probability": "road disruption risk",
        "distance_to_nearest_ambulance": "ambulance proximity constraint",
        "hospital_capacity": "hospital capacity context",
        "icu_availability": "ICU availability",
        "route_eta_minutes": "route ETA",
    }
    for _, c, name, _ in contrib[:6]:
        if abs(c) < 0.08: continue
        factors.append({"feature": name, "effect": "increases" if c > 0 else "reduces", "evidence": labels.get(name, name)})
    return {
        "risk_score": round(risk_score, 4),
        "risk_percent": round(risk_score * 100, 1),
        "priority": priority,
        "confidence": round(confidence, 4),
        "confidence_percent": round(confidence * 100, 1),
        "probabilities": {CLASSES[i]: round(float(probabilities[i]), 4) for i in range(len(CLASSES))},
        "factors": factors,
        "recommended_action": "Immediate response" if priority == "CRITICAL" else "Priority response" if priority == "HIGH" else "Standard response",
        "inference_provider": provider,
        "model_name": "ResQMesh Emergency Risk v1 (multinomial logistic regression)",
        "model_format": "ONNX when ONNX Runtime is available; NumPy fallback otherwise",
        "target": "Qualcomm QNN / Snapdragon NPU",
        "qnn_verified": provider == "QNNExecutionProvider",
        "features": values,
    }
