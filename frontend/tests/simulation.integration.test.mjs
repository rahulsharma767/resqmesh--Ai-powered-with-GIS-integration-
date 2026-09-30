/**
 * Integration test: drives the REAL SimulationEngine (engine.js) against a
 * LIVE person2_backend instance (real Mumbai road graph, real hospitals,
 * real ambulances, real road-closure/reroute endpoints). This is not a
 * mock -- it exercises the exact same engine.js the browser UI uses, just
 * ticked manually instead of via requestAnimationFrame.
 *
 * Requires person2_backend running on http://localhost:8000 (or
 * PERSON2_API_URL env var). Run with:
 *   VITE_PERSON2_API_URL=http://localhost:8000 node tests/simulation.integration.test.mjs
 */
import assert from "node:assert/strict";
import { SimulationEngine, PHASE } from "../src/simulation/engine.js";

const scenarioId = process.argv[2] || "CASCADING_FAILURE";
const seed = 104;

async function main() {
  const engine = new SimulationEngine({ seed, scenarioId });

  const incident = {
    incident_id: "INC-ITEST-1",
    latitude: 19.0662,
    longitude: 72.8697, // Bandra Kurla Complex
    severity: "critical",
    patient_condition: "chest pain, unconscious",
    required_capabilities: ["CARDIAC"],
    label: "Integration test incident",
  };

  console.log(`Starting incident under scenario=${scenarioId} seed=${seed} ...`);
  await engine.startIncident(incident);

  if (engine.state.phase === PHASE.ERROR) {
    console.error("Dispatch failed:", engine.state.lastError);
    process.exit(1);
  }

  assert.ok(engine.state.ambulance, "ambulance should be assigned");
  assert.ok(engine.state.hospital, "hospital should be assigned");
  assert.ok(engine.state.route && engine.state.route.coordinates.length > 1, "route should have real road coordinates");
  console.log(`Dispatched ${engine.state.ambulance.id} (${engine.state.ambulance.type}) -> hospital ${engine.state.hospital.name}`);

  engine.setSpeed(20); // fast-forward for the test
  const TICK_MS = 500;
  const MAX_TICKS = 4000; // generous ceiling so the test can't hang forever
  let ticks = 0;
  while (engine.state.phase !== PHASE.ARRIVED && engine.state.phase !== PHASE.ERROR && ticks < MAX_TICKS) {
    engine.tick(TICK_MS);
    // allow any in-flight async reroute/reassessment work (route failure, hospital
    // reassessment) to resolve between ticks, same as real animation frames would.
    await new Promise((r) => setTimeout(r, 5));
    ticks++;
  }

  console.log(`\nFinished after ${ticks} ticks, simTime=${engine.state.simTimeSec.toFixed(1)}s, phase=${engine.state.phase}`);
  console.log(`\nEvent timeline (${engine.state.events.length} events):`);
  for (const ev of engine.state.events) {
    console.log(`  [${ev.tSec.toFixed(1).padStart(7)}s] ${ev.type.padEnd(24)} ${ev.message}`);
  }

  assert.equal(engine.state.phase, PHASE.ARRIVED, "simulation should reach ARRIVED");

  const types = engine.state.events.map((e) => e.type);
  assert.ok(types.includes("INCIDENT_CREATED"));
  assert.ok(types.includes("AMBULANCE_DISPATCHED"));
  assert.ok(types.includes("AMBULANCE_STARTED"));
  assert.ok(types.includes("AMBULANCE_AT_INCIDENT"));
  assert.ok(types.includes("AMBULANCE_ARRIVED"));

  if (scenarioId === "CASCADING_FAILURE" || scenarioId === "ROUTE_FAILURE") {
    assert.ok(types.includes("ROUTE_FAILED"), "expected a ROUTE_FAILED event for this scenario");
    assert.ok(
      types.includes("ROUTE_RECALCULATED") || types.includes("ROUTE_FAILURE_UNRESOLVED"),
      "expected the route failure to be followed by a real reroute attempt"
    );
  }
  if (scenarioId === "CASCADING_FAILURE" || scenarioId === "STALE_HOSPITAL_CAPACITY") {
    assert.ok(types.includes("HOSPITAL_DATA_STALE"), "expected a HOSPITAL_DATA_STALE event for this scenario");
    assert.ok(types.includes("HOSPITAL_REASSESSED"), "expected a HOSPITAL_REASSESSED event for this scenario");
  }
  if (scenarioId === "CASCADING_FAILURE" || scenarioId === "GPS_DEGRADATION") {
    assert.ok(types.includes("GPS_DEGRADED"), "expected GPS_DEGRADED event(s) for this scenario");
  }

  console.log(`\nPASS: scenario ${scenarioId} completed end-to-end against the live backend.`);
}

main().catch((err) => {
  console.error("Integration test FAILED:", err);
  process.exit(1);
});
