# AI Startup Validator

Submit a business idea; four AI agents analyze it on a LangGraph pipeline and return a scored feasibility report (0–100 + verdict).

1. **Researcher** — searches the web (Tavily → SerpAPI fallback) for competitors and similar products; if all search fails, it answers from model knowledge and the report is flagged **unverified**.
2. **Market Analyst** — sizes the market (TAM-style estimates with confidence), trends, and target audience, consuming the researcher's output; runs its own targeted searches if the research is thin.
3. **Critic** — a devil's-advocate pass: risks with severity, weak assumptions, failure modes, and the one hardest question.
4. **Evaluator** — scores five dimensions (Market opportunity 25% · Differentiation 20% · Feasibility 20% · Business viability 20% · Timing 15%) into a 0–100 score with a verdict: **≥75 Promising · 50–74 Needs Rework · <50 High Risk**. The weighted total and verdict are computed in code, not by the LLM.

- **Stack:** Python 3.12 · FastAPI · LangGraph · Gemini (`gemini-3.8-flash`) · Tavily · vanilla HTML/CSS/JS (no build step)
- **Status:** Phase 10 of 10 complete. Roadmap: [PLAN.md](PLAN.md) · Rules: [IMPLEMENTATION.md](IMPLEMENTATION.md) · Progress: [PROGRESS.md](PROGRESS.md)

## How the scoring rubric works

Each dimension is scored 0–100 by the LLM; the final score is their weighted sum, and the verdict comes from fixed bands. The weighted total and verdict are computed in code (`backend/agents.py` from `backend/prompts.RUBRIC_WEIGHTS`), so the headline number can't be skewed by model arithmetic.

## Reliability model (self-healing)

- Every LLM call is retried up to 2 times with an adjusted "respond only with JSON" prompt; generic failures back off 0.5s/1s, rate limits back off 15s/30s.
- A persistent rate limit (429) or an exhausted key aborts the run with a structured `quota_exceeded` event → the UI shows a "paste a new API key" card → `POST /api/key` swaps the key in memory and persists it to `.env` → the run retries immediately. No restart, no terminal.
- Any other agent failure degrades to a valid-but-empty output plus a visible warning; the pipeline never dies because one agent failed.
- Web-search failure falls back to model knowledge flagged `research_unverified` (banner in the report).

## Run it locally

```bash
python -m venv .venv
source .venv/Scripts/activate    # Git Bash on Windows (cmd: .venv\Scripts\activate.bat; mac/linux: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env             # fill in GEMINI_API_KEY (required), TAVILY_API_KEY (recommended)
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000 · health check at `/health` · interactive API docs at `/docs`.

**Mock mode:** set `USE_MOCK=true` in `.env` to run the entire pipeline on canned data with no API keys — useful for demos and UI work. The UI shows a visible "MOCK DATA" badge. Set `FAKE_QUOTA_ERROR=1` to simulate an exhausted key and test the key-swap flow.

## Run the tests

```bash
pytest -q        # 37 tests; the suite always runs in mock mode (conftest.py forces it)
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/validate` `{idea}` | Starts a run; returns `{run_id}` immediately. |
| `GET /api/runs/{id}/events` | SSE stream: `agent_status` events per agent, then `report` or `run_error` `{code, message}`. |
| `GET /api/runs/{id}` | Re-fetch a run's status/report. |
| `POST /api/key` `{api_key}` | Hot-swap the Gemini key (memory + `.env`), no restart. |
| `GET /health` | `{status, mock_mode}`. |

## Architecture

```
POST /api/validate ──► background thread ──► LangGraph StateGraph (compiled once)
                                             START → validate_idea ─┬─(invalid)─► END: "need more detail"
                                                                     └─(valid)→ research → analyze_market
                                                                                → critique → evaluate → END
GET /api/runs/{id}/events ◄─ SSE ◄─ progress events (contextvar sink + state replay, deduped)
```

Shared `ValidatorState` (TypedDict) flows through the graph: `research`, `market`, `critique`, `evaluation` are each written by exactly one node; `progress`, `errors`, `data_flags` are append-only (`Annotated[list, operator.add]` reducers). LLM access is isolated in `backend/llm.py` (mock/real behind one signature); search in `backend/tools.py` (Tavily REST → SerpAPI REST → mock).

## Deploy to Render (free tier)

The app ships as a single Docker container (FastAPI + static frontend). Render's free tier needs **no credit card**.

1. Push this repo to GitHub:
   ```bash
   git remote add origin https://github.com/<you>/ai-startup-validator.git
   git push -u origin main
   ```
2. On [render.com](https://render.com): **New + → Web Service** → connect the GitHub repo.
3. Runtime **Docker** is auto-detected from the `Dockerfile`. Leave the build/start commands empty (the image's `CMD` honors Render's `PORT`).
4. **Environment variables:** `GEMINI_API_KEY` (required), `TAVILY_API_KEY` (recommended), optionally `LLM_MODEL` (default `gemini-3.8-flash`) and `USE_MOCK=false`. Never commit `.env` — keys live in Render's dashboard.
5. **Create Web Service** → first build takes a few minutes; you get an `onrender.com` URL.
6. Expected behavior, not a bug: free web services **spin down after 15 minutes of inactivity** and take **30–60 seconds to wake** on the next request.

Updating: every `git push` to the connected branch redeploys automatically.
