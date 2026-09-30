/**
 * Pure-Node test suite for the deterministic core of the simulation engine
 * (rng, geo, gpsModel, trafficModel, scenarios). These modules have no
 * React/Vite/browser dependency, so they run directly under plain Node --
 * no build step, no test framework, just assert().
 *
 * Run with:  node tests/simulation.engine.test.mjs
 */
import assert from "node:assert/strict";
import { SeededRandom } from "../src/simulation/rng.js";
import {
  haversineMeters,
  bearingDeg,
  cumulativeDistances,
  pointAtDistance,
  offsetMeters,
} from "../src/simulation/geo.js";
import { sampleGpsReading, GPS_QUALITY } from "../src/simulation/gpsModel.js";
import { trafficLevelAt, TRAFFIC_LEVEL } from "../src/simulation/trafficModel.js";
import { SCENARIOS, SCENARIO_ORDER } from "../src/simulation/scenarios.js";

let passed = 0;
function test(name, fn) {
  try {
    fn();
    passed++;
    console.log(`  ok  - ${name}`);
  } catch (err) {
    console.error(`FAIL  - ${name}`);
    console.error(err);
    process.exitCode = 1;
  }
}

console.log("SimulationEngine core -- deterministic module tests\n");

// ---------------------------------------------------------------------
test("SeededRandom: same seed -> identical sequence (reproducibility)", () => {
  const a = new SeededRandom(104);
  const b = new SeededRandom(104);
  const seqA = Array.from({ length: 50 }, () => a.next());
  const seqB = Array.from({ length: 50 }, () => b.next());
  assert.deepEqual(seqA, seqB);
});

test("SeededRandom: different seeds -> different sequences", () => {
  const a = new SeededRandom(104);
  const b = new SeededRandom(105);
  const seqA = Array.from({ length: 20 }, () => a.next());
  const seqB = Array.from({ length: 20 }, () => b.next());
  assert.notDeepEqual(seqA, seqB);
});

test("SeededRandom.reset(): restarting a stream reproduces the same values (restart() correctness)", () => {
  const r = new SeededRandom(42);
  const first = Array.from({ length: 10 }, () => r.next());
  r.reset();
  const second = Array.from({ length: 10 }, () => r.next());
  assert.deepEqual(first, second);
});

test("SeededRandom.range/int/bool/gaussian stay within documented bounds", () => {
  const r = new SeededRandom(7);
  for (let i = 0; i < 200; i++) {
    const v = r.range(10, 20);
    assert.ok(v >= 10 && v < 20);
    const n = r.int(1, 5);
    assert.ok(n >= 1 && n <= 5);
  }
});

// ---------------------------------------------------------------------
test("geo.haversineMeters: known distance between two real Mumbai points is plausible", () => {
  // Bandra (19.0550, 72.8296) to Andheri (19.1197, 72.8468) -- roughly 7-8km straight-line.
  const d = haversineMeters([72.8296, 19.055], [72.8468, 19.1197]);
  assert.ok(d > 6500 && d < 8500, `expected ~7-8km, got ${d}m`);
});

test("geo.haversineMeters: distance to self is zero", () => {
  const d = haversineMeters([72.83, 19.05], [72.83, 19.05]);
  assert.equal(d, 0);
});

test("geo.bearingDeg: due-east bearing is ~90deg", () => {
  const b = bearingDeg([72.0, 19.0], [72.1, 19.0]);
  assert.ok(Math.abs(b - 90) < 1, `expected ~90, got ${b}`);
});

test("geo.cumulativeDistances + pointAtDistance: interpolates correctly along a straight synthetic path", () => {
  const path = [
    [72.0, 19.0],
    [72.0, 19.01], // due north
    [72.0, 19.02],
  ];
  const cum = cumulativeDistances(path);
  const total = cum[cum.length - 1];
  const atStart = pointAtDistance(path, cum, 0);
  const atEnd = pointAtDistance(path, cum, total);
  const atMid = pointAtDistance(path, cum, total / 2);
  assert.deepEqual(atStart.position, path[0]);
  assert.deepEqual(atEnd.position, path[2]);
  // midpoint should be close to the middle vertex
  assert.ok(Math.abs(atMid.position[1] - 19.01) < 0.001);
});

test("geo.pointAtDistance: clamps beyond path length instead of extrapolating/crashing", () => {
  const path = [
    [72.0, 19.0],
    [72.0, 19.01],
  ];
  const cum = cumulativeDistances(path);
  const beyond = pointAtDistance(path, cum, cum[cum.length - 1] + 99999);
  assert.deepEqual(beyond.position, path[1]);
});

test("geo.offsetMeters: offsetting by (0,0) is a no-op", () => {
  const p = [72.83, 19.05];
  const p2 = offsetMeters(p, 0, 0);
  assert.ok(Math.abs(p2[0] - p[0]) < 1e-9 && Math.abs(p2[1] - p[1]) < 1e-9);
});

// ---------------------------------------------------------------------
test("gpsModel: same seed -> identical GPS reading sequence (GPS reproducibility, spec section 34)", () => {
  const a = new SeededRandom(104);
  const b = new SeededRandom(104);
  const seqA = Array.from({ length: 30 }, () => sampleGpsReading(a, GPS_QUALITY.DEGRADED));
  const seqB = Array.from({ length: 30 }, () => sampleGpsReading(b, GPS_QUALITY.DEGRADED));
  assert.deepEqual(seqA, seqB);
});

test("gpsModel: POOR accuracy radius is worse (larger) than GOOD on average", () => {
  const r1 = new SeededRandom(1);
  const r2 = new SeededRandom(1);
  const good = Array.from({ length: 200 }, () => sampleGpsReading(r1, GPS_QUALITY.GOOD).accuracyM);
  const poor = Array.from({ length: 200 }, () => sampleGpsReading(r2, GPS_QUALITY.POOR).accuracyM);
  const avg = (arr) => arr.reduce((a, b) => a + b, 0) / arr.length;
  assert.ok(avg(poor) > avg(good) * 3, `expected POOR >> GOOD, got poor=${avg(poor)} good=${avg(good)}`);
});

// ---------------------------------------------------------------------
test("trafficModel.trafficLevelAt: defaults to GREEN before any scheduled event", () => {
  const schedule = [{ atSec: 30, level: TRAFFIC_LEVEL.RED }];
  assert.equal(trafficLevelAt(0, schedule), TRAFFIC_LEVEL.GREEN);
  assert.equal(trafficLevelAt(29.9, schedule), TRAFFIC_LEVEL.GREEN);
});

test("trafficModel.trafficLevelAt: same seed/schedule -> same sequence (traffic reproducibility, spec section 34)", () => {
  const schedule = [
    { atSec: 0, level: TRAFFIC_LEVEL.GREEN },
    { atSec: 10, level: TRAFFIC_LEVEL.YELLOW },
    { atSec: 25, level: TRAFFIC_LEVEL.RED },
    { atSec: 40, level: TRAFFIC_LEVEL.GREEN },
  ];
  const sample = (sched) => [0, 5, 10, 15, 25, 39, 40, 100].map((t) => trafficLevelAt(t, sched));
  assert.deepEqual(sample(schedule), sample(schedule));
  assert.deepEqual(sample(schedule), [
    TRAFFIC_LEVEL.GREEN,
    TRAFFIC_LEVEL.GREEN,
    TRAFFIC_LEVEL.YELLOW,
    TRAFFIC_LEVEL.YELLOW,
    TRAFFIC_LEVEL.RED,
    TRAFFIC_LEVEL.RED,
    TRAFFIC_LEVEL.GREEN,
    TRAFFIC_LEVEL.GREEN,
  ]);
});

// ---------------------------------------------------------------------
test("scenarios: every id in SCENARIO_ORDER has a matching definition with required fields", () => {
  for (const id of SCENARIO_ORDER) {
    const s = SCENARIOS[id];
    assert.ok(s, `missing scenario definition for ${id}`);
    assert.equal(s.id, id);
    assert.ok(Array.isArray(s.trafficSchedule) && s.trafficSchedule.length >= 1);
    assert.ok(typeof s.label === "string" && s.label.length > 0);
  }
});

test("scenarios: CASCADING_FAILURE actually combines GPS + traffic + route-failure + hospital-staleness triggers", () => {
  const s = SCENARIOS.CASCADING_FAILURE;
  assert.ok(s.gpsDegradeAtFrac != null);
  assert.ok(s.routeFailureAtFrac != null);
  assert.ok(s.hospitalStaleAtFrac != null);
  assert.ok(s.trafficSchedule.length > 1);
});

test("scenarios: NORMAL_RESPONSE has no failure triggers (baseline)", () => {
  const s = SCENARIOS.NORMAL_RESPONSE;
  assert.equal(s.gpsDegradeAtFrac, null);
  assert.equal(s.routeFailureAtFrac, null);
  assert.equal(s.hospitalStaleAtFrac, null);
});

console.log(`\n${passed} test(s) passed.`);
if (process.exitCode) {
  console.error("\nSome tests FAILED.");
} else {
  console.log("All tests passed.");
}
