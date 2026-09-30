import { useEffect, useRef, useState, useCallback } from "react";
import { SimulationEngine, PHASE } from "./engine.js";

/**
 * React binding for SimulationEngine. Owns the engine instance + the
 * requestAnimationFrame loop; the engine itself has no React dependency
 * (it's a plain class so its core logic -- and the tests in
 * tests/simulation.engine.test.mjs -- can run in plain Node).
 */
export function useSimulationEngine({ seed = 104, scenarioId = "NORMAL_RESPONSE" } = {}) {
  const engineRef = useRef(null);
  if (!engineRef.current) {
    engineRef.current = new SimulationEngine({ seed, scenarioId });
  }
  const engine = engineRef.current;

  const [snapshot, setSnapshot] = useState(engine.state);
  const rafRef = useRef(null);
  const lastTsRef = useRef(null);

  useEffect(() => {
    const unsubscribe = engine.subscribe(setSnapshot);
    return unsubscribe;
  }, [engine]);

  useEffect(() => {
    function loop(ts) {
      if (lastTsRef.current == null) lastTsRef.current = ts;
      const dtMs = Math.min(ts - lastTsRef.current, 250); // clamp huge gaps (tab backgrounded, etc.)
      lastTsRef.current = ts;
      engine.tick(dtMs);
      rafRef.current = requestAnimationFrame(loop);
    }
    rafRef.current = requestAnimationFrame(loop);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      lastTsRef.current = null;
    };
  }, [engine]);

  const startIncident = useCallback((incident) => engine.startIncident(incident), [engine]);
  const restart = useCallback(() => engine.restart(), [engine]);
  const pause = useCallback(() => engine.pause(), [engine]);
  const resume = useCallback(() => engine.resume(), [engine]);
  const setSpeed = useCallback((s) => engine.setSpeed(s), [engine]);
  const setScenario = useCallback((s) => engine.setScenario(s), [engine]);
  const setSeed = useCallback((s) => engine.setSeed(s), [engine]);

  return { snapshot, startIncident, restart, pause, resume, setSpeed, setScenario, setSeed, PHASE };
}
