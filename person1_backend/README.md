# ResQMesh — AI/LLM Workflow (Person 1)

This is **only the AI/LLM side** of ResQMesh. It does not contain any ambulance
optimization, routing, hospital selection, backend APIs, or frontend — those belong
to Person 2 (deterministic engine) and Person 3 (UI).

## What this does

```
Emergency text (untrusted)
        │
        ▼
1. Incident Extractor        (nodes/extractor.py)
        │
        ▼
2. Ambiguity Gate             (nodes/ambiguity.py)
        │
        ▼  (optional human clarification merge — nodes/clarification.py)
        │
        ▼
4. Priority / Severity Cues   (nodes/priority.py)
        │
        ▼
   IncidentState  ────────────────────────────►  PERSON 2's deterministic engine
                                                   (ambulance assignment, routing,
                                                    hospital selection)
                                                          │
                                                          ▼
                                                   Proposed dispatch plan
                                                          │
        ◄─────────────────────────────────────────────────
        ▼
6. Adversarial Reviewer       (nodes/reviewer.py)
        │
        ▼
   ReviewResult  ─────────────────────────────►  PERSON 2's deterministic verifier
                                                          │
                                                          ▼
                                                   Verified plan
                                                          │
        ◄─────────────────────────────────────────────────
        ▼
7. Explanation Generator      (nodes/explainer.py)
        │
        ▼
   Dispatcher-readable explanation
```

**The LLM never chooses or authorizes a dispatch.** It extracts, questions, flags,
challenges, and explains. `IncidentState` and `ReviewRequest`/`ReviewResult` don't even
have a field for "assign ambulance X" — that's a structural guarantee, not just a prompt
instruction (see `tests/test_injection.py`).

## The JSON contract with Person 2

Defined once, in two equivalent forms:
- `schemas/models.py` — Pydantic models (Python-side source of truth)
- `schemas/incident_schema_v1.json` — JSON Schema (language-agnostic, for validation
  in Person 2's stack if they're not using Python/Pydantic)

Version pinned via `incident_schema_version = "1.0"`. Don't change field names/types
without bumping this version and telling Person 2.

### Three objects cross the boundary:

| Object | Direction | Produced by | Consumed by |
|---|---|---|---|
| `IncidentState` | Person 1 → Person 2 | `pipeline.build_incident_state()` | Person 2's optimizer |
| `ReviewResult` | Person 1 → Person 2 | `nodes.reviewer.review_plan()` | Person 2's verifier |
| `Explanation` | Person 1 → Person 3 (UI) | `nodes.explainer.generate_explanation()` | Dispatcher UI |

Person 2 does **not** need to read any prompt files or know how the LLM works —
they only need `schemas/models.py` (or the JSON Schema) and the three objects above.

See `examples/valid_input.json`, `examples/ambiguous_input.json`, and
`examples/invalid_input.json` for concrete examples of each.

## Setup

```bash
cd llm_workflow
pip install -r requirements.txt
cp .env.example .env
# edit .env and set LLM_API_KEY
```

## Running the pipeline

```python
from pipeline import build_incident_state
from nodes.clarification import apply_human_clarification
from nodes.reviewer import review_plan
from nodes.explainer import generate_explanation

# 1-2-4: extract + ambiguity check + priority cues
incident, ambiguity = build_incident_state(
    "There are around 4 people injured near Bandra station. "
    "One person is unconscious and another has severe bleeding."
)

if ambiguity.needs_clarification:
    # Person 3's UI shows ambiguity.questions to a human dispatcher, gets an answer back
    incident = apply_human_clarification(incident, {"patient_count": 4})

# --- hand incident (as .model_dump()) to Person 2's engine here ---
# proposed_plan = person2.optimize(incident)

# 6: adversarial review of Person 2's proposed plan
review = review_plan(
    incident=incident,
    fleet_state={...},       # from Person 2
    road_state={...},        # from Person 2
    hospital_state={...},    # from Person 2
    proposed_plan={...},     # from Person 2
)
# --- hand review (as .model_dump()) to Person 2's deterministic verifier ---

# 7: after Person 2's verifier confirms the plan, generate the explanation
explanation = generate_explanation(
    verified_facts={...}, assignment={...}, route={...},
    hospital={...}, uncertainty=incident.uncertainty,
)
```

## Baseline vs. ResQMesh (Part 10 & 11)

```bash
python -m evaluation.evaluate
```

This runs the 10 synthetic test cases (`evaluation/test_cases.py`) through:
- the full staged pipeline (`pipeline.build_incident_state`)
- the single-prompt baseline (`baseline/single_prompt_baseline.py`) — one big prompt
  that (unsafely, on purpose) recommends ambulance/route/hospital directly, kept only
  for comparison

`evaluation.evaluate.compare_baseline_vs_pipeline()` runs both side by side and reports,
per case, whether the baseline tried to directly authorize a dispatch (it will — that's
the point) versus the pipeline, which structurally cannot.

## Reliability / fail-safe behavior (Part 13)

Every LLM node (`nodes/*.py`) goes through `clients/llm_client.py`, which:
1. Retries transient failures (`LLM_MAX_RETRIES`, exponential backoff).
2. Strips markdown fences and extracts the first valid JSON object from the response.
3. Re-prompts once if JSON parsing fails, asking the model to return valid JSON only.
4. If it still fails: **never invents data.** Each node has its own explicit fail-safe:
   - `extract_incident` → returns an `IncidentState` with `uncertainty=1.0` and
     `missing_decision_critical_fields=["ALL_FIELDS_EXTRACTION_FAILED"]`.
   - `detect_ambiguity` → defaults to `needs_clarification=True` (never silently assumes
     everything is fine).
   - `review_plan` → defaults to `challenge_found=True, severity="HIGH"` (a reviewer
     failure is surfaced, not swallowed).
   - `generate_explanation` → returns an honest "explanation unavailable" message.

Every call is logged to `logs/llm_calls.jsonl` with model, prompt_version, timestamp,
input, output, latency, and token usage (`nodes/logger.py`).

## Prompt injection defense (Part 12)

Every prompt explicitly tells the model the input is untrusted data, never instructions
(see any file in `prompts/`). Structurally, `IncidentState` has no field that could
authorize a dispatch, so even a successful injection can't cause one. See
`evaluation/test_cases.py::TC09_prompt_injection` and `tests/test_injection.py`.

## Running tests

```bash
python run_tests.py
```

All unit tests use `tests/fake_client.py` (a canned-response fake) so they run without
`LLM_API_KEY` or network access. For a live end-to-end run against the real model:

```bash
python -m evaluation.evaluate
```

## File structure

```
llm_workflow/
├── prompts/                        versioned prompt templates
│   ├── incident_extractor_v1.txt
│   ├── ambiguity_gate_v1.txt
│   ├── priority_cues_v1.txt
│   ├── adversarial_reviewer_v1.txt
│   └── explanation_generator_v1.txt
├── schemas/
│   ├── models.py                   Pydantic contract (source of truth)
│   └── incident_schema_v1.json     JSON Schema (language-agnostic)
├── clients/
│   └── llm_client.py               retries, JSON extraction, logging, fail-safe
├── nodes/
│   ├── extractor.py                Part 1
│   ├── ambiguity.py                Part 2
│   ├── clarification.py            Part 3
│   ├── priority.py                 Part 4
│   ├── reviewer.py                 Part 6
│   ├── explainer.py                Part 7
│   └── logger.py                   Part 9 call logging
├── baseline/
│   └── single_prompt_baseline.py   Part 10
├── evaluation/
│   ├── test_cases.py                Part 11 synthetic cases
│   └── evaluate.py                  Part 11 runner + baseline comparison
├── tests/                          offline unit tests (FakeLLMClient)
├── examples/                       valid / ambiguous / invalid IncidentState examples
├── pipeline.py                     orchestrates Parts 1,2,4 → IncidentState
├── run_tests.py
├── requirements.txt
├── .env.example
└── README.md
```

## How Person 2 connects to my work

Person 2 never imports my prompt files or LLM client directly. They only need:

1. **Input:** `IncidentState` (JSON, matches `schemas/incident_schema_v1.json`) — call
   `pipeline.build_incident_state(raw_text)` (or receive it over whatever transport we
   agree on — HTTP, shared queue, etc.) and feed `incident.model_dump()` into their
   optimizer.
2. **Output → my input:** after producing a `proposed_plan`, call
   `nodes.reviewer.review_plan(incident, fleet_state, road_state, hospital_state, proposed_plan)`
   and pass the resulting `ReviewResult` into their deterministic verifier.
3. **Output:** once their verifier confirms the plan, call
   `nodes.explainer.generate_explanation(...)` to get the dispatcher-facing text.

They do not need to understand prompt engineering, retries, or JSON-repair logic —
that's all encapsulated behind these three function calls.
