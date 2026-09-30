/**
 * Scenario presets (spec section 24).
 *
 * Every trigger is expressed as a FRACTION of the current leg's estimated
 * duration (0..1), not a fixed wall-clock second. The engine converts each
 * fraction to an actual simulation-second once it knows the real ETA for
 * the leg in progress (which depends on which real ambulance/hospital/route
 * the backend picked), so the same scenario behaves sensibly whether the
 * incident is 3 minutes or 15 minutes away.
 *
 * trafficSchedule: [{atFrac, level}] -- deterministic congestion timeline
 * gpsDegradeAtFrac / gpsPoorAtFrac: GPS quality step-downs
 * routeFailureAtFrac: triggers a blocked-segment + reroute event
 * hospitalStaleAtFrac: triggers hospital-capacity staleness + reassessment
 *   (evaluated once, during the ambulance->incident leg, so the
 *   already-selected hospital can still be swapped before pickup)
 */

import { TRAFFIC_LEVEL } from "./trafficModel.js";

export const SCENARIOS = {
  NORMAL_RESPONSE: {
    id: "NORMAL_RESPONSE",
    label: "Normal Response",
    description: "Clear roads, stable GPS, no failures. Baseline response.",
    trafficSchedule: [{ atFrac: 0, level: TRAFFIC_LEVEL.GREEN }],
    gpsDegradeAtFrac: null,
    gpsPoorAtFrac: null,
    routeFailureAtFrac: null,
    hospitalStaleAtFrac: null,
  },
  HEAVY_TRAFFIC: {
    id: "HEAVY_TRAFFIC",
    label: "Heavy Traffic",
    description: "Congestion builds through the response, slowing the ambulance and stretching ETA.",
    trafficSchedule: [
      { atFrac: 0, level: TRAFFIC_LEVEL.GREEN },
      { atFrac: 0.15, level: TRAFFIC_LEVEL.YELLOW },
      { atFrac: 0.35, level: TRAFFIC_LEVEL.ORANGE },
      { atFrac: 0.7, level: TRAFFIC_LEVEL.RED },
      { atFrac: 0.9, level: TRAFFIC_LEVEL.ORANGE },
    ],
    gpsDegradeAtFrac: null,
    gpsPoorAtFrac: null,
    routeFailureAtFrac: null,
    hospitalStaleAtFrac: null,
  },
  GPS_DEGRADATION: {
    id: "GPS_DEGRADATION",
    label: "GPS Degradation",
    description: "GPS accuracy deteriorates mid-journey (GOOD -> DEGRADED -> POOR) before recovering.",
    trafficSchedule: [{ atFrac: 0, level: TRAFFIC_LEVEL.GREEN }],
    gpsDegradeAtFrac: 0.25,
    gpsPoorAtFrac: 0.45,
    gpsRecoverAtFrac: 0.75,
    routeFailureAtFrac: null,
    hospitalStaleAtFrac: null,
  },
  ROUTE_FAILURE: {
    id: "ROUTE_FAILURE",
    label: "Route Failure",
    description: "A road segment ahead becomes unavailable; the engine closes it and computes a real alternate route.",
    trafficSchedule: [{ atFrac: 0, level: TRAFFIC_LEVEL.GREEN }],
    gpsDegradeAtFrac: null,
    gpsPoorAtFrac: null,
    routeFailureAtFrac: 0.35,
    hospitalStaleAtFrac: null,
  },
  STALE_HOSPITAL_CAPACITY: {
    id: "STALE_HOSPITAL_CAPACITY",
    label: "Stale Hospital Capacity",
    description: "The selected hospital's capacity data goes stale; the system reassesses and may reassign.",
    trafficSchedule: [{ atFrac: 0, level: TRAFFIC_LEVEL.GREEN }],
    gpsDegradeAtFrac: null,
    gpsPoorAtFrac: null,
    routeFailureAtFrac: null,
    hospitalStaleAtFrac: 0.4,
  },
  CASCADING_FAILURE: {
    id: "CASCADING_FAILURE",
    label: "Cascading Failure",
    description: "GPS degradation + traffic spike + route failure + stale hospital capacity, all in one response.",
    trafficSchedule: [
      { atFrac: 0, level: TRAFFIC_LEVEL.GREEN },
      { atFrac: 0.2, level: TRAFFIC_LEVEL.YELLOW },
      { atFrac: 0.4, level: TRAFFIC_LEVEL.RED },
      { atFrac: 0.85, level: TRAFFIC_LEVEL.ORANGE },
    ],
    gpsDegradeAtFrac: 0.3,
    gpsPoorAtFrac: 0.5,
    gpsRecoverAtFrac: 0.8,
    routeFailureAtFrac: 0.45,
    hospitalStaleAtFrac: 0.3,
  },
};

export const SCENARIO_ORDER = [
  "NORMAL_RESPONSE",
  "HEAVY_TRAFFIC",
  "GPS_DEGRADATION",
  "ROUTE_FAILURE",
  "STALE_HOSPITAL_CAPACITY",
  "CASCADING_FAILURE",
];

/** Threshold (seconds of *simulated* time) after which hospital capacity data is considered stale. */
export const HOSPITAL_STALE_THRESHOLD_SEC = 90;

/** Ambulance base cruising speed by type, km/h -- before traffic/road multipliers. */
export const BASE_SPEED_KPH = {
  BASIC: 40,
  ALS: 45,
  ICU: 42,
};

/** Max acceleration / deceleration, km/h per simulated second -- keeps movement smooth, not teleporting. */
export const ACCEL_KPH_PER_SEC = 8;
export const DECEL_KPH_PER_SEC = 14;
