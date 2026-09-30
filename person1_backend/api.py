"""
Minimal FastAPI wrapper around Person 1's existing pipeline.

    POST /api/analyze  { "raw_text": "..." }
        -> { "incident_state": IncidentState, "ambiguity_result": AmbiguityResult }

This file does NOT reimplement any extraction/safety logic — it only calls
`pipeline.build_incident_state()` and serializes the EXISTING IncidentState /
AmbiguityResult Pydantic models. No competing schema is introduced.

Mode is controlled entirely by the PERSON1_MODE env var (see clients/llm_client.py):
    PERSON1_MODE=mock  (default) -> deterministic offline heuristics, no LLM calls
    PERSON1_MODE=real             -> calls the configured LLM_PROVIDER (needs LLM_API_KEY)

Run:
    uvicorn api:app --reload --port 8000
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pipeline import build_incident_state

app = FastAPI(title="ResQMesh Person 1 API")

# Local dev CORS only — the frontend runs on Vite's default port. Extend via
# CORS_ALLOWED_ORIGINS (comma-separated) if the frontend runs elsewhere.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_origins = os.environ.get("CORS_ALLOWED_ORIGINS", _default_origins).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    raw_text: str


@app.get("/api/health")
def health():
    return {"status": "ok", "person1_mode": os.environ.get("PERSON1_MODE", "mock")}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    if not req.raw_text or not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text must not be empty")

    # raw_text is untrusted emergency input — build_incident_state() and its
    # nodes are responsible for treating it as data, never as instructions
    # (see nodes/extractor.py and tests/test_injection.py).
    incident_state, ambiguity_result = build_incident_state(req.raw_text)

    return {
        "incident_state": incident_state.model_dump(),
        "ambiguity_result": ambiguity_result.model_dump(),
    }
