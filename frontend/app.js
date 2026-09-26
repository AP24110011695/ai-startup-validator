/* AI Startup Validator — vanilla ES6, no build step.
   Views: form → progress (SSE) → report. All rendering uses textContent (no HTML
   injection), since agent output is model-generated text. */
"use strict";

const AGENTS = [
  { id: "researcher", name: "1 · Researcher", blurb: "Searching the web for competitors and similar products" },
  { id: "analyst", name: "2 · Market Analyst", blurb: "Sizing the market, trends, and target audience" },
  { id: "critic", name: "3 · Critic", blurb: "Stress-testing the idea: risks, weak assumptions, failure modes" },
  { id: "evaluator", name: "4 · Evaluator", blurb: "Scoring feasibility and writing the verdict" },
];

const $ = (id) => document.getElementById(id);
const views = { form: $("view-form"), progress: $("view-progress"), report: $("view-report") };

function setView(name) {
  for (const [key, el] of Object.entries(views)) el.hidden = key !== name;
}

let currentIdea = "";
let stream = null;

$("idea-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const idea = $("idea").value.trim();
  if (!idea) return;
  currentIdea = idea;
  $("form-error").hidden = true;
  startRun();
});

async function startRun() {
  setView("progress");
  $("progress-idea").textContent = currentIdea;
  resetProgress();
  let resp;
  try {
    resp = await fetch("/api/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idea: currentIdea, use_live: $("use-live").checked }),
    });
  } catch {
    return showFormError("Could not reach the server. Is it running?");
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    return showFormError(body.detail || "The request failed — please try again.");
  }
  const { run_id } = await resp.json();
  listen(run_id);
}

function showFormError(message) {
  const box = $("form-error");
  box.textContent = message;
  box.hidden = false;
  setView("form");
}

function resetProgress() {
  $("quota-box").hidden = true;
  $("progress-error").hidden = true;
  $("start-over").hidden = true;
  const list = $("agent-list");
  list.textContent = "";
  for (const a of AGENTS) {
    const li = document.createElement("li");
    li.className = "agent queued";
    li.id = `agent-${a.id}`;
    const dot = document.createElement("span");
    dot.className = "agent-dot";
    const text = document.createElement("div");
    const name = document.createElement("div");
    name.className = "agent-name";
    name.textContent = a.name;
    const blurb = document.createElement("div");
    blurb.className = "agent-blurb";
    blurb.textContent = a.blurb;
    text.append(name, blurb);
    const state = document.createElement("span");
    state.className = "agent-state";
    state.textContent = "queued";
    li.append(dot, text, state);
    list.append(li);
  }
}

function listen(runId) {
  if (stream) stream.close();
  const es = new EventSource(`/api/runs/${runId}/events`);
  stream = es;
  es.addEventListener("agent_status", (e) => {
    const { agent, status } = JSON.parse(e.data);
    const row = $(`agent-${agent}`);
    if (!row) return;
    row.classList.remove("queued", "working", "done", "failed");
    row.classList.add(status === "started" ? "working" : status === "failed" ? "failed" : "done");
    row.querySelector(".agent-state").textContent =
      status === "started" ? "working…" : status === "failed" ? "failed" : "done";
  });
  es.addEventListener("report", (e) => {
    es.close();
    renderReport(JSON.parse(e.data));
  });
  es.addEventListener("run_error", (e) => {
    es.close();
    const err = JSON.parse(e.data);
    if (err.code === "quota_exceeded") {
      $("quota-box").hidden = false; // paste-a-new-key flow
    } else {
      const box = $("progress-error");
      box.textContent = err.message || "Something went wrong.";
      box.hidden = false;
    }
    $("start-over").hidden = false;
  });
}

$("key-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const key = $("new-key").value.trim();
  if (!key) return;
  $("key-error").hidden = true;
  const resp = await fetch("/api/key", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: key }),
  });
  if (!resp.ok) {
    const box = $("key-error");
    box.textContent = "Could not save the key — please try again.";
    box.hidden = false;
    return;
  }
  $("new-key").value = "";
  startRun(); // key is live server-side; immediately retry the same idea
});

$("start-over").addEventListener("click", () => setView("form"));
$("new-report").addEventListener("click", () => setView("form"));

function renderReport(report) {
  const { score, verdict } = report.evaluation;
  $("score").textContent = score;
  const tone = score >= 75 ? "good" : score >= 50 ? "warn" : "bad";
  const chip = $("verdict");
  chip.textContent = verdict;
  chip.className = `verdict-chip ${tone}`;
  $("mock-badge").hidden = !report.mock_mode;
  $("report-idea").textContent = report.idea;

  const warn = $("warnings");
  warn.textContent = "";
  for (const w of report.warnings || []) {
    const p = document.createElement("p");
    p.className = "warning";
    p.textContent = w;
    warn.append(p);
  }
  warn.hidden = !(report.warnings || []).length;

  $("summary").textContent = report.evaluation.executive_summary || "—";
  $("recommendation").textContent = report.evaluation.recommendation || "—";
  fillList("next-steps", report.evaluation.next_steps);

  const rv = $("research-verified");
  rv.textContent = report.research.verified
    ? "verified via live web search"
    : "unverified — from model knowledge (live search unavailable)";
  rv.className = `verified-note ${report.research.verified ? "good" : "warn"}`;
  const comp = $("competitors");
  comp.textContent = "";
  for (const c of report.research.competitors || []) {
    const li = document.createElement("li");
    if (c.url) {
      const link = document.createElement("a");
      link.href = c.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = c.name;
      li.append(link);
    } else {
      li.append(c.name);
    }
    if (c.similarity) {
      const sim = document.createElement("span");
      sim.className = "similarity";
      sim.textContent = c.similarity;
      li.append(sim);
    }
    if (c.description) {
      const desc = document.createElement("p");
      desc.textContent = c.description;
      li.append(desc);
    }
    comp.append(li);
  }
  if (!comp.children.length) fillList("competitors", ["No competitors found."]);

  const ms = $("market-size");
  ms.textContent = "";
  for (const m of report.market.market_size || []) {
    const li = document.createElement("li");
    const bits = [m.text];
    if (m.basis) bits.push(m.basis);
    if (m.confidence) bits.push(`${m.confidence} confidence`);
    li.textContent = bits.join(" — ");
    ms.append(li);
  }
  if (!ms.children.length) fillList("market-size", ["—"]);
  fillList("trends", report.market.trends);
  fillList("audience", report.market.target_audience);

  const risks = $("risks");
  risks.textContent = "";
  for (const r of report.critique.risks || []) {
    const li = document.createElement("li");
    const sev = document.createElement("span");
    sev.className = `severity ${r.severity === "high" ? "bad" : r.severity === "medium" ? "warn" : "low"}`;
    sev.textContent = r.severity;
    li.append(sev);
    if (r.category) {
      const cat = document.createElement("span");
      cat.className = "category";
      cat.textContent = r.category;
      li.append(cat);
    }
    li.append(` ${r.risk}`);
    risks.append(li);
  }
  if (!risks.children.length) fillList("risks", ["No risks returned."]);
  fillList("assumptions", report.critique.weak_assumptions);
  fillList("failure-modes", report.critique.failure_modes);
  $("hardest-question").textContent = report.critique.hardest_question
    ? `Hardest question: ${report.critique.hardest_question}`
    : "";

  setView("report");
}

function fillList(id, items) {
  const ul = $(id);
  ul.textContent = "";
  if (!items || !items.length) items = ["—"];
  for (const it of items) {
    const li = document.createElement("li");
    li.textContent = it;
    ul.append(li);
  }
}
