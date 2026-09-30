import { useState, useMemo } from "react";
import { AlertTriangle, Siren, PlayCircle, PauseCircle, RefreshCw, Zap, MapPin, Gauge, Clock, Radio, Building2, Ambulance as AmbulanceIcon } from "lucide-react";
import { useSimulationEngine } from "./useSimulationEngine";
import LiveSimulationMap from "./LiveSimulationMap";
import { SCENARIOS, SCENARIO_ORDER } from "./scenarios.js";
import { gpsQualityMeta } from "./gpsModel.js";
import { TRAFFIC_LABEL } from "./trafficModel.js";

const INCIDENT_PRESETS = [
  { label: "Bandra Kurla Complex", lat: 19.0662, lon: 72.8697 },
  { label: "Andheri Station (W)", lat: 19.1197, lon: 72.8468 },
  { label: "Dadar TT Circle", lat: 19.0176, lon: 72.844 },
  { label: "Colaba Causeway", lat: 18.9067, lon: 72.8147 },
  { label: "Powai Lake", lat: 19.1176, lon: 72.906 },
  { label: "Worli Sea Face", lat: 19.0176, lon: 72.8177 },
];

const SEVERITIES = ["low", "moderate", "critical"];
const CONDITIONS = [
  { label: "Cardiac (chest pain)", value: "chest pain, possible cardiac event", caps: ["CARDIAC"] },
  { label: "Trauma (road accident)", value: "road traffic accident, multiple injuries", caps: ["TRAUMA"] },
  { label: "Respiratory distress", value: "severe difficulty breathing", caps: ["RESPIRATORY"] },
  { label: "Unconscious / unresponsive", value: "unconscious, unresponsive", caps: ["NEURO"] },
  { label: "General / basic", value: "fall injury, conscious and stable", caps: [] },
];

let incidentCounter = 1;

function Panel({ title, icon: Icon, right, children, style }) {
  return (
    <div className="rqm-panel" style={{ padding: 14, ...style }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: "0.85em", color: "var(--text)" }}>
          {Icon && <Icon size={15} style={{ color: "var(--accent)" }} />}
          {title}
        </div>
        {right}
      </div>
      {children}
    </div>
  );
}

function Row({ label, value, tone }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: "0.8em", borderBottom: "1px solid var(--border-soft)" }}>
      <span style={{ color: "var(--text-faint)" }}>{label}</span>
      <span style={{ fontWeight: 600, color: tone ? `var(--${tone})` : "var(--text)" }} className="rqm-mono">
        {value}
      </span>
    </div>
  );
}

function Btn({ children, onClick, active, disabled, variant = "default" }) {
  const bg = active ? "var(--accent)" : variant === "primary" ? "var(--accent-soft)" : "var(--panel-2)";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="rqm-btn rqm-focus"
      style={{
        padding: "6px 11px",
        borderRadius: 7,
        border: "1px solid var(--border)",
        background: bg,
        color: active ? "#000" : "var(--text)",
        fontWeight: 600,
        fontSize: "0.78em",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        display: "flex",
        alignItems: "center",
        gap: 5,
      }}
    >
      {children}
    </button>
  );
}

function severityColor(sev) {
  if (sev === "critical") return "critical";
  if (sev === "warning") return "high";
  if (sev === "success") return "low";
  return "info";
}

function fmtClock(sec) {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const ss = s % 60;
  return `${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

export default function LiveSimulationPage() {
  const [preset, setPreset] = useState(INCIDENT_PRESETS[0]);
  const [severity, setSeverity] = useState("critical");
  const [conditionIdx, setConditionIdx] = useState(0);
  const [seedInput, setSeedInput] = useState(104);

  const { snapshot, startIncident, restart, pause, resume, setSpeed, setScenario, setSeed } = useSimulationEngine({
    seed: 104,
    scenarioId: "NORMAL_RESPONSE",
  });

  const scenario = SCENARIOS[snapshot.scenarioId];
  const started = snapshot.phase !== "IDLE";

  const trigger = () => {
    const cond = CONDITIONS[conditionIdx];
    setSeed(Number(seedInput) || 104);
    startIncident({
      incident_id: `INC-${String(incidentCounter++).padStart(3, "0")}`,
      latitude: preset.lat,
      longitude: preset.lon,
      severity,
      patient_condition: cond.value,
      required_capabilities: cond.caps,
      patient_count: cond.label.includes("Trauma") ? 3 : cond.label.includes("Unconscious") ? 1 : 1,
      label: `Medical Emergency - ${preset.label}`,
    });
  };

  const runDemo = () => {
    setSeed(104);
    setScenario("CASCADING_FAILURE");
    setSpeed(5);
    startIncident({
      incident_id: `INC-${String(incidentCounter++).padStart(3, "0")}`,
      latitude: INCIDENT_PRESETS[0].lat,
      longitude: INCIDENT_PRESETS[0].lon,
      severity: "critical",
      patient_condition: "major trauma, severe bleeding, two unconscious, two critical, cardiac arrest",
      required_capabilities: ["CARDIAC"],
      patient_count: 4,
      label: `Medical Emergency - ${INCIDENT_PRESETS[0].label} (DEMO)`,
    });
  };

  const gpsMeta = gpsQualityMeta(snapshot.gps?.quality || "GOOD");
  const eventsReversed = useMemo(() => [...snapshot.events].reverse(), [snapshot.events]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div
        className="rqm-panel"
        style={{
          padding: "10px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 10,
          borderColor: "var(--high)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span className="rqm-mono" style={{ fontWeight: 800, color: "var(--high)", fontSize: "0.82em", letterSpacing: ".05em" }}>
            SIMULATION MODE - SYNTHETIC DATA
          </span>
          <span style={{ fontSize: "0.75em", color: "var(--text-faint)" }}>
            Real Mumbai road network + real hospital/ambulance selection from person2_backend. Ambulance movement, GPS
            noise, traffic and hospital-data staleness are simulated.
          </span>
        </div>
        <div className="rqm-mono" style={{ fontSize: "0.78em", color: "var(--text-dim)", display: "flex", gap: 14 }}>
          <span>
            <Clock size={12} style={{ verticalAlign: "-2px" }} /> {fmtClock(snapshot.simTimeSec)}
          </span>
          <span>Scenario: {scenario.label}</span>
          <span>Seed: {snapshot.seed}</span>
          <span>Speed: {snapshot.speed}x</span>
        </div>
      </div>

      {snapshot.phase === "ERROR" && (
        <div className="rqm-panel" style={{ padding: 14, borderColor: "var(--critical)", color: "var(--critical)", fontSize: "0.85em" }}>
          <AlertTriangle size={14} style={{ verticalAlign: "-2px", marginRight: 6 }} />
          {snapshot.lastError || "Dispatch failed."} Make sure person2_backend is running (see README) at the URL configured
          in frontend/.env (VITE_PERSON2_API_URL).
        </div>
      )}

      <Panel title="AI Incident Intelligence" icon={Zap} right={
        <span className="rqm-mono" style={{ fontSize: "0.68em", color: snapshot.ai?.status === "READY" ? "var(--low)" : "var(--high)" }}>
          {snapshot.ai?.status || "IDLE"}
        </span>
      }>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(110px, 1fr))", gap: 10 }}>
          {[
            ["Risk Score", snapshot.ai?.riskScore == null ? "—" : `${(snapshot.ai.riskScore * 100).toFixed(1)}%`, snapshot.ai?.priority === "CRITICAL" ? "critical" : snapshot.ai?.priority === "HIGH" ? "high" : "info"],
            ["Priority", snapshot.ai?.priority || "—", snapshot.ai?.priority === "CRITICAL" ? "critical" : "high"],
            ["Confidence", snapshot.ai?.confidence == null ? "—" : `${(snapshot.ai.confidence * 100).toFixed(1)}%`, "info"],
            ["Inference", snapshot.ai?.provider || "—", snapshot.ai?.qnnVerified ? "low" : "info"],
            ["Target", "SNAPDRAGON X / QNN", "accent"],
          ].map(([label, value, tone]) => (
            <div key={label} className="rqm-panel" style={{ padding: 10, background: "var(--panel-2)" }}>
              <div style={{ fontSize: "0.68em", color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: ".07em" }}>{label}</div>
              <div className="rqm-mono" style={{ fontSize: label === "Inference" ? "0.72em" : "1.15em", fontWeight: 800, marginTop: 5, color: tone === "accent" ? "var(--accent)" : `var(--${tone})` }}>{value}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 10 }}>
          <div style={{ padding: 10, border: "1px solid var(--border-soft)", borderRadius: 8 }}>
            <div className="rqm-mono" style={{ fontSize: "0.68em", color: "var(--text-faint)", marginBottom: 5 }}>MODEL / RUNTIME</div>
            <div style={{ fontSize: "0.76em" }}>{snapshot.ai?.modelName || "ResQMesh Emergency Risk v1"}</div>
            <div style={{ fontSize: "0.7em", color: "var(--text-faint)", marginTop: 3 }}>Actual provider is reported at runtime. QNN/NPU is never claimed without verification.</div>
          </div>
          <div style={{ padding: 10, border: "1px solid var(--border-soft)", borderRadius: 8 }}>
            <div className="rqm-mono" style={{ fontSize: "0.68em", color: "var(--text-faint)", marginBottom: 5 }}>WHY THE MODEL MOVED</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {(snapshot.ai?.factors || []).slice(0, 5).map((f) => (
                <span key={f.feature} className="rqm-mono" style={{ fontSize: "0.66em", padding: "4px 6px", borderRadius: 5, background: f.effect === "increases" ? "var(--critical-soft)" : "var(--low-soft)", color: f.effect === "increases" ? "var(--critical)" : "var(--low)" }}>
                  {f.evidence}
                </span>
              ))}
              {(!snapshot.ai?.factors || snapshot.ai.factors.length === 0) && <span style={{ fontSize: "0.72em", color: "var(--text-faint)" }}>Waiting for first local inference…</span>}
            </div>
          </div>
        </div>
        {snapshot.ai?.lastTrigger && <div className="rqm-mono" style={{ marginTop: 8, fontSize: "0.66em", color: "var(--text-faint)" }}>AI trigger: {snapshot.ai.lastTrigger} · {snapshot.ai?.recommendedAction || "Awaiting assessment"}</div>}
      </Panel>

      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr 300px", gap: 14, alignItems: "start" }}>
        {/* Controls */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Panel title="Simulation Clock" icon={Gauge}>
            <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
              <Btn onClick={resume} active={snapshot.running && !snapshot.paused} disabled={!started}>
                <PlayCircle size={13} /> Start
              </Btn>
              <Btn onClick={pause} disabled={!started || snapshot.paused}>
                <PauseCircle size={13} /> Pause
              </Btn>
              <Btn onClick={restart} disabled={!started}>
                <RefreshCw size={13} /> Restart
              </Btn>
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {[1, 2, 5, 10].map((s) => (
                <Btn key={s} onClick={() => setSpeed(s)} active={snapshot.speed === s}>
                  {s}x
                </Btn>
              ))}
            </div>
          </Panel>

          <Panel title="Scenario" icon={Zap}>
            <select
              value={snapshot.scenarioId}
              onChange={(e) => setScenario(e.target.value)}
              className="rqm-focus"
              style={{ width: "100%", background: "var(--panel-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", fontSize: "0.78em", marginBottom: 8 }}
            >
              {SCENARIO_ORDER.map((id) => (
                <option key={id} value={id}>
                  {SCENARIOS[id].label}
                </option>
              ))}
            </select>
            <div style={{ fontSize: "0.72em", color: "var(--text-faint)", marginBottom: 8 }}>{scenario.description}</div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <span style={{ fontSize: "0.72em", color: "var(--text-faint)" }}>Seed</span>
              <input
                type="number"
                value={seedInput}
                onChange={(e) => setSeedInput(e.target.value)}
                className="rqm-mono rqm-focus"
                style={{ width: 70, background: "var(--panel-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "4px 6px", fontSize: "0.78em" }}
              />
            </div>
          </Panel>

          <Panel title="New Emergency" icon={Siren}>
            <select
              value={preset.label}
              onChange={(e) => setPreset(INCIDENT_PRESETS.find((p) => p.label === e.target.value))}
              className="rqm-focus"
              style={{ width: "100%", background: "var(--panel-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", fontSize: "0.78em", marginBottom: 6 }}
            >
              {INCIDENT_PRESETS.map((p) => (
                <option key={p.label} value={p.label}>
                  {p.label}
                </option>
              ))}
            </select>
            <select
              value={conditionIdx}
              onChange={(e) => setConditionIdx(Number(e.target.value))}
              className="rqm-focus"
              style={{ width: "100%", background: "var(--panel-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", fontSize: "0.78em", marginBottom: 6 }}
            >
              {CONDITIONS.map((c, i) => (
                <option key={c.label} value={i}>
                  {c.label}
                </option>
              ))}
            </select>
            <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
              {SEVERITIES.map((s) => (
                <Btn key={s} onClick={() => setSeverity(s)} active={severity === s}>
                  {s}
                </Btn>
              ))}
            </div>
            <Btn onClick={trigger} variant="primary" active>
              <MapPin size={13} /> Dispatch
            </Btn>
            <div style={{ height: 8 }} />
            <Btn onClick={runDemo}>
              <PlayCircle size={13} /> Run Full Demo
            </Btn>
          </Panel>
        </div>

        {/* Map */}
        <Panel title="GIS Live Map (real Mumbai road network)" icon={MapPin} style={{ padding: 0, overflow: "hidden" }}>
          <LiveSimulationMap snapshot={snapshot} height={620} />
        </Panel>

        {/* Live response + hospital + timeline */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Panel title="Live Response" icon={AmbulanceIcon}>
            {!snapshot.ambulance ? (
              <div style={{ fontSize: "0.78em", color: "var(--text-faint)" }}>No active response. Trigger an emergency to begin.</div>
            ) : (
              <>
                <Row label="Unit" value={snapshot.ambulance.id} />
                <Row label="Type" value={snapshot.ambulance.type} />
                <Row label="Status" value={snapshot.phase.replaceAll("_", " ")} />
                <Row label="Speed" value={`${snapshot.ambulance.speedKph.toFixed(0)} km/h`} />
                <Row label="ETA" value={snapshot.route ? `${Math.max(snapshot.route.etaMinutes, 0).toFixed(1)} min` : "-"} />
                <Row label="Distance left" value={snapshot.route ? `${Math.max(snapshot.route.distanceKmRemaining ?? snapshot.route.distanceKm, 0).toFixed(2)} km` : "-"} />
                <Row label="GPS" value={`±${Math.round(snapshot.gps.accuracyM || 0)}m (${gpsMeta.label})`} tone={gpsMeta.tone} />
                <Row label="Traffic" value={TRAFFIC_LABEL[snapshot.traffic.level]} />
                <Row label="Destination" value={snapshot.hospital?.name || "-"} />
                {snapshot.decision && (
                  <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--border-soft)", fontSize: "0.7em", color: "var(--text-faint)" }}>
                    <div style={{ marginBottom: 4 }}>
                      <strong style={{ color: "var(--text-dim)" }}>Why this unit: </strong>
                      {snapshot.decision.ambulance_reason}
                    </div>
                    <div>
                      <strong style={{ color: "var(--text-dim)" }}>Why this hospital: </strong>
                      {snapshot.decision.hospital_reason}
                    </div>
                  </div>
                )}
              </>
            )}
          </Panel>

          <Panel title="Destination Hospital" icon={Building2}>
            {!snapshot.hospital ? (
              <div style={{ fontSize: "0.78em", color: "var(--text-faint)" }}>-</div>
            ) : (
              <>
                <Row label="Name" value={snapshot.hospital.name} />
                <Row label="Available beds" value={snapshot.hospital.availableBeds} />
                <Row label="ICU" value={snapshot.hospital.icuAvailable ? "Available" : "Not available"} />
                <Row label="Emergency" value={snapshot.hospital.emergencyAvailable ? "Yes" : "No"} />
                <Row label="Status" value={snapshot.hospital.status} />
                <Row label="Capacity data" value={snapshot.hospital.stale ? "STALE - reassessing" : "Fresh"} tone={snapshot.hospital.stale ? "high" : "low"} />
              </>
            )}
          </Panel>

          <Panel title="Live Event Timeline" icon={Radio}>
            <div style={{ maxHeight: 320, overflowY: "auto" }} className="rqm-scroll">
              {eventsReversed.length === 0 && <div style={{ fontSize: "0.78em", color: "var(--text-faint)" }}>No events yet.</div>}
              {eventsReversed.map((ev) => (
                <div key={ev.id} style={{ padding: "6px 0", borderBottom: "1px solid var(--border-soft)" }}>
                  <div className="rqm-mono" style={{ fontSize: "0.68em", color: "var(--text-faint)" }}>
                    {fmtClock(ev.tSec)} - {ev.type}
                  </div>
                  <div style={{ fontSize: "0.76em", color: `var(--${severityColor(ev.severity)})` }}>{ev.message}</div>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
