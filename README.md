# AI Startup Validator

Submit a business idea; four AI agents (Researcher → Market Analyst → Critic → Evaluator) analyze it on a LangGraph pipeline and return a scored feasibility report (0–100 + verdict).

- **Stack:** Python · FastAPI · LangGraph · Gemini · Tavily · vanilla HTML/CSS/JS
- **Status:** Phase 1 of 10 complete — project skeleton only. Roadmap: [PLAN.md](PLAN.md) · Rules: [IMPLEMENTATION.md](IMPLEMENTATION.md) · Progress: [PROGRESS.md](PROGRESS.md)

## Setup (full instructions arrive in Phase 10)

```bash
python -m venv .venv
source .venv/Scripts/activate    # Git Bash on Windows (cmd: .venv\Scripts\activate.bat)
pip install -r requirements.txt
cp .env.example .env             # keys optional while USE_MOCK=true
uvicorn backend.main:app --reload
```

Then open http://127.0.0.1:8000 — health check at `/health`.
