# LEARN.md — Explain This Project in Interviews

A study guide for talking about the AI Startup Validator: what it is, how it works, the concepts you must be able to explain cold, likely questions with model answers, and the justifications for every major choice.

---

## 1. What it does and why it's useful (plain English)

**The problem:** first-time founders fall in love with ideas and build them without checking whether the market exists, who the competitors are, or what could kill the project. Real validation means market research, competitive analysis, and honest risk assessment — things beginners skip because they're slow, expensive, or uncomfortable.

**The project:** a web app where you paste a business idea and four specialized AI agents analyze it in sequence — one researches real competitors on the live web, one sizes the market and audience, one plays devil's advocate, and one compiles everything into a feasibility score from 0–100 with a verdict (Promising / Needs Rework / High Risk) and concrete next steps. What used to take a weekend of manual research (or a consultant) happens in about a minute, with sources and risks shown honestly — including a visible "unverified" flag whenever the system had to fall back on model knowledge instead of live search.

**The deeper point (say this in interviews):** the interesting engineering isn't the LLM prompts — it's the *system around them*: orchestration with shared state, structured JSON outputs validated by schemas, retry/degrade logic so one failing agent never kills the run, and quota handling that lets the user recover with zero technical effort.

## 2. The multi-agent architecture and how LangGraph orchestrates it

**Four agents, one shared state, one directed graph:**

```
START → validate_idea ──(invalid: too short/vague)──► END ("need more detail")
           │ valid
           ▼
        research ──► analyze_market ──► critique ──► evaluate ──► END (report)
```

- Each agent is a **node** — a plain Python function that receives the shared state and returns a *partial update* (e.g., only its own output key plus appended progress events).
- **Shared state** is a single `TypedDict` (`ValidatorState`) that flows through the graph: `idea` in; `research`, `market`, `critique`, `evaluation` out — each written by exactly one owner node; `progress`, `errors`, and `data_flags` are append-only lists.
- **LangGraph's role:** it compiles the graph once, executes nodes in edge order, merges each node's partial updates into the state, and supports conditional edges (`validate_idea` routes garbage input straight to END) and reducers.
- **Append-only via reducers:** the progress/error lists use `Annotated[list, operator.add]`, so LangGraph *concatenates* a node's returned items onto the existing list instead of overwriting — no node can destroy another agent's data. Tests assert state preservation after every node.
- **Why sequential, not parallel:** the analyst consumes the researcher's findings and the critic consumes both — the data dependency IS the design. (The graph could fan out later; the state schema wouldn't change.)
- **From graph to UI:** the FastAPI layer runs the compiled graph in a background thread, streams `graph.stream(...)` state snapshots, and pushes per-agent SSE events to the browser so the user sees "Researcher: working…" in real time, then the final report.

## 3. Key concepts you must be able to explain

**Agent state.** One dict is the single source of truth for a run. Ownership is explicit: each output key has exactly one writer node; everything else treats it read-only. Append-only channels (progress/errors/flags) record everything that happened, including failures — the report's warning banners are generated from them. *Why it matters:* multi-agent systems fail when agents clobber each other or when failures vanish silently; explicit ownership + append-only logs solve both.

**Tool calling / grounding.** The Researcher is "grounded": it builds 2–4 targeted queries from the idea, calls the search tool (Tavily REST, SerpAPI fallback), and the LLM only *extracts and dedupes* real results into a schema — it never invents competitors when search data is present. If all search fails, it falls back to model knowledge with `verified=false`, and the UI shows an "unverified" badge. Grounded-LLM-with-fallback is the pattern; the key rule is *the system knows and shows when it's not grounded*.

**Prompt design per agent.** Each agent has a persona + a task + an output contract: "You are a skeptical senior VC… respond ONLY with valid JSON matching: {risks: [{risk, severity: high|medium|low, category}…]}". The severity rubric is defined in the prompt (high = likely fatal if true); the scoring weights are in the evaluator prompt AND as code constants. Prompts live in one module (`prompts.py`) as data, not buried in code.

**Structured output.** Every agent's response is validated against a pydantic model; validation failure counts as a failure and triggers a retry with the JSON schema appended to the prompt. The frontend renders only schema-shaped data and uses `textContent` everywhere (no HTML injection from model output).

**The scoring rubric logic.** Five dimensions (opportunity 25, differentiation 20, feasibility 20, viability 20, timing 15), each scored 0–100 by the LLM; the *weighted total and verdict band are recomputed in Python*, so model arithmetic errors can't skew the headline number. A test feeds the evaluator a fake "score: 99, all-zero subscores" and asserts the code corrects it to 0/High Risk.

**Error handling and retries.** Layered: (1) `call_llm` retries up to 2 extra times with an adjusted prompt — short backoff for generic errors, 15–30s backoff for 429 rate limits; (2) after that, a rate-limit failure converts to a fatal `QuotaError`, while other failures convert to a *degraded but schema-valid output* plus an `errors` entry — the graph literally never aborts because one agent failed; (3) the API layer maps `QuotaError` to a `quota_exceeded` SSE event; (4) the UI shows a paste-a-new-key card, `POST /api/key` swaps the key in memory and persists it to `.env`, and the run retries instantly. Every layer was tested by *forcing* failures in mocks.

**Mock-vs-real API pattern.** One env var (`USE_MOCK=true`) routes every LLM call to canned per-agent builders and every search to canned results, behind the *same function signatures* the real providers use. The whole system — graph, retries, SSE, UI, quota flow — was built and tested against mocks with zero API keys; going live was one `.env` change. Mock outputs are visibly labeled (MOCK DATA badge) so fake results can never masquerade as real ones.

**SSE streaming.** Server-Sent Events over a plain GET: the server replays buffered events for late subscribers, then streams live per-agent status and the final report. Chosen over WebSockets because the traffic is one-directional. A server event named `error` would collide with the browser's built-in EventSource connection-error event, so the app's event is named `run_error`.

**Real-world war stories (great interview material):** the API returned a 404 because `gemini-2.5-flash` was "no longer available to new users" — the model id became config, not a constant; a live run recovered from two 503 "high demand" spikes via backoff; a real 429 quota abort surfaced the key-swap UI exactly as designed.

## 4. Likely interview questions (with short model answers)

**Q: Why use a graph orchestrator instead of just four function calls?**
A: A graph gives me shared typed state with defined merge semantics, conditional edges (input validation routes to END), a place to hang cross-cutting concerns (progress events, retries), and a structure that survives change — adding a parallel branch or a human-approval loop is a graph edit, not a rewrite. Sequential calls also can't express routing ("too vague → skip everything") cleanly.

**Q: Why these four agents? Couldn't one prompt do it?**
A: One prompt doing research + analysis + criticism + scoring produces mush: each role needs a different persona, different inputs, and a different output schema. Splitting them gives each model call a narrow job, lets the critic see the other agents' outputs (so risks cite actual findings), and makes each stage independently testable and independently degradable. It also mirrors how a real investment committee works.

**Q: How do you trust LLM output?**
A: Three layers: schema validation (pydantic rejects malformed JSON, triggering a retry), deterministic post-processing (the score/verdict and the verified flags are computed in code, not taken from the model), and provenance surfacing (unverified data is flagged in the state and shown in the UI).

**Q: What happens when an agent fails mid-run?**
A: The node wrapper catches it after the LLM-level retries and substitutes a degraded-but-valid output plus an errors entry, so the pipeline continues and the report shows a warning. Quota-class failures are the exception: they abort the run deliberately and surface the key-recovery UI, because a report built entirely on a dead key is worthless.

**Q: How does the user recover from an exhausted API key?**
A: The run aborts with a structured `quota_exceeded` event; the UI shows a card with a key input; submitting calls `POST /api/key`, which swaps the key in an in-memory dict every module reads from and appends it to `.env`; the frontend immediately re-runs the idea. No restart, no terminal, no .env editing.

**Q: How do you test an LLM application?**
A: Separate determinism from the model. The orchestration, state merging, retries, streaming, and UI are all tested against mock LLM/search functions with forced failures (garbage JSON, timeouts, 429s) — 37 deterministic tests. Real-model behavior is verified in live end-to-end runs, not in the suite.

**Q: Why SSE instead of WebSockets or polling?**
A: Progress is one-way server→client; SSE is a plain GET, auto-reconnects, needs no protocol negotiation, and the server can replay buffered events for late subscribers — which also makes it trivially resumable. Polling would be chatty; WebSockets would be bidirectional machinery I don't need.

**Q: How would you scale it?**
A: Swap the in-memory run store for Redis, move runs to a task queue (Celery/ARQ) with the SSE endpoint reading events from it, and stream from the database instead of thread buffers. The graph and agents don't change — that's the payoff of isolating orchestration from transport.

**Q: What's the weakest part today?**
A: The input validator is a heuristic (length/letters), so semantically vague ideas flow through and get generic feedback; an LLM-based pre-check or clarifying-question loop would fix it. Also the in-memory store means runs vanish on restart, and prompt-injection resistance in search snippets deserves hardening.

## 5. Why-did-you-make-this-choice justifications

**Why LangGraph?** I needed: shared state with controlled merging (append-only reducers for logs, single-writer keys for outputs), conditional edges, and a library whose abstraction *is* the agent pipeline — so retries, progress hooks, and routing live in one place. Hand-rolled function calls would bury those in ad-hoc code; heavier frameworks would hide the state flow I explicitly wanted to teach, test, and show.

**Why four agents, in this order?** Research → Analysis → Critique → Evaluation mirrors real diligence and creates a data funnel: each agent narrows and sharpens the previous output, and the evaluator gets three independent lenses. The critic deliberately comes *after* analysis so its risks are grounded in evidence, not vibes.

**Why FastAPI?** Native async/SSE streaming, pydantic everywhere (my I/O schemas and the LLM JSON schemas are the same models), automatic OpenAPI docs, and a dependency graph that fits a single small backend.

**Why a vanilla JS frontend instead of React?** The UI is one page with three views; the API contract (SSE + JSON) is the real interface. Vanilla means no Node toolchain, no build step, instant deploys, and a codebase a backend interviewer can read top to bottom. The API contract keeps a React rewrite cheap if the app grows.

**Why Gemini?** Free-tier access with native JSON/response-schema mode made structured output reliable without prompt-hacking. The LLM is hidden behind one function (`call_llm`), so switching to OpenAI/Anthropic is one file — which is the actual design point: provider is a detail, not an architecture.

**Why in-memory storage?** It's a v1 validation tool: runs are short-lived, there's no multi-user requirement, and a DB would add a dependency without adding user value yet. The run store is a dict behind one module, so Redis/Postgres is a contained swap.

**Why mock-first development?** It removed the API key from the critical path: every behavior — including failure behaviors — was provable before any key existed, and it stays the cheapest regression harness. The seam (one function signature) is the same seam I'd use to swap providers.
