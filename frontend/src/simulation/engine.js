/**
 * SimulationEngine -- the single source of truth for the Live Simulation
 * page (spec section 3). Everything the UI shows (map markers, ETA,
 * timeline, hospital card) is read from ONE snapshot object produced here;
 * nothing is faked independently in a component.
 *
 * Real vs. simulated, explicitly:
 *   REAL (from person2_backend, real Mumbai OSM road graph):
 *     - ambulance/hospital selection + reasoning
 *     - road-following route coordinates (A*)
 *     - road closures + alternate routing when a segment fails
 *   SIMULATED (no live feed exists for any of this in the real world either):
 *     - ambulance physical movement along the real route (interpolation/physics)
 *     - GPS actual-vs-reported noise
 *     - traffic congestion schedule
 *     - hospital-capacity data-age / staleness clock
 *
 * The whole thing is deterministic for a given (seed, scenario, incident):
 * all "random" elements are drawn from one seeded RNG stream (rng.js), and
 * all scenario timing is a fixed fraction-of-ETA schedule (scenarios.js),
 * not per-frame randomness.
 */

import { SeededRandom } from "./rng.js";
import { cumulativeDistances, pathLengthMeters, pointAtDistance, haversineMeters, offsetMeters } from "./geo.js";
import { sampleGpsReading, GPS_QUALITY } from "./gpsModel.js";
import { TRAFFIC_LEVEL, trafficLevelAt, TRAFFIC_SPEED_MULTIPLIER } from "./trafficModel.js";
import { SCENARIOS, HOSPITAL_STALE_THRESHOLD_SEC, BASE_SPEED_KPH, ACCEL_KPH_PER_SEC, DECEL_KPH_PER_SEC } from "./scenarios.js";
import * as backend from "./backendClient.js";

const GPS_SAMPLE_INTERVAL_SEC = 2;
const TRAIL_MIN_SPACING_M = 25;
const HOSPITAL_REASSESS_DELAY_SEC = 4;

function nowEventId() {
  return `${Date.now().toString(36)}-${Math.floor(Math.random() * 1e6).toString(36)}`;
}

export const PHASE = {
  IDLE: "IDLE",
  DISPATCHING: "DISPATCHING",
  EN_ROUTE_TO_INCIDENT: "EN_ROUTE_TO_INCIDENT",
  AT_INCIDENT: "AT_INCIDENT",
  EN_ROUTE_TO_HOSPITAL: "EN_ROUTE_TO_HOSPITAL",
  ARRIVED: "ARRIVED",
  ERROR: "ERROR",
};

function freshState(seed, scenarioId) {
  return {
    simTimeSec: 0,
    running: false,
    paused: false,
    speed: 1,
    seed,
    scenarioId,
    phase: PHASE.IDLE,
    offlineFallback: false,
    incident: null,
    decision: null,
    ambulance: null,
    gps: { quality: GPS_QUALITY.GOOD, accuracyM: 8, actual: null, reported: null },
    traffic: { level: TRAFFIC_LEVEL.GREEN },
    route: null,
    hospital: null,
    fleet: [],
    events: [],
    lastError: null,
    ai: { status: "IDLE", riskScore: null, priority: null, confidence: null, factors: [], provider: "—", target: "Qualcomm QNN / Snapdragon NPU", modelName: "—", recommendedAction: "—", lastTrigger: null, qnnVerified: false },
  };
}

export class SimulationEngine {
  constructor({ seed = 104, scenarioId = "NORMAL_RESPONSE" } = {}) {
    this.state = freshState(seed, scenarioId);
    this.rng = new SeededRandom(seed);
    this._listeners = new Set();
    this._legRuntime = null; // per-leg mutable runtime (not part of public snapshot directly, mirrored into state.route)
    this._lastIncidentRequest = null;
    this._gpsAccum = 0;
    this._rerouting = false;
    this._routeFailureTriggered = false;
    this._hospitalStaleTriggered = false;
    this._hospitalsCache = null;
    this._hospitalWasReassigned = false;
    this._hospitalPendingRoute = null;
    this._incidentNode = null;
    this._hospitalNode = null;
    this._aiRequestInFlight = false;
    this._aiSequence = 0;
  }

  // ---- pub/sub -----------------------------------------------------------
  subscribe(fn) {
    this._listeners.add(fn);
    return () => this._listeners.delete(fn);
  }

  _emit() {
    const snapshot = this.state;
    for (const fn of this._listeners) fn(snapshot);
  }

  _setState(patch) {
    this.state = { ...this.state, ...patch };
    this._emit();
  }

  _logEvent(type, message, { severity = "info", entityId = null, metadata = null } = {}) {
    const ev = {
      id: nowEventId(),
      tSec: this.state.simTimeSec,
      type,
      severity,
      message,
      entityId,
      metadata,
    };
    this.state = { ...this.state, events: [...this.state.events, ev] };
    this._emit();
  }

  // ---- controls -----------------------------------------------------------
  setSpeed(speed) {
    this._setState({ speed });
  }

  setScenario(scenarioId) {
    if (!SCENARIOS[scenarioId]) return;
    this._setState({ scenarioId });
  }

  setSeed(seed) {
    this.rng = new SeededRandom(seed);
    this._setState({ seed });
  }

  pause() {
    this._setState({ paused: true });
  }

  resume() {
    if (this.state.phase === PHASE.IDLE) return;
    this._setState({ paused: false, running: true });
  }

  /** Re-run the exact same incident from t=0 with the same seed/scenario -- must reproduce the same event sequence. */
  async restart() {
    if (!this._lastIncidentRequest) return;
    await backend.clearRoadClosures().catch(() => {});
    this.rng.reset();
    this._routeFailureTriggered = false;
    this._hospitalStaleTriggered = false;
    this._gpsAccum = 0;
    this._rerouting = false;
    this._hospitalWasReassigned = false;
    this._hospitalPendingRoute = null;
    const { seed, scenarioId } = this.state;
    this.state = freshState(seed, scenarioId);
    this._emit();
    await this.startIncident(this._lastIncidentRequest, { isRestart: true });
  }

  // ---- incident lifecycle --------------------------------------------------
  async startIncident(incidentInput, { isRestart = false } = {}) {
    if (!isRestart) {
      await backend.clearRoadClosures().catch(() => {});
      this._routeFailureTriggered = false;
      this._hospitalStaleTriggered = false;
      this._hospitalWasReassigned = false;
      this._hospitalPendingRoute = null;
      this._gpsAccum = 0;
      this._rerouting = false;
    }
    this._lastIncidentRequest = incidentInput;
    this._setState({
      phase: PHASE.DISPATCHING,
      running: true,
      paused: false,
      incident: {
        id: incidentInput.incident_id,
        lat: incidentInput.latitude,
        lon: incidentInput.longitude,
        severity: incidentInput.severity,
        condition: incidentInput.patient_condition,
        label: incidentInput.label || "Medical Emergency",
        patientCount: Number(incidentInput.patient_count || incidentInput.number_of_patients || 1),
      },
    });
    this._logEvent("INCIDENT_CREATED", `${(incidentInput.label || "Medical emergency")} reported (${incidentInput.severity.toUpperCase()})`, {
      severity: incidentInput.severity === "critical" ? "critical" : "warning",
    });

    let dispatchResp;
    try {
      dispatchResp = await backend.dispatchEmergency(incidentInput);
    } catch (err) {
      this._setState({ phase: PHASE.ERROR, running: false, lastError: String(err.message || err) });
      this._logEvent("DISPATCH_FAILED", `Dispatch backend unreachable: ${err.message || err}`, { severity: "critical" });
      return;
    }

    if (!dispatchResp.ambulance || !dispatchResp.hospital || !dispatchResp.routes?.ambulance_to_incident?.found) {
      this._setState({ phase: PHASE.ERROR, running: false, lastError: "No feasible ambulance/hospital/route for this incident." });
      this._logEvent("DISPATCH_FAILED", "No feasible ambulance, hospital, or route was found for this incident.", { severity: "critical" });
      return;
    }

    this._setState({ decision: dispatchResp.decision });
    this._logEvent(
      "AMBULANCE_DISPATCHED",
      `${dispatchResp.ambulance.ambulance_id} dispatched (${dispatchResp.ambulance.type}). ${dispatchResp.decision.ambulance_reason}`,
      { entityId: dispatchResp.ambulance.ambulance_id }
    );
    this._logEvent(
      "HOSPITAL_SELECTED",
      `${dispatchResp.hospital.name} selected as destination. ${dispatchResp.decision.hospital_reason}`,
      { entityId: dispatchResp.hospital.hospital_id }
    );

    const incidentNode = dispatchResp.pickup.graph_node;
    let hospitalNode = null;
    try {
      const hospitals = await backend.listHospitals();
      this._hospitalsCache = hospitals;
      const h = hospitals.find((x) => x.hospital_id === dispatchResp.hospital.hospital_id);
      hospitalNode = h ? Number(h.graph_node) : null;
      this._setState({
        hospital: h
          ? {
              id: h.hospital_id,
              name: h.name,
              lat: Number(h.latitude),
              lon: Number(h.longitude),
              node: Number(h.graph_node),
              availableBeds: Number(h.available_beds),
              icuAvailable: h.icu_available === true || h.icu_available === "True",
              emergencyAvailable: h.emergency_available === true || h.emergency_available === "True",
              status: h.status,
              lastUpdatedSimSec: 0,
              stale: false,
            }
          : null,
      });
    } catch (err) {
      this._logEvent("WARNING", `Could not fetch full hospital directory: ${err.message || err}`, { severity: "warning" });
    }

    // Populate a handful of nearby AVAILABLE ambulances for map/fleet context (spec section 16).
    try {
      const fleet = await backend.listAmbulances();
      const nearby = fleet
        .filter((a) => a.status === "AVAILABLE" && a.ambulance_id !== dispatchResp.ambulance.ambulance_id)
        .map((a) => ({
          id: a.ambulance_id,
          lat: Number(a.latitude),
          lon: Number(a.longitude),
          status: a.status,
          type: a.ambulance_type,
        }))
        .sort((a, b) => haversineMeters([incidentResp_lon(dispatchResp), incidentResp_lat(dispatchResp)], [a.lon, a.lat]) -
          haversineMeters([incidentResp_lon(dispatchResp), incidentResp_lat(dispatchResp)], [b.lon, b.lat]))
        .slice(0, 18);
      this._setState({ fleet: nearby });
    } catch (err) {
      // Non-fatal -- fleet context is a nice-to-have overlay, not required for the core flow.
    }

    this._setState({
      ambulance: {
        id: dispatchResp.ambulance.ambulance_id,
        type: dispatchResp.ambulance.type,
        node: null,
        position: dispatchResp.routes.ambulance_to_incident.coordinates[0],
        headingDeg: 0,
        speedKph: 0,
        traveledTrail: [],
      },
    });

    this._beginLeg({
      legName: "TO_INCIDENT",
      route: dispatchResp.routes.ambulance_to_incident,
      originNode: dispatchResp.ambulance ? null : null,
      destNode: incidentNode,
      phase: PHASE.EN_ROUTE_TO_INCIDENT,
    });
    this._hospitalPendingRoute = dispatchResp.routes.incident_to_hospital;
    this._incidentNode = incidentNode;
    this._hospitalNode = hospitalNode;

    this._logEvent("AMBULANCE_STARTED", `${dispatchResp.ambulance.ambulance_id} en route to incident. ETA ${dispatchResp.routes.ambulance_to_incident.duration_minutes.toFixed(1)} min.`);
    // Real local model inference happens after deterministic dispatch has produced
    // the current operational context. AI can recommend risk/priority, but it
    // never selects or overrides the ambulance, route, or hospital.
    this._requestAIReassessment("Initial incident assessment");
  }

  async _requestAIReassessment(trigger) {
    const requestId = ++this._aiSequence;
    this._setState({ ai: { ...this.state.ai, status: "ANALYZING", lastTrigger: trigger } });
    try {
      const result = await backend.analyzeAI({
        incident: {
          incident_id: this.state.incident?.id,
          latitude: this.state.incident?.lat,
          longitude: this.state.incident?.lon,
          severity: this.state.incident?.severity,
          patient_condition: this.state.incident?.condition,
          patient_count: this.state.incident?.patientCount || 1,
          label: this.state.incident?.label,
        },
        traffic: this.state.traffic?.level || "GREEN",
        route_eta_minutes: this.state.route?.etaMinutes || 8,
        road_block_probability: this.state.traffic?.level === "RED" ? 0.85 : this.state.traffic?.level === "ORANGE" ? 0.55 : this.state.traffic?.level === "YELLOW" ? 0.30 : 0.08,
        fleet: this.state.fleet || [],
        hospitals: this._hospitalsCache || [],
      });
      if (requestId !== this._aiSequence) return;
      this._setState({
        ai: {
          status: "READY",
          riskScore: result.risk_score,
          priority: result.priority,
          confidence: result.confidence,
          factors: result.factors || [],
          provider: result.inference_provider || "UNKNOWN",
          target: result.target || "Qualcomm QNN / Snapdragon NPU",
          modelName: result.model_name || "ResQMesh Emergency Risk",
          recommendedAction: result.recommended_action || "—",
          lastTrigger: trigger,
          qnnVerified: Boolean(result.qnn_verified),
          probabilities: result.probabilities || {},
        },
      });
      this._logEvent("AI_REASSESSMENT", `Local AI updated risk to ${result.risk_percent}% (${result.priority}) after ${trigger.toLowerCase()}.`, {
        severity: result.priority === "CRITICAL" ? "critical" : result.priority === "HIGH" ? "warning" : "info",
        metadata: { provider: result.inference_provider, confidence: result.confidence_percent },
      });
    } catch (err) {
      if (requestId !== this._aiSequence) return;
      this._setState({ ai: { ...this.state.ai, status: "ERROR", provider: "UNAVAILABLE", lastTrigger: trigger } });
      this._logEvent("AI_INFERENCE_WARNING", `Local AI unavailable; deterministic response remains active (${err.message || err}).`, { severity: "warning" });
    }
  }

  _beginLeg({ legName, route, destNode, phase }) {
    const coords = route.coordinates;
    const cum = cumulativeDistances(coords);
    this._legRuntime = {
      legName,
      nodePath: route.node_path,
      destNode,
      startSimSec: this.state.simTimeSec,
      etaMinutesAtStart: route.duration_minutes,
      currentSpeedKph: 0,
    };
    this._routeFailureTriggered = false;
    this._setState({
      phase,
      route: {
        legName,
        coordinates: coords,
        cumDistances: cum,
        totalDistanceM: pathLengthMeters(cum),
        progressM: 0,
        nodePath: route.node_path,
        destNode,
        etaMinutes: route.duration_minutes,
        distanceKm: route.distance_km,
        failedSegment: null,
        alternativeNote: null,
      },
    });
  }

  // ---- main tick, called every animation frame by the React hook --------
  tick(dtRealMs) {
    if (!this.state.running || this.state.paused) return;
    if (this.state.phase !== PHASE.EN_ROUTE_TO_INCIDENT && this.state.phase !== PHASE.EN_ROUTE_TO_HOSPITAL) return;

    const dtSim = (dtRealMs / 1000) * this.state.speed;
    const simTimeSec = this.state.simTimeSec + dtSim;
    const legElapsedSec = simTimeSec - this._legRuntime.startSimSec;
    const legEtaSec = Math.max(this._legRuntime.etaMinutesAtStart * 60, 5);
    const legFrac = Math.min(legElapsedSec / legEtaSec, 1.5);

    const scenario = SCENARIOS[this.state.scenarioId];

    // --- traffic ---
    const trafficScheduleSec = scenario.trafficSchedule.map((e) => ({ atSec: e.atFrac * legEtaSec, level: e.level }));
    const newLevel = trafficLevelAt(legElapsedSec, trafficScheduleSec);
    if (newLevel !== this.state.traffic.level) {
      const trafficMessage = `Traffic ${newLevel === TRAFFIC_LEVEL.GREEN ? "cleared" : "increased"} to ${newLevel}.`;
      this._logEvent("TRAFFIC_CHANGED", trafficMessage, {
        severity: newLevel === TRAFFIC_LEVEL.RED ? "warning" : "info",
      });
      this.state = { ...this.state, traffic: { level: newLevel } };
      this._requestAIReassessment(`traffic changed to ${newLevel}`);
    } else {
      this.state = { ...this.state, traffic: { level: newLevel } };
    }

    // --- GPS quality schedule (based on the to-incident leg only, per spec) ---
    if (this._legRuntime.legName === "TO_INCIDENT" && (scenario.gpsDegradeAtFrac || scenario.gpsPoorAtFrac)) {
      let targetQuality = GPS_QUALITY.GOOD;
      if (scenario.gpsPoorAtFrac != null && legFrac >= scenario.gpsPoorAtFrac) targetQuality = GPS_QUALITY.POOR;
      else if (scenario.gpsDegradeAtFrac != null && legFrac >= scenario.gpsDegradeAtFrac) targetQuality = GPS_QUALITY.DEGRADED;
      if (scenario.gpsRecoverAtFrac != null && legFrac >= scenario.gpsRecoverAtFrac) targetQuality = GPS_QUALITY.GOOD;
      if (targetQuality !== this.state.gps.quality) {
        this._logEvent(
          "GPS_DEGRADED",
          targetQuality === GPS_QUALITY.GOOD ? "GPS accuracy recovered." : `GPS accuracy degraded to ${targetQuality}.`,
          { severity: targetQuality === GPS_QUALITY.POOR ? "warning" : "info" }
        );
        this.state = { ...this.state, gps: { ...this.state.gps, quality: targetQuality } };
      }
    }

    // --- route failure trigger ---
    if (
      !this._routeFailureTriggered &&
      scenario.routeFailureAtFrac != null &&
      legFrac >= scenario.routeFailureAtFrac &&
      !this._rerouting
    ) {
      this._routeFailureTriggered = true;
      this._triggerRouteFailure();
    }

    // --- hospital staleness trigger (evaluated once, during the to-incident leg) ---
    if (
      this._legRuntime.legName === "TO_INCIDENT" &&
      !this._hospitalStaleTriggered &&
      scenario.hospitalStaleAtFrac != null &&
      legFrac >= scenario.hospitalStaleAtFrac
    ) {
      this._hospitalStaleTriggered = true;
      this._triggerHospitalStaleness(legElapsedSec);
    }

    // --- movement physics ---
    const baseSpeed = BASE_SPEED_KPH[this.state.ambulance.type] || 40;
    const trafficMult = TRAFFIC_SPEED_MULTIPLIER[newLevel];
    const targetSpeedKph = this._rerouting ? 2 : baseSpeed * trafficMult;
    const cur = this._legRuntime.currentSpeedKph;
    const rate = targetSpeedKph > cur ? ACCEL_KPH_PER_SEC : DECEL_KPH_PER_SEC;
    const nextSpeed = cur + Math.sign(targetSpeedKph - cur) * Math.min(Math.abs(targetSpeedKph - cur), rate * dtSim);
    this._legRuntime.currentSpeedKph = Math.max(0, nextSpeed);

    const metersPerSec = (this._legRuntime.currentSpeedKph * 1000) / 3600;
    let progressM = this.state.route.progressM + metersPerSec * dtSim;
    const totalM = this.state.route.totalDistanceM;
    let arrived = false;
    if (progressM >= totalM) {
      progressM = totalM;
      arrived = true;
    }

    const { position, headingDeg, segmentIndex } = pointAtDistance(
      this.state.route.coordinates,
      this.state.route.cumDistances,
      progressM
    );

    // --- GPS sampling (throttled) ---
    this._gpsAccum += dtSim;
    let gpsPatch = {};
    if (this._gpsAccum >= GPS_SAMPLE_INTERVAL_SEC || !this.state.gps.actual) {
      this._gpsAccum = 0;
      const { accuracyM, dxMeters, dyMeters } = sampleGpsReading(this.rng, this.state.gps.quality);
      const reported = offsetMeters(position, dxMeters, dyMeters);
      gpsPatch = { gps: { ...this.state.gps, actual: position, reported, accuracyM } };
    } else {
      gpsPatch = { gps: { ...this.state.gps, actual: position } };
    }

    // --- trail (throttled by distance) ---
    const trail = this.state.ambulance.traveledTrail;
    const last = trail[trail.length - 1];
    const shouldAppend = !last || haversineMeters(last, position) >= TRAIL_MIN_SPACING_M;

    const remainingKm = (totalM - progressM) / 1000;
    // Only recompute ETA off the live speed once the ambulance is actually
    // moving at a reasonable pace -- while nearly stopped (e.g. decelerating
    // into a reroute), dividing by a near-zero speed would spike the ETA to
    // an absurd number, so keep showing the last sane estimate instead.
    const MIN_SPEED_FOR_ETA_KPH = 10;
    const etaMin =
      this._legRuntime.currentSpeedKph > MIN_SPEED_FOR_ETA_KPH
        ? (remainingKm / this._legRuntime.currentSpeedKph) * 60
        : this.state.route.etaMinutes;

    this.state = {
      ...this.state,
      simTimeSec,
      ...gpsPatch,
      route: { ...this.state.route, progressM, distanceKmRemaining: remainingKm, etaMinutes: etaMin, segmentIndex },
      ambulance: {
        ...this.state.ambulance,
        position,
        headingDeg,
        speedKph: this._legRuntime.currentSpeedKph,
        traveledTrail: shouldAppend ? [...trail, position] : trail,
      },
    };
    this._emit();

    if (arrived) this._onLegArrived();
  }

  async _onLegArrived() {
    if (this._legRuntime.legName === "TO_INCIDENT") {
      this._setState({ phase: PHASE.AT_INCIDENT });
      this._logEvent("AMBULANCE_AT_INCIDENT", `${this.state.ambulance.id} arrived on scene.`);
      const hospitalRoute = this._hospitalPendingRoute;
      const hospNode = this.state.hospital ? this.state.hospital.node : this._hospitalNode;
      if (hospitalRoute && hospitalRoute.found && !this._hospitalWasReassigned) {
        this._beginLeg({ legName: "TO_HOSPITAL", route: hospitalRoute, destNode: hospNode, phase: PHASE.EN_ROUTE_TO_HOSPITAL });
        this._logEvent("AMBULANCE_DEPARTED_SCENE", `Transporting patient to ${this.state.hospital?.name || "destination hospital"}. ETA ${hospitalRoute.duration_minutes.toFixed(1)} min.`);
      } else if (hospNode != null) {
        // Hospital was reassigned while en route -- compute a fresh real route now.
        try {
          const result = await backend.rerouteAround(this._incidentNode, hospNode);
          if (result.found) {
            this._beginLeg({ legName: "TO_HOSPITAL", route: result, destNode: hospNode, phase: PHASE.EN_ROUTE_TO_HOSPITAL });
            this._logEvent("AMBULANCE_DEPARTED_SCENE", `Transporting patient to ${this.state.hospital?.name || "reassigned hospital"}. ETA ${result.duration_minutes.toFixed(1)} min.`);
          } else {
            this._setState({ phase: PHASE.ERROR, running: false, lastError: "No route found from incident to reassigned hospital." });
          }
        } catch (err) {
          this._setState({ phase: PHASE.ERROR, running: false, lastError: String(err.message || err) });
        }
      }
    } else {
      this._setState({ running: false, phase: PHASE.ARRIVED });
      this._logEvent("AMBULANCE_ARRIVED", `${this.state.ambulance.id} arrived at ${this.state.hospital?.name || "hospital"}. Response complete.`, { severity: "success" });
    }
  }

  // ---- route failure / reroute -------------------------------------------
  async _triggerRouteFailure() {
    const nodePath = this._legRuntime.nodePath;
    const startIdx = Math.min((this.state.route.segmentIndex || 0) + 2, nodePath.length - 2);
    if (startIdx < 0 || !nodePath[startIdx] || !nodePath[startIdx + 1]) return;

    const a = this.state.route.coordinates[startIdx];
    const b = this.state.route.coordinates[startIdx + 1];

    this._rerouting = true;
    this.state = { ...this.state, route: { ...this.state.route, failedSegment: { a, b } } };
    this._logEvent("ROUTE_FAILED", "Road segment ahead is unavailable (closure/incident). Calculating alternative route...", { severity: "warning" });

    const destNode = this._legRuntime.destNode;
    // A single blocked directed edge can occasionally sit on a genuine
    // graph bottleneck (a dead-end stub with no parallel street). Rather
    // than surface that as a permanent failure, try a small number of
    // nearby candidate edges further along the path -- reopening any that
    // didn't help -- before concluding no alternative exists.
    const MAX_ATTEMPTS = 5;
    let result = null;
    let closedU = null;
    let closedV = null;
    for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
      const idx = Math.min(startIdx + attempt * 2, nodePath.length - 2);
      const u = nodePath[idx];
      const v = nodePath[idx + 1];
      if (u == null || v == null) break;
      try {
        await backend.closeRoadEdge(u, v);
        closedU = u;
        closedV = v;
        const originNode = nodePath[idx];
        const attemptResult = await backend.rerouteAround(originNode, destNode);
        if (attemptResult.found) {
          result = attemptResult;
          break;
        }
        // that edge didn't yield an alternative -- leave it closed (still a
        // realistic accumulating closure) and try the next candidate.
      } catch (err) {
        this._logEvent("WARNING", `Closure attempt failed: ${err.message || err}`, { severity: "warning" });
        break;
      }
    }

    try {
      if (result && result.found) {
        const newCum = cumulativeDistances(result.coordinates);
        const previousEta = this.state.route.etaMinutes;
        this.state = {
          ...this.state,
          route: {
            ...this.state.route,
            coordinates: result.coordinates,
            cumDistances: newCum,
            totalDistanceM: pathLengthMeters(newCum),
            progressM: 0,
            nodePath: result.node_path,
            etaMinutes: result.duration_minutes,
            distanceKm: result.distance_km,
            alternativeNote: `Previous ETA ${previousEta.toFixed(1)} min -> new ETA ${result.duration_minutes.toFixed(1)} min (blocked segment).`,
          },
        };
        this._legRuntime.nodePath = result.node_path;
        this._legRuntime.startSimSec = this.state.simTimeSec;
        this._legRuntime.etaMinutesAtStart = result.duration_minutes;
        this._logEvent(
          "ROUTE_RECALCULATED",
          `Alternative route calculated. Previous ETA ${previousEta.toFixed(1)} min, new ETA ${result.duration_minutes.toFixed(1)} min.`,
          { severity: "info" }
        );
        this._requestAIReassessment("road closure and route failure");
      } else {
        this._logEvent("ROUTE_FAILURE_UNRESOLVED", "No alternative route could be found around the blocked segment.", { severity: "critical" });
      }
    } catch (err) {
      this._logEvent("ROUTE_FAILURE_UNRESOLVED", `Reroute request failed: ${err.message || err}`, { severity: "critical" });
    } finally {
      this._rerouting = false;
      this._emit();
    }
  }

  // ---- hospital staleness / reassessment ---------------------------------
  _triggerHospitalStaleness(legElapsedSec) {
    if (!this.state.hospital) return;
    const dataAgeSec = HOSPITAL_STALE_THRESHOLD_SEC + 5;
    this.state = { ...this.state, hospital: { ...this.state.hospital, stale: true, dataAgeSec } };
    this._logEvent(
      "HOSPITAL_DATA_STALE",
      `${this.state.hospital.name} capacity data is stale (last updated ${Math.round(dataAgeSec)}s of simulated time ago).`,
      { severity: "warning" }
    );
    this._requestAIReassessment("hospital capacity data became stale");
    setTimeout(() => this._reassessHospital(), (HOSPITAL_REASSESS_DELAY_SEC * 1000) / Math.max(this.state.speed, 1));
  }

  async _reassessHospital() {
    this._logEvent("HOSPITAL_REASSESSED", "Checking hospital availability...");
    let hospitals = this._hospitalsCache;
    try {
      hospitals = await backend.listHospitals();
      this._hospitalsCache = hospitals;
    } catch (err) {
      this._logEvent("WARNING", `Could not refresh hospital directory: ${err.message || err}`, { severity: "warning" });
      if (!hospitals) return;
    }

    const incident = this.state.incident;
    const current = this.state.hospital;
    const eligible = hospitals.filter(
      (h) => h.status !== "FULL" && (h.emergency_available === true || h.emergency_available === "True")
    );
    if (!eligible.length) return;

    const scored = eligible.map((h) => {
      const distKm = haversineMeters([incident.lon, incident.lat], [Number(h.longitude), Number(h.latitude)]) / 1000;
      const bedsScore = Math.min(Number(h.available_beds) || 0, 20) / 20;
      const staleBonus = h.hospital_id === current.id ? -3.0 : 0; // penalize the now-stale current pick
      const score = bedsScore * 2 - distKm * 0.15 + staleBonus;
      return { h, score, distKm };
    });
    scored.sort((a, b) => b.score - a.score);
    const best = scored[0].h;

    if (best.hospital_id === current.id) {
      this._logEvent("HOSPITAL_REASSESSED", `${current.name} remains the best available destination after reassessment.`);
      this.state = { ...this.state, hospital: { ...current, stale: false, dataAgeSec: 0 } };
      this._emit();
      return;
    }

    const previousName = current.name;
    this._hospitalWasReassigned = true;
    this.state = {
      ...this.state,
      hospital: {
        id: best.hospital_id,
        name: best.name,
        lat: Number(best.latitude),
        lon: Number(best.longitude),
        node: Number(best.graph_node),
        availableBeds: Number(best.available_beds),
        icuAvailable: best.icu_available === true || best.icu_available === "True",
        emergencyAvailable: best.emergency_available === true || best.emergency_available === "True",
        status: best.status,
        lastUpdatedSimSec: this.state.simTimeSec,
        stale: false,
      },
    };
    this._logEvent(
      "HOSPITAL_CHANGED",
      `Destination updated: ${previousName} -> ${best.name} (reason: prior hospital's capacity data was stale; ${best.name} has ${best.available_beds} beds available).`,
      { severity: "warning" }
    );
    this._requestAIReassessment("hospital destination reassessed");

    // If we're already en route to the (old) hospital, splice a fresh real route to the new one right now.
    if (this.state.phase === PHASE.EN_ROUTE_TO_HOSPITAL) {
      try {
        const result = await backend.rerouteAround(this._incidentNode, Number(best.graph_node));
        if (result.found) {
          const newCum = cumulativeDistances(result.coordinates);
          this.state = {
            ...this.state,
            route: {
              ...this.state.route,
              coordinates: result.coordinates,
              cumDistances: newCum,
              totalDistanceM: pathLengthMeters(newCum),
              progressM: 0,
              nodePath: result.node_path,
              etaMinutes: result.duration_minutes,
              distanceKm: result.distance_km,
            },
          };
          this._legRuntime.nodePath = result.node_path;
          this._legRuntime.destNode = Number(best.graph_node);
          this._legRuntime.startSimSec = this.state.simTimeSec;
          this._legRuntime.etaMinutesAtStart = result.duration_minutes;
        }
      } catch (err) {
        this._logEvent("WARNING", `Could not compute route to reassigned hospital yet: ${err.message || err}`, { severity: "warning" });
      }
    } else {
      // Not yet en route to hospital -- the pending route will be recomputed in _onLegArrived().
      this._hospitalPendingRoute = null;
    }
    this._emit();
  }
}

// small helpers kept at module scope to avoid re-creating closures per tick
function incidentResp_lat(dispatchResp) {
  return dispatchResp.pickup.latitude;
}
function incidentResp_lon(dispatchResp) {
  return dispatchResp.pickup.longitude;
}
