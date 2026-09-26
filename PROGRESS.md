# PROGRESS.md — AI Startup Validator

## Phase 1 — Project Setup & Environment
**Status:** done (2026-09-27)

**What was built:** Repo skeleton (`backend/`, `frontend/`, `tests/`, `logs/`); `.venv` (Python 3.12.10) with all deps installed (fastapi 0.141, langgraph 1.2.12, google-genai 2.25, tavily-python 0.8.4, uvicorn, python-dotenv, httpx, pytest 9.1); `.gitignore` + `.env.example`; `backend/config.py` (settings from `.env`, `API_KEYS` dict, `set_api_key()` stub for Phase 8); `backend/logging_setup.py` (console + `logs/app.log`); `backend/main.py` (FastAPI: `GET /health`, static frontend mount, startup log line); `pytest.ini`; placeholder `frontend/index.html`; README skeleton. **Verified:** `uvicorn backend.main:app` starts; `GET /health` → `{"status":"ok","mock_mode":true}`; `/` serves the placeholder page; `logs/app.log` receives the startup entry; git repo initialized with initial commit.

**Assumptions:** Python 3.12.10 found on PATH as `python` (satisfies the 3.11+ requirement). `USE_MOCK` defaults to true when `.env` is absent, so no `.env` file was created yet (it will be created from `.env.example` / by the Phase 8 key flow). `/health` returns an extra `mock_mode` field beyond the planned `{"status":"ok"}` — useful for the UI to badge mock data.

**Known issues:** none.

## Phase 2 — Agent Architecture & State Design
**Status:** done (2026-09-27)

**What was built:** `backend/state.py` — `ValidatorState(TypedDict)` with append-only `progress` / `errors` / `data_flags` lists using `Annotated[list, operator.add]` reducers, plus the node-ownership table in the module docstring; `backend/schemas.py` — pydantic models (`Competitor`, `ResearchFindings`, `MarketAnalysis`, `MarketEstimate`, `Risk`, `Critique`, `Subscores`, `FinalEvaluation`, `Report`), all valid in degraded mode (empty defaults + `verified` flags); `backend/prompts.py` — persona + JSON-only output contract drafts for the 4 agents (refined in Phases 3–6); `tests/test_schemas.py` — round-trip tests for every schema + degraded-defaults test + prompt-presence test. **Verified:** 4/4 pytest tests pass; all three modules import cleanly; graph diagram (PLAN.md) and ownership table (state.py) committed.

**Assumptions:** added `input_rejected: bool` to state (written by `validate_idea` in Phase 7) as the conditional-edge signal — it was implied by the PLAN.md graph but not named as a field until now. Added a small permanent test file (`tests/test_schemas.py`) beyond the plan's file list to lock the acceptance criteria ("schemas round-trip") into the suite.

**Known issues:** none.

## Phase 3 — Researcher Agent
**Status:** done (2026-09-27)

**What was built:** `backend/tools.py` — `web_search()`: mock → Tavily REST → SerpAPI REST (via httpx, explicit 15s timeouts, every provider failure logged, empty list = "no live results"); `backend/llm.py` — `call_llm(agent, system, user, schema)` with the mock implementation (canned per-agent JSON, validated through the target schema) and the same signature the real Gemini call gets in Phase 8; `backend/agents.py` — `research_node()` (heuristic 3-query generation → search → LLM extraction/dedup → `ResearchFindings`) with LLM-knowledge fallback: no search results ⇒ `verified=false` + `research_unverified` flag + `search_unavailable` errors entry; `tests/test_research.py` — 4 tests. **Verified:** 8/8 pytest pass (happy path schema-valid + verified; degraded path flagged + logged; ownership of `research` key; provider-failure logging).

**Assumptions:** search implemented against Tavily/SerpAPI REST endpoints directly via httpx for guaranteed explicit timeouts, so `tavily-python` is currently installed-but-unused (left in requirements.txt for now); search-query generation is heuristic (no extra LLM call); `verified` is set deterministically from search success rather than trusting the LLM's own claim; LLM-call-level retry + real Gemini call deliberately deferred to Phase 8 (untestable before a key), node-level retry wrapper in Phase 7 per plan.

**Known issues:** none.
