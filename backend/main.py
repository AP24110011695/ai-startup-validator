"""FastAPI app: health, static frontend, and the validation API (Phase 8).

POST /api/validate starts a background graph run and returns {run_id};
GET /api/runs/{id}/events streams SSE (agent_status events, then a report or
error event); GET /api/runs/{id} re-fetches a finished run; POST /api/key
hot-swaps the Gemini key with no restart. Runs are kept in memory (no DB for v1).
"""
import json
import logging
import os
import threading
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import agents, config
from backend.agents import now_iso
from backend.config import ROOT, USE_MOCK
from backend.graph import GRAPH
from backend.llm import QuotaError
from backend.logging_setup import setup_logging
from backend.schemas import Report

setup_logging()
logger = logging.getLogger(__name__)
logger.info("startup: mock_mode=%s, llm_model=%s", USE_MOCK, config.LLM_MODEL)

app = FastAPI(title="AI Startup Validator")

RUNS: dict[str, dict] = {}
STREAM_POLL_SECONDS = 0.2
STREAM_MAX_SECONDS = 600  # real runs with rate-limit backoffs can take a few minutes


class ValidateRequest(BaseModel):
    idea: str
    # Per-run mode from the UI toggle: True = live pipeline, False = mock,
    # absent = use the server-level USE_MOCK default.
    use_live: bool | None = None


class KeyRequest(BaseModel):
    api_key: str


@app.get("/health")
def health() -> dict:
    # version = Render's deployed commit hash (RENDER_GIT_COMMIT), so the live
    # site's /health always answers "which code is deployed?".
    return {
        "status": "ok",
        "mock_mode": USE_MOCK,
        "version": os.getenv("RENDER_GIT_COMMIT", "local"),
    }


@app.post("/api/validate")
def start_validation(req: ValidateRequest) -> dict:
    idea = req.idea.strip()
    if not idea:
        raise HTTPException(status_code=422, detail="idea is required")
    run_id = uuid4().hex[:12]
    RUNS[run_id] = {
        "run_id": run_id, "idea": idea, "status": "running",
        "events": [], "report": None, "error": None, "done": threading.Event(),
    }
    # Toggle ON -> live (mock=False); OFF -> mock; absent -> None (env default).
    mock_override = None if req.use_live is None else not req.use_live
    threading.Thread(target=_execute_run, args=(run_id, idea, mock_override), daemon=True, name=f"run-{run_id}").start()
    return {"run_id": run_id}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown run")
    return {"run_id": run_id, "status": run["status"], "report": run["report"], "error": run["error"]}


@app.get("/api/runs/{run_id}/events")
def stream_events(run_id: str) -> StreamingResponse:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown run")
    return StreamingResponse(
        _sse(run),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/key")
def update_key(req: KeyRequest) -> dict:
    api_key = req.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=422, detail="api_key is required")
    config.set_api_key("GEMINI_API_KEY", api_key)
    logger.info("GEMINI_API_KEY hot-swapped via /api/key")
    return {"ok": True}


def _execute_run(run_id: str, idea: str, mock_override: bool | None) -> None:
    """Thread body: stream the graph, pushing SSE events as agents complete.
    agent_status events arrive in real time via the progress sink (a node's
    "started" pushes the moment it begins); the state replay dedupes against them.
    The mode override is bound to this run's thread context so concurrent runs
    with different toggle states stay independent.
    """
    run = RUNS[run_id]
    seen: set[str] = set()

    def emit(event: dict) -> None:
        key = json.dumps(event, sort_keys=True)
        if key in seen:
            return
        seen.add(key)
        _push(run, "agent_status", event)

    mode_token = config.mock_override.set(mock_override)
    try:
        state: dict = {}
        progress_token = agents.progress_sink.set(emit)
        try:
            for snapshot in GRAPH.stream({"idea": idea, "run_id": run_id, "created_at": now_iso()}, stream_mode="values"):
                state = snapshot
                for event in state.get("progress", []):
                    emit(event)
        finally:
            agents.progress_sink.reset(progress_token)
        if state.get("input_rejected"):
            detail = next((e for e in state.get("errors", []) if e.get("type") == "invalid_input"), {})
            _fail(run, "invalid_input", detail.get("message", "Please describe your idea in more detail."))
            return
        report = _build_report(idea, state)
        run["report"] = report
        _push(run, "report", report)
        run["status"] = "done"
    except QuotaError as exc:
        _fail(run, "quota_exceeded", str(exc))
    except Exception as exc:
        logger.exception("run %s failed", run_id)
        _fail(run, "llm_error", str(exc))
    finally:
        config.mock_override.reset(mode_token)
        run["done"].set()


def _build_report(idea: str, state: dict) -> dict:
    """Assemble the UI-facing report from the final graph state; degraded paths
    (mock data, unverified research, failed agents) surface as warnings."""
    run_is_mock = config.use_mock()
    warnings = []
    if run_is_mock:
        warnings.append("MOCK MODE: generated from canned sample data, not real analysis.")
    flags = state.get("data_flags", [])
    if "research_unverified" in flags:
        warnings.append("Competitor research is unverified — live search was unavailable, so it comes from model knowledge.")
    if "market_unverified" in flags:
        warnings.append("Market analysis lacks live data.")
    warnings += [f"{e['agent']} agent failed: {e['message'][:120]}" for e in state.get("errors", []) if e.get("type") == "llm_error"]
    report = Report(
        idea=idea, generated_at=now_iso(), mock_mode=run_is_mock,
        research=state.get("research") or {},
        market=state.get("market") or {},
        critique=state.get("critique") or {},
        evaluation=state.get("evaluation") or {},
        warnings=warnings,
    )
    return report.model_dump()


def _fail(run: dict, code: str, message: str) -> None:
    # "run_error" rather than "error": a server event named "error" would collide
    # with EventSource's built-in connection-error event in the browser.
    run["error"] = {"code": code, "message": message}
    _push(run, "run_error", run["error"])
    run["status"] = "error"


def _push(run: dict, event_type: str, data) -> None:
    run["events"].append({"event": event_type, "data": data})


def _sse(run: dict):
    """Replay buffered events from the start, then stream live until the run ends."""
    index = 0
    deadline = time.time() + STREAM_MAX_SECONDS
    while True:
        while index < len(run["events"]):
            event = run["events"][index]
            index += 1
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
        if run["done"].is_set() or time.time() > deadline:
            return
        time.sleep(STREAM_POLL_SECONDS)


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
