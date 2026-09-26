# IMPLEMENTATION.md — Rules for the Coding Agent

These rules apply to every phase of PLAN.md and override convenience. They are hard constraints unless explicitly marked otherwise.

## 1. Coding Standards

- Python 3.11+. PEP 8, type hints on all public functions, f-strings, `pathlib` for paths.
- Fixed folder structure (see PLAN.md "Target Repo Structure"); new files belong where the tree says, not wherever is convenient at the moment.
- Naming: `snake_case` for Python; env vars `UPPER_SNAKE`; agent node functions end in `_node`; mock functions are prefixed `mock_`.
- Pydantic models in `schemas.py` are the only place I/O shapes are defined — agents never hand-roll ad-hoc response dicts.
- Frontend: vanilla ES6, semantic HTML, one CSS file with `:root` custom properties as design tokens. No frameworks, no build step, no runtime CDN dependencies.
- Comments state constraints and *why*, never narrate *what*.
- **No bloat:** prefer the smallest clean solution. No abstraction layers "for later", no config for things with one sensible value, no features beyond the spec. A helper file earns its existence only when it has two real callers.
- Git: `git init` in Phase 1; one commit per completed phase (`phase-N: <summary>`); never commit `.env` or `logs/`.

## 2. Error Handling & Self-Fixing Rules

- **Every** LLM call is wrapped in try/except. On failure, retry up to **2 times** (3 attempts total) with an adjusted prompt — e.g., append "Respond ONLY with valid JSON matching this schema: …", lower temperature. If the last attempt fails, return a **degraded-but-valid** output (schema with empty/neutral fields), record the error in `state.errors`, and let the pipeline continue. The graph must never crash because one agent failed.
- **Web search failure:** fall back to the LLM's own knowledge, set `verified=false` on the findings, add `"research_unverified"` to `state.data_flags`, and surface an "unverified" badge in the report/UI. Never silently present LLM-memory "research" as verified web data.
- Every LLM/search call has an **explicit timeout**; a timeout is a normal error-path failure (retry → degrade), not a crash.
- Log everything to `logs/app.log` via the `logging` module (timestamp, level, agent, error, stack trace for exceptions). No stray `print()` debugging left in committed code.
- **Self-fix rule:** if a bug appears while implementing a phase — reproduce → diagnose → fix → re-test before moving on. Ask the user a question **only if truly blocked** (missing API key, genuinely ambiguous requirement). Note notable fixes in PROGRESS.md known issues.
- User-facing errors are structured codes (`quota_exceeded`, `llm_timeout`, `invalid_input`, `search_unavailable`), never raw tracebacks.

## 3. State Management Rule (hard)

- The LangGraph state is the single source of truth. Nodes return partial updates; the graph merges them.
- **Append/merge only:** no node may delete or overwrite another agent's output. Append-only lists: `state.errors`, `state.progress`, `state.data_flags` (use `Annotated[list, operator.add]` reducers).
- Every node must tolerate missing upstream fields (degraded inputs): check before use, never assume.
- Tests must assert state preservation (e.g., after `evaluate_node` runs, `research` is still intact).

## 4. UI Rule (hard constraint — no AI slop)

- **Forbidden:** purple/gradient hero imagery, robot/astronaut/brain illustrations, glassmorphism, generic chat-bubble layouts, emoji-decorated headings, dark-purple "AI startup" aesthetics.
- **Required:** one minimal palette — near-white background, ink/slate text, **one** accent color; green/amber/red reserved exclusively for verdict/status semantics; system font stack; generous whitespace; clear typographic hierarchy; report as clean cards/sections with a prominent score badge.
- The loading state must show exactly **which agent is currently working** (4 named rows with individual status), not a generic spinner.
- Simple > flashy. Subtle transitions only. Everything readable, fast, usable on desktop and mobile widths.

## 5. Phase Execution Protocol

When the user says "read PLAN.md and IMPLEMENTATION.md and execute Phase N":

1. Read both files fully.
2. Read PROGRESS.md (if it exists) — completed phases, assumptions, known issues.
3. Implement **only** that phase's tasks. No phase-hopping, no drive-by refactors of earlier phases.
4. Test the phase against its acceptance criteria in PLAN.md; self-fix until green.
5. Update PROGRESS.md: mark Phase N done + short summary of what was built + assumptions made + known issues.
6. **Stop.** Do not start the next phase unless explicitly told.

- **Assumptions:** never ask the user anything that can reasonably be inferred or defaulted. Make a sensible decision, record it in PROGRESS.md, move on. (Only sanctioned interruption: the Phase 8 API-key pause.)
- **PROGRESS.md format:** one entry per phase — status (done / in progress), what was built, assumptions, known issues. Created after Phase 1, updated after every phase.

## 6. Mock Mode (Phases 1–7)

- `USE_MOCK=true` (the default) routes every LLM call through `mock_llm()` and every search through `mock_search()` — realistic, hardcoded sample JSON per agent, clearly marked MOCK_MODE.
- Orchestration, state passing, retries, SSE streaming, and the UI must all be **proven against mocks** before any real key exists. Switching later is `USE_MOCK=false` + keys in `.env` — a one-line operational change.
- Mock outputs carry `data_source: "mock"` and the UI shows a visible "MOCK DATA" badge, so mock results can never masquerade as real analysis.

## 7. Real-API Pause Point (≈ Phase 8)

- The only sanctioned stop-and-ask: when a real key is genuinely required (end of Phase 8). Request exactly: **`GEMINI_API_KEY`** (required — the plan assumes Gemini; if you'd rather use OpenAI/Anthropic/Groq, say so at that point, the swap is one file), **`TAVILY_API_KEY`** (recommended, free tier), **`SERPAPI_API_KEY`** (optional fallback).
- After the key arrives: wire it in, test, fix everything that surfaces, and continue through Phases 9–10 and LEARN.md **autonomously** — no further user input.

## 8. API Quota / Rate-Limit Handling (Phase 8 onward — user-facing)

- Detect quota-class failures **specifically**: HTTP 429, Gemini `RESOURCE_EXHAUSTED`, "quota exceeded" / "insufficient credits" messages — distinguished from generic errors.
- On detection: stream a structured `quota_exceeded` event; the UI shows a plain message ("Your API key limit has been reached. Paste a new API key to continue.") with an input field + button. **No terminal, no `.env` editing, no restart.**
- Submitting the new key calls `POST /api/key`, which swaps the key in memory (and persists to `.env`), then the frontend immediately retries the run.
- Never render stack traces or provider error dumps in the UI.

## 9. Self-Fix Commitment (Phases 1–7)

- Mocks mean every bug is reproducible and fixable without the user. No phase may be marked done in PROGRESS.md until its acceptance criteria **demonstrably pass** — tests actually run and pass, not assumed.

## 10. Final Deliverable — LEARN.md (after Phase 10, real API verified)

Create `LEARN.md` as an interview-prep guide containing:

1. A plain-English summary of what the project does and why it's useful.
2. The multi-agent architecture: how LangGraph orchestrates the 4 agents (shared state, nodes, edges, conditional routing).
3. Key concepts to understand and explain: agent state, tool calling, per-agent prompt/persona design, the scoring rubric logic, error handling / retry logic, mock-vs-real API pattern, SSE streaming.
4. Likely interview questions about this project with short model answers.
5. "Why did you make this choice?" justifications: why LangGraph, why these 4 agents, why FastAPI + a vanilla frontend, why Gemini, why in-memory storage for v1.
