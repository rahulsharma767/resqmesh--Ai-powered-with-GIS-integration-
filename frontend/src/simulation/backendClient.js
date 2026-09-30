/**
 * Thin fetch wrapper around person2_backend (the real Mumbai road-graph /
 * dispatch / hospital / ambulance / road-closure API). See
 * person2_backend/backend/app/main.py for the authoritative route list.
 *
 * Every response from this client is REAL backend data (real road routing,
 * real snapped hospital/ambulance node positions) -- it is only the ongoing
 * animation, GPS noise, traffic schedule and staleness clock layered on top
 * (in engine.js) that is simulated, and that is always clearly labeled as
 * such in the UI.
 */

const BASE_URL =
  (typeof import.meta !== "undefined" && import.meta.env && import.meta.env.VITE_PERSON2_API_URL) ||
  "http://localhost:8000";

async function request(path, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      ...options,
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`${options.method || "GET"} ${path} -> HTTP ${res.status}: ${body.slice(0, 200)}`);
    }
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

export async function checkHealth() {
  return request("/health");
}

export async function listHospitals() {
  const data = await request("/api/v1/hospitals");
  return data.hospitals || [];
}

export async function listAmbulances() {
  const data = await request("/api/v1/ambulances");
  return data.ambulances || [];
}

export async function getHospital(hospitalId) {
  return request(`/api/v1/hospitals/${encodeURIComponent(hospitalId)}`);
}

/**
 * Real dispatch decision: picks the best available ambulance + best
 * hospital using the backend's real scoring + real A* routing, for a given
 * incident lat/lon. This is the single call that drives spec sections
 * 16/17/19 (dispatch selection + reasoning) for the primary incident.
 */
export async function dispatchEmergency(incident) {
  return request("/api/v1/emergency/dispatch", {
    method: "POST",
    body: JSON.stringify(incident),
  });
}


export async function analyzeAI(payload) {
  return request("/api/ai/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  }, 8000);
}

export async function getAIStatus() {
  return request("/api/ai/status", {}, 5000);
}

export async function closeRoadEdge(u, v) {
  return request("/api/v1/roads/closures", {
    method: "POST",
    body: JSON.stringify({ u, v }),
  });
}

export async function clearRoadClosures() {
  return request("/api/v1/roads/closures", { method: "DELETE" });
}

export async function rerouteAround(originNode, destNode) {
  return request("/api/v1/roads/reroute", {
    method: "POST",
    body: JSON.stringify({ origin_node: originNode, destination_node: destNode }),
  });
}

export { BASE_URL };
