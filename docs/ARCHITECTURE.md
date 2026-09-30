# ResQMesh AI Architecture

```text
                         RESQMESH AI
                              │
                 Emergency report / event
                              │
                              ▼
                  Existing incident pipeline
                 extraction + ambiguity checks
                              │
                              ▼
                  Structured IncidentState
                              │
                              ▼
                 ┌─────────────────────────┐
                 │ Local Risk AI Engine    │
                 │                         │
                 │ 15 operational features│
                 │ ↓                       │
                 │ learned classifier      │
                 │ ↓                       │
                 │ risk / priority /       │
                 │ confidence / factors    │
                 └────────────┬────────────┘
                              │ advisory only
                              ▼
                 Deterministic Dispatch Engine
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
        Ambulance          A* Routing       Hospital
        capability         road feasibility capability/
        availability       + closures       capacity
             └────────────────┼────────────────┘
                              ▼
                       Verified response
                              │
                              ▼
                       Live simulation
             traffic / GPS / road closure / capacity
                              │
                              ▼
                      AI reassessment
                              │
                              ▼
                         Rerouting /
                     destination revalidation
                              │
                              ▼
                        Human approval
```

## Runtime boundary

The local model is exported as ONNX. The backend attempts ONNX Runtime and prefers `QNNExecutionProvider` only when the installed runtime exposes it. Otherwise the same learned parameters are evaluated locally through the NumPy fallback. This means the demo can be developed on non-Snapdragon hardware without pretending that a Qualcomm NPU is active.

## Why this separation matters

The model can change its risk recommendation as traffic, route ETA or hospital state changes, but it cannot directly override hard operational constraints. This is the core safety boundary of the application.
