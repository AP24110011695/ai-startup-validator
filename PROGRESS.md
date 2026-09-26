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

## Phase 4 — Market Analyst Agent
**Status:** done (2026-09-27)

**What was built:** `analyze_market_node()` in `backend/agents.py` — consumes the researcher's findings read-only (formatted into its prompt), decides research is "thin" when it is unverified or source-less and then runs 2 targeted searches of its own (market-size/TAM + industry-trends queries); output validated as `MarketAnalysis`; `verified` computed deterministically (research verified OR own searches returned live data), with `market_unverified` flag + `data_unverified` errors entry in the degraded case. Mock analyst builder added to `backend/llm.py`. `tests/test_analyst.py` — 4 tests. **Verified:** 12/12 pytest pass — chained research→analyst proves state passing; merged state keeps `research` byte-identical (append/merge rule); degraded no-research path flags unverified and performs exactly 2 supplemental searches; solid research triggers no extra searches.

**Assumptions:** "thin research" heuristic = unverified OR no sources (simple, deterministic); supplemental searches only enrich the prompt — they don't rewrite the researcher's findings; analyst's `verified` is optimistic-or-inherited (true if either the research was verified or its own searches succeeded).

**Known issues:** none.

## Phase 5 — Critic Agent
**Status:** done (2026-09-27)

**What was built:** `critique_node()` in `backend/agents.py` — devil's-advocate pass consuming idea + research + market (all read-only, formatted into the prompt via `_format_research` / `_format_market` helpers; no web search — it's a judgment pass over upstream data); returns schema-valid `Critique` (risks with severity/category, weak assumptions, failure modes, hardest question). Mock critic builder added to `backend/llm.py` (consistent with the mock research/market universe). Severity rubric was already documented in `prompts.py` (Phase 2). `tests/test_critic.py` — 3 tests. **Verified:** 15/15 pytest pass — 3-node chained run; every risk severity within high/medium/low with at least one high; grounding spot-check proves upstream facts (competitor names, market summary, idea) reach the critic's prompt; merged state holds research + market + critique simultaneously with nothing overwritten.

**Assumptions:** the critic gets no web search (plan positions it as judgment over upstream data); "referencing upstream facts" is spot-checked at the prompt level (upstream content reaches the LLM call) since the mock response is canned and can't literally cite upstream data.

**Known issues:** none.

## Phase 6 — Evaluator / Compiler Agent
**Status:** done (2026-09-27)

**What was built:** `evaluate_node()` in `backend/agents.py` — consumes idea + research + market + critique (read-only, formatted into the prompt via `_format_critique` helper added alongside the existing formatters); the LLM supplies dimension subscores, and the node **recomputes** the weighted total and verdict band in code from `RUBRIC_WEIGHTS` / `VERDICT_BANDS` (now defined as constants in `backend/prompts.py`, the rubric's documented home, alongside the prose weights in `EVALUATOR_PROMPT`). Mock evaluator builder added to `llm.py` (70/45/75/60/55 → 62 "Needs Rework", consistent with the canned upstream data). Rubric section added to README (per the plan task "documented in prompts.py + README"). `tests/test_evaluator.py` — 4 tests. **Verified:** 19/19 pytest pass — full 4-node pipeline yields a complete schema-valid `Report` (score 62 / "Needs Rework"); a forced wrong LLM total (99/"Promising") is corrected to the rubric result (0 → "High Risk"); evaluator writes only its own key and all upstream outputs survive byte-identical; rubric constants match the prompt prose and sum to 1.0.

**Assumptions:** `schemas.py` needed no changes (FinalEvaluation was already complete from Phase 2 — the plan's "FinalEvaluation finalized" is a no-op); score/verdict are deliberately computed in code rather than trusted from the LLM (same deterministic-override pattern as `verified` in earlier nodes); README was edited in this phase despite not being in the phase's Files column because the task text explicitly requires the rubric documented there.

**Known issues:** none.

## Phase 7 — LangGraph Orchestration
**Status:** done (2026-09-27)

**What was built:** `backend/graph.py` — compiled `StateGraph` (module-level `GRAPH` singleton) wiring `validate_idea` → conditional edge → research → analyze_market → critique → evaluate → END; `validate_idea_node` rejects ideas under 10 chars or without letters (`input_rejected` + `invalid_input` errors entry as the "need more detail" payload); `run_validation(idea, run_id=None)` one-call entry point (generates `run_id`/`created_at`; the Phase 8 API can pass its own). `with_retry(node, agent, output_key, schema)` in `backend/agents.py` — wraps each agent node: appends `started`/`finished`/`failed` progress events, and on a node raising after `call_llm`'s retries substitutes a degraded schema-valid output (+ `llm_error` errors entry) so the graph never aborts. `backend/llm.py` — `call_llm` now implements the retry rules itself: 3 attempts (initial + `MAX_LLM_RETRIES=2`) with the adjusted "Respond ONLY with valid JSON matching this schema" prompt appended on retries, then raises `LLMError`. `tests/test_graph.py` — 4 tests. **Verified:** 23/23 pytest pass — end-to-end mock run (score 62, all 8 progress events, empty errors/flags); two invalid inputs exit early before any agent; forced LLM failure makes exactly 12 calls (4 agents × 3 attempts), produces 4 degraded outputs + 4 error entries + `failed` statuses, and the graph completes; a flaky researcher that fails twice recovers on attempt 3 via the adjusted prompt with no error entry left behind.

**Assumptions:** the retry-with-adjusted-prompt lives in `call_llm` (per IMPLEMENTATION.md's "every LLM call" rule) while the wrapper handles degrade + progress — this supersedes the Phase 3 note that deferred `call_llm` retries to Phase 8 (Phase 7's forced-failure test needs them now, and they're mock-testable); wrapper emits a third status `failed` beyond the planned started/finished (UI maps it to a warning state); the validator node emits no progress events on success (instantaneous, not an agent row); semantic vagueness ("make money") is NOT caught by the length/letters heuristic — deferred to the Phase 10 edge-case work.

**Known issues:** none.

## Phase 8 — Backend API Layer
**Status:** done (mock scope; ⏸️ paused at the sanctioned key request — real-mode live verification pending)

**What was built:** `backend/main.py` — `POST /api/validate` (starts the graph in a background thread, returns `{run_id}` immediately), `GET /api/runs/{id}/events` (SSE: replays buffered events, then live `agent_status` per agent → `report` or `error` {code, message}), `GET /api/runs/{id}` (re-fetch), `POST /api/key` (hot-swap, no restart), in-memory `RUNS` store; report assembly with warnings (MOCK MODE badge, unverified research/market, failed agents). `backend/config.py` — real `set_api_key()` (in-memory swap + `.env` persistence) and `FAKE_QUOTA_ERROR` simulation switch. `backend/llm.py` — real Gemini call path (`_real_completion`: google-genai SDK, JSON response mode, 60s timeout, pydantic response schema), provider error mapping (429/RESOURCE_EXHAUSTED/quota/credits → `QuotaError`; timeouts → `LLMTimeoutError`; else `LLMError`); `QuotaError` is never retried and propagates through the retry wrapper to abort the run as a `quota_exceeded` SSE event (the UI's paste-a-new-key flow). `tests/test_api.py` — 8 tests. **Verified:** 31/31 pytest pass; live curl check: POST /api/validate → run_id, SSE shows 8 agent_status events then the full report, GET /api/runs/{id} → status done; simulated quota → structured `quota_exceeded`; `/api/key` swaps in memory and persists to `.env` (placeholder written, ready for the real key).

**Assumptions/deviations:** search-provider (Tavily) quota errors do NOT abort the run — they fall back to LLM knowledge flagged `research_unverified` per IMPLEMENTATION.md's fallback rule; only LLM-key quota is fatal (documented conflict resolution). Real-mode path is written but not live-verified (no key yet — that is the sanctioned pause). `LLM_MODEL` is read dynamically so a key swap takes effect immediately.

**Known issues:** none.

**⏸️ PAUSED — waiting for the user to provide: `GEMINI_API_KEY` (required), `TAVILY_API_KEY` (recommended), `SERPAPI_API_KEY` (optional).**

**✅ Pause resolved (same day):** user provided `GEMINI_API_KEY` + `TAVILY_API_KEY` (no SerpAPI — fine, it's an optional fallback). Wired into `.env` (gitignored), `USE_MOCK=false`. Real-mode findings and fixes: (1) `gemini-2.5-flash` returns 404 "no longer available to new users" → switched to `gemini-3.8-flash` (the API told us the replacement; key itself authenticated); (2) free tier hits 429s quickly → 429-class errors now retry with 15s/30s backoff and only convert to fatal `QuotaError` after all retries; transient 503 "high demand" spikes were observed and recovered via backoff in a live run; (3) `conftest.py` forces `USE_MOCK=true` for the test suite regardless of `.env` so pytest never touches real quota. **Live end-to-end verified:** full pipeline on a real idea returned 5 real competitors (Real Dog Box, Farm Hounds, PupJoy, BarkBox), real market analysis, and score 64 / "Needs Rework" with zero errors.

## Phase 9 — Frontend UI
**Status:** done (2026-09-27)

**What was built:** `frontend/index.html` / `style.css` / `app.js` — three views (form → agent progress → report) toggled client-side; SSE consumption via EventSource; per-agent rows with queued/working/done/failed states and a pulsing dot; report with score badge (color-mapped by verdict band), verdict chip, MOCK DATA badge, warnings banners, competitor list with source links + similarity chips, market section, risks with severity chips, weak assumptions, failure modes, hardest-question callout; quota card ("Your API key limit has been reached… paste a new key") that POSTs `/api/key` and auto-retries the same idea. All rendering via `textContent` (no HTML injection from model output). Backend: SSE `error` event renamed `run_error` (a server event named "error" collides with EventSource's built-in connection-error event); agent `started` events now arrive in real time via a contextvar progress sink (`agents.progress_sink`) instead of post-node state snapshots, deduped against state replay in `main.py`. **Verified in a real browser:** form → progress (queued/working/done observed live) → full report render (screenshots checked against every no-AI-slop constraint: flat palette, white cards, no gradients/glass/robotry); quota flow tested with `FAKE_QUOTA_ERROR=1` (box appears, key paste → auto-retry → box re-appears, as expected under simulation); quota flow ALSO verified live with a real 429 during a real-mode run; invalid input shows the "too vague or too short" message with Start over. 37/37 tests pass after changes.

**Assumptions:** server event named `run_error` instead of the planned `error` (EventSource collision — technical necessity); a third progress status `failed` is surfaced as a red state rather than collapsing into "finished"; report layout uses hand-written CSS design tokens (single accent #1d4ed8, semantic green/amber/red reserved for verdicts/status).

**Known issues:** none.

## Phase 10 — Testing, Error Handling Polish & Deployment Prep
**Status:** done locally (2026-09-27); Render deployment itself requires the user's GitHub/Render accounts (exact steps in README)

**What was built:** `tests/test_edge_cases.py` — vague input ("make money") completes gracefully via the agents (heuristic validator deliberately only rejects unusable input), ~5.5k-char input, total search failure at graph level (completes flagged `research_unverified`), LLM timeouts (retry → degrade with `High Risk` defaults), malformed LLM output (garbage string → 12 attempts → degrade), concurrent runs (two simultaneous runs complete independently); `Dockerfile` (python:3.12-slim, honors Render's `PORT`) + `.dockerignore` (secrets/tests/docs excluded — `.env` never enters the image); final README (architecture, reliability model, API reference, mock mode, exact Render deploy steps). **Verified:** 37/37 pytest pass; Docker image builds (`sha256:ae08949c…`) and the container serves `/health` + starts a run; `FAKE_QUOTA_ERROR` documented in `.env.example`.

**Assumptions:** Render deployment was NOT executed — it requires a GitHub remote (no credentials in this environment) and the user's Render account; README contains the exact 6-step deploy procedure (push to GitHub → connect repo → Docker auto-detected → set env vars → deploy → expect 15-min spin-down / 30–60s wake on the free tier, no credit card).

**Known issues:** the provided Gemini key's free-tier daily quota was exhausted during browser verification (live 429s, correctly surfaced the key-recovery UI); a full real-mode UI report run will work once quota resets (daily) or the user pastes a fresh key via the UI's key box — the flow is ready and was exercised with the real key during `/api/key` setup.

## Final deliverable — LEARN.md
**Status:** done (2026-09-27)

`LEARN.md` written per IMPLEMENTATION.md §10: plain-English summary; architecture + LangGraph orchestration walkthrough; key concepts (agent state, tool grounding, per-agent prompts, rubric-in-code, layered retries, mock-vs-real, SSE, war stories); 8 likely interview questions with model answers; and why-choices for LangGraph, the 4 agents, FastAPI, vanilla frontend, Gemini, in-memory storage, and mock-first development.
