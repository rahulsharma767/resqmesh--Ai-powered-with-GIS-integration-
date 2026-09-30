# ResQMesh AI — Exact Demo Script

## Before the demo
1. Start the backend on port 8000.
2. Start Vite on port 5173.
3. Open **Live Simulation**.
4. Confirm the map loads and the AI panel is visible.

## 60–90 second run
1. Click **Run Full Demo**.
2. Keep the speed at **5x**.
3. Point to **Risk Score / Priority / Confidence** while the first AI assessment arrives.
4. Point to the selected ambulance and destination hospital.
5. Let the simulation reach the traffic event. Say: **“The operational state changed, so the local model reassesses instead of treating the original answer as permanent.”**
6. When the route failure appears, point to the red blocked segment.
7. Point to the **ROUTE_RECALCULATED** event and the new route.
8. Point to the AI reassessment event and provider label.
9. When hospital data becomes stale, point to the destination update/reassessment.
10. Finish on: **“AI recommends. Deterministic systems verify. Human operators remain authoritative.”**

## If QNN is not active
Say exactly: **“This development machine is using the local fallback. The application checks for Qualcomm QNN at runtime and only reports QNN when the provider is actually present.”**

Never claim NPU execution unless the status panel says it is verified.
