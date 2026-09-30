# ResQMesh AI — Snapdragon AI Lab Submission Brief

## 1. Project name
**RESQMESH AI — On-Device Emergency Response Intelligence**

## 2. One-line pitch
ResQMesh AI combines local AI risk assessment with deterministic GIS routing to help emergency operators respond to changing incidents in real time on Snapdragon-powered PCs.

## 3. Problem
Emergency reports arrive as incomplete natural language while ambulance availability, road conditions and hospital capacity change continuously. A useful system must interpret the report quickly without allowing an AI model to bypass operational constraints.

## 4. Solution
ResQMesh AI connects the existing ResQMesh pipeline to a real local ML risk engine. Structured incident features are scored locally for risk, priority and confidence. The deterministic engine then handles ambulance feasibility, road routing, hospital matching and hard constraints. The simulation can trigger traffic changes, road closures and hospital-capacity changes, causing the AI state and operational plan to be reassessed.

## 5. Innovation
The AI is not an isolated classifier or chatbot. Its output is connected to a live GIS response state. The system demonstrates a closed loop: **understand → assess risk → dispatch deterministically → route → observe changing conditions → reassess → reroute/revalidate → human approval**.

## 6. AI architecture
```text
Structured incident features
        ↓
Multinomial logistic-regression risk model
        ↓
risk score + priority + confidence + learned feature factors
        ↓
ONNX artifact / ONNX Runtime
        ↓
QNN Execution Provider when available
        ↓
Snapdragon NPU target
```

The checked-in fallback uses the same trained parameters through local NumPy execution when ONNX Runtime/QNN is unavailable.

## 7. Snapdragon optimization
The inference boundary is intentionally portable. `GET /api/ai/status` reports the actual provider. QNN is selected only if the runtime exposes `QNNExecutionProvider`. No NPU execution or speedup is claimed without verification.

## 8. Technical implementation
- React + Vite command-center UI
- Leaflet live Mumbai map
- Python + FastAPI backend
- Existing A* road routing and closure-aware rerouting
- Existing deterministic ambulance selection
- Existing hospital capability/capacity matching
- Local ML risk engine with ONNX artifact
- Dynamic traffic, GPS, route-failure and hospital-staleness simulation
- Human-in-the-loop safety boundary

## 9. Deployment/accessibility
The application is Windows-friendly and can run locally without cloud AI for the risk model. The same inference contract can target Snapdragon/QNN when the appropriate Qualcomm runtime is installed.

## 10. Safety
**AI recommends. Deterministic systems verify. Human operators remain authoritative.** The model never directly selects an ambulance or hospital and cannot override road closures, fleet availability, hospital capacity or operational constraints.

## 11. Demo flow
1. Start Live Simulation.
2. Click **Run Full Demo**.
3. Show the initial local AI risk/priority/confidence panel.
4. Show deterministic ambulance and hospital selection on the Mumbai GIS map.
5. Let traffic rise.
6. Show **AI REASSESSMENT**.
7. Trigger/show the road closure and route failure.
8. Show real alternate-route calculation and updated AI state.
9. Show hospital-capacity reassessment.
10. Close on the runtime/provider panel and human-approval safety boundary.

## 12. Scalability
The modular inference API can be extended to richer incident classifiers, Qualcomm AI Hub models, computer vision verification and real operational feeds while keeping the deterministic safety boundary intact.

## 13. Why useful
Emergency operations involve rapidly changing information. A local model can provide a fast, transparent risk signal while the existing GIS layer keeps the response grounded in actual resource and route constraints.

## 14. Technology stack
React, Vite, Leaflet, Python, FastAPI, NetworkX/A* routing, NumPy, scikit-learn-trained model, ONNX artifact, optional ONNX Runtime/QNN execution.

## Limitations
Training data included in this repository is synthetic simulation data and is not clinical data. This prototype is not a certified emergency dispatch system. Hardware/runtime performance must be measured on the target Snapdragon device before making performance claims.
