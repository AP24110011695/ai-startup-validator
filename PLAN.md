# PLAN.md — AI Startup Validator

A multi-agent GenAI application: the user submits a business idea, four agents (Researcher → Market Analyst → Critic → Evaluator) run as an orchestrated LangGraph pipeline, and the user gets back a scored feasibility report (0–100 + verdict).

## Tech Stack & Key Decisions

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn | Serves both the API and the static frontend. |
| Orchestration | LangGraph `StateGraph` | Shared `TypedDict` state, conditional edges, per-node retry wrapper. |
| LLM | Google Gemini — default model `gemini-2.5-flash`, overridable via `LLM_MODEL` env var | **Assumption:** you hinted at `GEMINI_API_KEY`, so Gemini is the default. Native JSON-output mode. All LLM access is isolated in `backend/llm.py`, so swapping to OpenAI / Anthropic / Groq later is a one-file change — say so at the Phase 8 pause if you prefer another provider. Exact model id is verified when the real key arrives (Phase 8). |
| Web search | Tavily (primary) → SerpAPI (fallback) → LLM's own knowledge (last resort, flagged **unverified**) | Also mocked in mock mode. Phases 1–7 need **no API keys at all**. |
| Frontend | Plain HTML/CSS/JS single page, served by FastAPI | **Deviation from React + Tailwind — explained below.** |
| Storage | In-memory run store (dict keyed by `run_id`) | No database for v1, per spec. |
| Config | `.env` via `python-dotenv`; `USE_MOCK=true` default until Phase 8 | One env var flips mock ↔ real. |

**Frontend deviation (explained):** the UI is one page with three views (form → progress → report). Vanilla JS + hand-written CSS means zero build tooling (no Node/npm on Windows), native streaming support, direct static serving from FastAPI, and the simplest possible deploy — matching your "Simple > flashy" rule. The API contract (SSE events + JSON report) keeps a future React/Tailwind rewrite independent of the backend. This is your spec's "plain HTML/CSS/JS if simpler" branch; it is simpler here.

**Streaming choice:** per-agent progress is streamed with Server-Sent Events (SSE) — one-way server→client progress is exactly what SSE is for, with no WebSocket complexity.

## Target Repo Structure (final state)

```
AI Startup Validator/
├── backend/
│   ├── __init__.py
│   ├── main.py           # FastAPI app + endpoints (Phase 8)
│   ├── config.py         # env/settings + runtime API-key hot-swap (Phase 8)
│   ├── logging_setup.py  # logs/app.log configuration
│   ├── state.py          # LangGraph shared state schema (Phase 2)
│   ├── schemas.py        # pydantic I/O models (Phase 2)
│   ├── prompts.py        # agent personas, prompts, scoring rubric (Phase 2+)
│   ├── llm.py            # call_llm: mock/real, retry, error mapping (Phase 3/8)
│   ├── tools.py          # web_search: tavily → serpapi → mock (Phase 3)
│   ├── agents.py         # the 4 node functions + retry wrapper (Phases 3–7)
│   └── graph.py          # StateGraph wiring (Phase 7)
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── tests/                # pytest suite (grows per phase)
├── logs/                 # app.log (gitignored)
├── .env.example
├── requirements.txt
├── pytest.ini
├── Dockerfile            # Phase 10
└── PLAN.md · IMPLEMENTATION.md · PROGRESS.md · README.md · LEARN.md (final)
```

## Pipeline Graph (drawn here in Phase 2, built in Phase 7)

```
START
  │
  ▼
validate_idea ────(too vague / unusable input)────► END  ("need more detail" payload, no report)
  │ valid
  ▼
research ─────────► [Tavily → SerpAPI → LLM knowledge fallback]
  │
  ▼
analyze_market ───► [consumes research; optional 1–2 targeted searches of its own]
  │
  ▼
critique ─────────► [consumes idea + research + market]
  │
  ▼
evaluate ─────────► [synthesizes all three; score + verdict]
  │
  ▼
 END  (final report JSON)
```

Rule: any agent that fails after retries degrades gracefully (valid-but-empty output + a recorded error + a UI-visible warning) and the pipeline **continues** — the graph never aborts because one agent failed.

---

## Phase 1 — Project Setup & Environment

**Goal:** A runnable skeleton — venv, dependencies, config, logging, and an empty FastAPI server serving a placeholder page.

**Tasks:**
- [ ] `git init`; create `.gitignore` (`.venv/`, `.env`, `logs/`, `__pycache__/`, `.pytest_cache/`)
- [ ] Create folders: `backend/`, `frontend/`, `tests/`, `logs/`
- [ ] `requirements.txt`: fastapi, uvicorn[standard], langgraph, google-genai, tavily-python, python-dotenv, httpx, pytest
- [ ] Create virtual env `.venv` and install deps (Windows/Git Bash compatible commands, documented in README)
- [ ] `.env.example`: `GEMINI_API_KEY=`, `TAVILY_API_KEY=`, `SERPAPI_API_KEY=`, `USE_MOCK=true`, `LLM_MODEL=gemini-2.5-flash`, `LOG_LEVEL=INFO`
- [ ] `backend/config.py` — loads `.env` once, exposes settings as module-level constants (includes `set_api_key()` stub used by the Phase 8 hot-swap)
- [ ] `backend/logging_setup.py` — logging to `logs/app.log` + console
- [ ] `backend/main.py` — FastAPI app: `GET /health` → `{"status": "ok"}`, serves `frontend/` as static files (placeholder page)
- [ ] `pytest.ini` (root on `sys.path` so `backend.*` imports resolve in tests)
- [ ] README.md skeleton (title, one-paragraph pitch, "full setup instructions come in Phase 10")

**Files:** `backend/__init__.py`, `backend/config.py`, `backend/logging_setup.py`, `backend/main.py`, `frontend/index.html` (placeholder), `requirements.txt`, `.env.example`, `.gitignore`, `pytest.ini`, `README.md`

**Done when:** `.venv` exists and all deps import cleanly; `uvicorn backend.main:app` starts; `GET /health` returns ok; `logs/app.log` receives a startup entry; placeholder page is served at `/`; initial git commit made.

---

## Phase 2 — Agent Architecture & State Design

**Goal:** Freeze all contracts before agent code: shared state schema, per-agent output schemas, agent personas/prompts, and the graph topology.

**Tasks:**
- [ ] `backend/state.py` — `ValidatorState(TypedDict)` with fields:
  - `idea`, `run_id`, `created_at` — inputs
  - `progress` — **append-only** `[{agent, status: started|finished, ts}]` (feeds Phase 8 SSE) — uses an `Annotated[list, operator.add]` reducer so LangGraph merges appends instead of overwriting
  - `errors` — **append-only** `[{agent, type, message}]`
  - `data_flags` — **append-only** list of strings (`"mock_mode"`, `"research_unverified"`, …)
  - `research`, `market`, `critique`, `evaluation` — one dict each, written exactly once by its owning agent
- [ ] `backend/schemas.py` — pydantic models: `Competitor`, `ResearchFindings`, `MarketAnalysis`, `Critique`, `Risk`, `FinalEvaluation`, `Report` — every model valid even in degraded mode (nullable fields + `verified` flags)
- [ ] `backend/prompts.py` — persona + system-prompt drafts for the 4 agents (constants; refined in Phases 3–6)
- [ ] Draw the graph (nodes, edges, conditional edge on input validation) — the diagram in this doc, reviewed and committed
- [ ] Document ownership: which node writes which state keys (nothing else may touch them)

**Files:** `backend/state.py`, `backend/schemas.py`, `backend/prompts.py`, this doc (graph diagram)

**Done when:** all three modules import cleanly; each schema round-trips a sample payload via `Model.model_validate(...)`; the diagram and state-ownership table are committed; no orchestration code yet (Phase 7).

---

## Phase 3 — Researcher Agent

**Goal:** Turn the idea into structured competitive intel using live web search, with graceful fallback to LLM knowledge.

**Tasks:**
- [ ] `backend/tools.py` — `web_search(query) -> [{title, url, snippet}]`: Tavily → (on failure) SerpAPI → (on failure or `USE_MOCK`) mock results; explicit timeout; every failure logged
- [ ] `backend/llm.py` — `call_llm(prompt, schema)`: mock implementation returning realistic canned JSON (real implementation lands in Phase 8 behind the same signature)
- [ ] `backend/agents.py` — `research_node(state)`: builds 2–4 targeted search queries from the idea, runs search, LLM call extracts/dedupes competitors into `ResearchFindings`
- [ ] Fallback path: if all search providers fail → LLM answers from its own knowledge with `verified=false`, `data_flags += "research_unverified"` (per IMPLEMENTATION.md)
- [ ] Mock mode: `mock_search()` + mock LLM return realistic canned competitor data, clearly marked MOCK_MODE
- [ ] `tests/test_research.py` — mock happy path; induced search-failure path (monkeypatched) proving fallback + logging + error entry

**Files:** `backend/tools.py`, `backend/llm.py`, `backend/agents.py`, `tests/test_research.py`

**Done when:** node returns schema-valid `ResearchFindings` in mock mode; degraded run yields `verified=false` + `research_unverified` flag + log entries; only `research_node` writes the `research` key.

---

## Phase 4 — Market Analyst Agent

**Goal:** Consume the researcher's output and produce market size, trend, and target-audience analysis; run 1–2 targeted searches of its own if data is thin.

**Tasks:**
- [ ] `analyze_market_node(state)`: prompt includes research findings (read-only); optional targeted TAM/trend queries when research lacks data; returns `MarketAnalysis` with per-estimate confidence + unverified flags
- [ ] Mock: canned realistic `MarketAnalysis`
- [ ] `tests/test_analyst.py` — chained `research_node → analyze_market_node` (proves state passing between nodes); degraded test with empty research

**Files:** `backend/agents.py`, `tests/test_analyst.py`

**Done when:** output is schema-valid; state after the node still contains `research` intact (append/merge rule verified by test); works in mock + degraded modes.

---

## Phase 5 — Critic Agent

**Goal:** Devil's-advocate pass: concrete risks, weak assumptions, and failure modes grounded in the idea and prior findings.

**Tasks:**
- [ ] `critique_node(state)`: persona = skeptical senior VC; consumes idea + research + market; returns `Critique` = `risks[{risk, severity, category}]`, `weak_assumptions[]`, `failure_modes[]`, `hardest_question`
- [ ] Severity rubric documented in `prompts.py`: high = "likely fatal if true", medium = "materially threatens the business", low = "worth monitoring"
- [ ] Mock: canned `Critique`
- [ ] `tests/test_critic.py` — chained 3-node run; output schema-valid; severities present; state holds research + market + critique simultaneously

**Files:** `backend/agents.py`, `tests/test_critic.py`

**Done when:** schema-valid output referencing upstream findings; three-node chained state verified.

---

## Phase 6 — Evaluator / Compiler Agent

**Goal:** Synthesize all three agents' outputs into a numeric feasibility score, verdict, and actionable summary.

**Tasks:**
- [ ] Scoring rubric (documented in `prompts.py` + README): Market opportunity **25** · Differentiation/moat **20** · Feasibility & execution **20** · Business viability/monetization **20** · Timing/trend fit **15** — each dimension scored 0–100 by the LLM, weighted sum = final 0–100 score
- [ ] Verdict bands: **≥75 Promising** · **50–74 Needs Rework** · **<50 High Risk**
- [ ] `evaluate_node(state)`: consumes research + market + critique; returns `FinalEvaluation` = `{score, subscores, verdict, executive_summary, strengths[], recommendation, next_steps[]}`
- [ ] Mock: canned `FinalEvaluation` consistent with the canned upstream data (e.g., 62 / "Needs Rework")
- [ ] `tests/test_evaluator.py` — full 4-node plain-function sequence; assert complete report + all upstream outputs still present in state

**Files:** `backend/agents.py`, `backend/schemas.py` (FinalEvaluation finalized), `tests/test_evaluator.py`

**Done when:** 4-node pipeline produces a complete, schema-valid report in mock mode; state append/merge verified; rubric documented.

---

## Phase 7 — LangGraph Orchestration

**Goal:** Wire the four nodes into a real `StateGraph` with conditional edges, retry handling, and progress events.

**Tasks:**
- [ ] `backend/graph.py` — nodes: `validate_idea`, `research`, `analyze_market`, `critique`, `evaluate`; edges: `START → validate_idea → (conditional) → research → analyze_market → critique → evaluate → END`
- [ ] `validate_idea` + conditional edge: input < ~10 chars or contains no letters → route to `END` early with a "need more detail" payload instead of a report
- [ ] `with_retry(node)` wrapper: on LLM/parse failure, retry up to 2 times with an adjusted prompt (e.g., "Respond ONLY with valid JSON matching this schema: …"); after the final failure → degraded valid output + `errors` entry — graph never aborts on one agent failing
- [ ] Progress events: wrapper appends `{agent, status, ts}` to `state.progress` on start/finish (feeds Phase 8 SSE)
- [ ] `build_graph()` compiled once at module level + `run_validation(idea)` helper
- [ ] `tests/test_graph.py` — mock happy path; invalid-input early-exit path; forced-failure path proving 2 retries then graceful degradation

**Files:** `backend/graph.py`, `backend/agents.py` (retry wrapper), `tests/test_graph.py`

**Done when:** compiled graph runs end-to-end in mock via pytest; final state contains progress events for all 4 agents + the complete report; garbage input ends early with the clarification payload; forced-failure test proves retry-then-degrade.

---

## Phase 8 — Backend API Layer ⏸️ PAUSE POINT

**Goal:** Expose the graph over HTTP with live per-agent progress streaming, plus quota-safe key handling.

**Tasks:**
- [ ] `POST /api/validate {idea}` → starts the run in a background thread, returns `{run_id}` immediately; events buffered in the in-memory run store
- [ ] `GET /api/runs/{run_id}/events` → SSE stream (`text/event-stream`): replays buffered events from the start, then streams live: `agent_status` events per node → `report` (final JSON) or `error` `{code, message}`
- [ ] `GET /api/runs/{run_id}` → re-fetch a finished run's report/status
- [ ] `POST /api/key {api_key}` → hot-swaps `GEMINI_API_KEY` in memory (and appends to `.env`) — no restart, no terminal, no manual editing
- [ ] `backend/llm.py` real implementation behind `USE_MOCK=false`: `google-genai` SDK, JSON response mode, explicit timeout; error mapping: HTTP 429 / `RESOURCE_EXHAUSTED` / quota-or-credit messages → `quota_exceeded`; timeout → `llm_timeout`; else `llm_error`
- [ ] Quota simulation switch (`FAKE_QUOTA_ERROR=1`) so the full quota UI flow is testable **before** the real key exists
- [ ] `tests/test_api.py` — stream + error paths via FastAPI TestClient in mock mode

**Files:** `backend/main.py`, `backend/llm.py`, `backend/config.py`, `tests/test_api.py`

**Done when:** mock SSE stream observed end-to-end (agent_status events, then report); simulated quota returns a structured `quota_exceeded` event; `POST /api/key` swaps the key without a restart.

**✋ STOP HERE and ask the user for: `GEMINI_API_KEY` (required), `TAVILY_API_KEY` (recommended, free tier), `SERPAPI_API_KEY` (optional fallback).** Resume autonomously once provided — no further questions for the rest of the project.

---

## Phase 9 — Frontend UI

**Goal:** Clean single-page UI: form → per-agent progress → formatted report, plus the quota key flow. (Hard UI constraints live in IMPLEMENTATION.md §4.)

**Tasks:**
- [ ] `frontend/index.html` / `style.css` / `app.js` — three client-side views; consumes the SSE endpoint
- [ ] Progress view: 4 named agent rows (name + one-line role) with states queued → working → done (subtle spinner/check only)
- [ ] Report view: prominent score badge (0–100 + verdict chip, green/amber/red), then sections: Summary & verdict · Competitors (with source links) · Market analysis · Risks & weak assumptions · Recommendation & next steps; warning banner when `research_unverified`; visible "MOCK DATA" badge in mock mode
- [ ] Quota flow: on `quota_exceeded` → inline card "Your API key limit has been reached. Paste a new API key to continue." + key input + button → `POST /api/key` → auto-retry the run
- [ ] Design constraints (hard): near-white background, ink/slate text, ONE accent color, green/amber/red reserved for verdicts/status; system font stack; generous whitespace; no gradients, no glassmorphism, no robot imagery, no chat bubbles

**Files:** `frontend/index.html`, `frontend/style.css`, `frontend/app.js`

**Done when:** a full mock run drives form → progress → report correctly; UI reviewed against every design constraint; quota card flow works against the simulated quota switch.

---

## Phase 10 — Testing, Error Handling Polish & Deployment Prep

**Goal:** Harden edge cases, finalize docs, and deploy the app live on Render's free tier.

**Tasks:**
- [ ] Edge-case tests: vague input ("make money"), very long input, total search failure, LLM timeout, quota error, malformed LLM JSON (forced → retry path), two concurrent runs
- [ ] Full pytest suite green (graph + API + schemas)
- [ ] README.md final: what it is, architecture diagram, setup (Windows + Unix), required keys, mock vs real mode, demo script, API reference, scoring rubric, and the exact Render deploy steps (connect GitHub repo, set env vars, deploy)
- [ ] `Dockerfile` (single container: uvicorn serving API + static frontend) + `.dockerignore`
- [ ] **Deploy to Render (free tier)** — one web service running the Dockerfile, serving both the FastAPI backend and the static frontend. No credit card required for this tier.
  - Why Render only: Railway's free tier is a 30-day trial with $5 credit, then requires a paid plan — rejected, no risk of charges accepted. Fly.io requires a credit card for new users and has no free tier — rejected. Vercel isn't suitable: serverless functions have a 5-minute timeout and aren't built for a long-running FastAPI backend with SSE streaming — rejected.
  - Expected behavior, not a bug to fix: free Render web services spin down after 15 minutes of inactivity and take 30–60 seconds to wake on the next request.
- [ ] Real end-to-end: `USE_MOCK=false`, run 2–3 real ideas through the UI with the real key; fix whatever surfaces

**Files:** `tests/`, `README.md`, `Dockerfile`, `.dockerignore`

**Done when:** pytest suite green; real-key end-to-end validated through the UI; a stranger can clone + run from README alone; Docker image builds and serves the app; app is live on a Render free-tier URL, accessible without a credit card, and the README includes the exact Render deploy steps (connect GitHub repo, set env vars, deploy).

---

**Post-plan deliverable (not a phase):** after Phase 10 passes with the real API key, write `LEARN.md` — the interview-prep guide specified in IMPLEMENTATION.md §10.
