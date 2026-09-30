/**
 * Deterministic, time-scheduled traffic model.
 *
 * Real live traffic feeds are not available (documented limitation, same as
 * person2_backend's build_graph.py speed table). Instead of re-rolling
 * random congestion every animation frame (which the spec explicitly rules
 * out), each scenario carries a fixed schedule of {atSec, level} events; the
 * traffic level at simulation time T is simply "the last scheduled event at
 * or before T", defaulting to GREEN. This is fully deterministic for a given
 * scenario and trivially reproducible.
 */

export const TRAFFIC_LEVEL = {
  GREEN: "GREEN",
  YELLOW: "YELLOW",
  ORANGE: "ORANGE",
  RED: "RED",
};

// Speed multiplier applied on top of the ambulance's base speed.
export const TRAFFIC_SPEED_MULTIPLIER = {
  [TRAFFIC_LEVEL.GREEN]: 1.0,
  [TRAFFIC_LEVEL.YELLOW]: 0.75,
  [TRAFFIC_LEVEL.ORANGE]: 0.5,
  [TRAFFIC_LEVEL.RED]: 0.3,
};

export const TRAFFIC_LABEL = {
  [TRAFFIC_LEVEL.GREEN]: "Low",
  [TRAFFIC_LEVEL.YELLOW]: "Moderate",
  [TRAFFIC_LEVEL.ORANGE]: "Heavy",
  [TRAFFIC_LEVEL.RED]: "Severe",
};

/**
 * schedule: [{atSec, level}], sorted ascending by atSec.
 * Returns the active level at simSec.
 */
export function trafficLevelAt(simSec, schedule) {
  let level = TRAFFIC_LEVEL.GREEN;
  for (const ev of schedule) {
    if (ev.atSec <= simSec) level = ev.level;
    else break;
  }
  return level;
}
