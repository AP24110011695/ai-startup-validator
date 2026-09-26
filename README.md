# AI Startup Validator

Submit a business idea; four AI agents (Researcher → Market Analyst → Critic → Evaluator) analyze it on a LangGraph pipeline and return a scored feasibility report (0–100 + verdict).

- **Stack:** Python · FastAPI · LangGraph · Gemini · Tavily · vanilla HTML/CSS/JS
- **Status:** Phase 1 of 10 complete — project skeleton only. Roadmap: [PLAN.md](PLAN.md) · Rules: [IMPLEMENTATION.md](IMPLEMENTATION.md) · Progress: [PROGRESS.md](PROGRESS.md)

## Scoring rubric (how the 0–100 score works)

The Evaluator agent scores five dimensions 0–100; the final score is their weighted sum, and the verdict comes from fixed bands:

| Dimension | Weight |
|---|---|
| Market opportunity | 25% |
| Differentiation / moat | 20% |
| Feasibility & execution | 20% |
| Business viability / monetization | 20% |
| Timing / trend fit | 15% |

Verdict bands: **≥75 Promising** · **50–74 Needs Rework** · **<50 High Risk**. The weighted total and verdict are computed in code, not by the LLM, so the headline number can't be skewed by model arithmetic.

## Setup (full instructions arrive in Phase 10)

```bash
python -m venv .venv
source .venv/Scripts/activate    # Git Bash on Windows (cmd: .venv\Scripts\activate.bat)
pip install -r requirements.txt
cp .env.example .env             # keys optional while USE_MOCK=true
uvicorn backend.main:app --reload
```

Then open http://127.0.0.1:8000 — health check at `/health`.
