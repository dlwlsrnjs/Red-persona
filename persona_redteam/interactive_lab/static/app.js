const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

let config = null;
let currentCase = null;
const lanes = new Map();
let laneViewMode = "all";
let focusedLaneId = "";

function historyMode() {
  return $("#historyEnabled").checked ? "with_history" : "no_history";
}

function runOptions(protocol) {
  return Object.entries(config.historical_runs || {}).filter(([, run]) =>
    run.protocol === protocol && run.history_modes.includes(historyMode())
  );
}

function populateRunSelect(select, protocol, allowNone = false) {
  const previous = select.value;
  select.replaceChildren();
  if (allowNone) {
    const option = el("option"); option.value = ""; option.textContent = "저장 실행 없음 / 새 실시간 실행";
    select.append(option);
  }
  for (const [runId, run] of runOptions(protocol)) {
    const option = el("option"); option.value = runId;
    const count = run.artifact_counts[historyMode()] || 0;
    option.textContent = `${run.label} · ${count} cases`;
    if (runId === previous) option.selected = true;
    select.append(option);
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options,
  });
  let value;
  try { value = await response.json(); } catch (_) { value = {error: await response.text()}; }
  if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`);
  return value;
}

function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = String(text);
  return node;
}

function jsonBlock(value) {
  const pre = el("pre");
  pre.textContent = JSON.stringify(value, null, 2);
  return pre;
}

function showError(node, error) {
  node.textContent = error instanceof Error ? error.message : String(error);
  node.classList.remove("hidden");
}

function clearError(node) {
  node.textContent = "";
  node.classList.add("hidden");
}

async function loadCases() {
  clearError($("#globalError"));
  const outcome = $("#outcome").value;
  const q = encodeURIComponent($("#caseQuery").value.trim());
  const history = $("#historyEnabled").checked ? "1" : "0";
  const run = encodeURIComponent($("#caseRun").value);
  try {
    const value = await api(`/api/cases?outcome=${outcome}&q=${q}&history=${history}&run=${run}`);
    const select = $("#caseSelect");
    select.replaceChildren();
    for (const row of value.cases) {
      const option = el("option");
      option.value = row.case_id;
      option.textContent = `${row.case_id} · ${row.outcome} · ${row.crisis_label || "unknown"} · ${row.goal_preview || ""}`;
      select.append(option);
    }
    $("#caseCount").textContent = `${value.count} cases`;
  } catch (error) { showError($("#globalError"), error); }
}

async function randomCase() {
  clearError($("#globalError"));
  const outcome = $("#outcome").value;
  const history = $("#historyEnabled").checked ? "1" : "0";
  const run = encodeURIComponent($("#caseRun").value);
  try {
    const row = await api(`/api/cases/random?outcome=${outcome}&history=${history}&run=${run}`);
    if (![...$("#caseSelect").options].some(o => o.value === row.case_id)) await loadCases();
    $("#caseSelect").value = row.case_id;
    await loadCase();
  } catch (error) { showError($("#globalError"), error); }
}

function renderScores(score) {
  const root = $("#scoreSummary");
  root.replaceChildren();
  const badges = el("div", "badges");
  for (const [name, value] of [
    ["R3+", score.r3_plus], ["B4+", score.b4_plus],
    ["HB+", score.harmbench_positive], ["Strict joint", score.strict_joint],
  ]) {
    const badge = el("span", value ? "success" : "failure", `${name}: ${value ? "✓" : "×"}`);
    badges.append(badge);
  }
  root.append(badges);
  const table = el("table");
  const head = el("tr");
  ["Direction", "R", "B", "HB", "Joint", "CARES"].forEach(x => head.append(el("th", "", x)));
  table.append(head);
  for (const row of score.branches || []) {
    const tr = el("tr");
    [row.direction, row.R, row.B, row.harmbench_positive ? "+" : "−", row.joint_success ? "✓" : "×", row.cares_label || "—"]
      .forEach(x => tr.append(el("td", "", x == null ? "—" : x)));
    table.append(tr);
  }
  root.append(table);
}

function renderCase(value) {
  currentCase = value;
  $("#caseInspector").classList.remove("hidden");
  $("#runBuilder").classList.remove("hidden");
  $("#goalText").textContent = value.goal;
  $("#personaText").textContent = value.persona;
  $("#personaMeta").textContent = `${value.persona_id} · ${value.crisis_label} · H${value.harm_level}`;
  const badgeRoot = $("#caseBadges"); badgeRoot.replaceChildren();
  badgeRoot.append(el("span", value.historical_score.status, value.historical_score.status));
  badgeRoot.append(el("span", "", value.case_id));
  badgeRoot.append(el("span", "", value.historical_run_label || value.historical_run));
  badgeRoot.append(el("span", "", $("#historyEnabled").checked ? "history" : "no history"));
  renderScores(value.historical_score);

  const history = $("#historyList"); history.replaceChildren();
  (value.persona_history || []).forEach((turn, index) => {
    const item = el("div", "timeline-item");
    item.append(el("h4", "", `Observation ${index + 1}`));
    item.append(el("p", "", turn.user || ""));
    const state = el("pre"); state.textContent = typeof turn.persona_state === "string" ? turn.persona_state : JSON.stringify(turn.persona_state, null, 2);
    item.append(state); history.append(item);
  });

  const selection = value.persona_selection || {};
  $("#selectionReason").replaceChildren(jsonBlock({selected: selection.selected, fit_quality: selection.fit_quality, attempts: selection.attempts}));
  const candidatesRoot = $("#personaCandidates"); candidatesRoot.replaceChildren();
  const table = el("table");
  const hr = el("tr"); ["Rank", "Persona", "Concerns", "Style", "Retrieval"].forEach(x => hr.append(el("th", "", x))); table.append(hr);
  for (const row of selection.retrieval_top_k || []) {
    const tr = el("tr");
    [row.rank, row.persona_id, JSON.stringify(row.concerns), JSON.stringify(row.communication_style), JSON.stringify(row.retrieval_metadata)]
      .forEach(x => tr.append(el("td", "", x == null ? "" : x)));
    table.append(tr);
  }
  candidatesRoot.append(table);

  const pool = $("#questionPool"); pool.replaceChildren();
  (value.question_pool.candidates || []).forEach((row, index) => {
    const card = el("article", "question-card");
    card.append(el("strong", "", `${index}. ${row.focus}`));
    card.append(el("p", "", `Case A: ${row.similar_case}`));
    card.append(el("p", "", `Case B: ${row.contrast_case}`));
    const pre = el("pre"); pre.textContent = row.research_question; card.append(pre); pool.append(card);
  });
  const audits = el("article", "question-card"); audits.append(el("strong", "", "실제 분기별 선택 감사"));
  audits.append(jsonBlock(value.branches.map(row => ({direction: row.direction, audit: row.recovery_question_audit, anchor: row.anchor})))); pool.append(audits);
  renderPersonaStage();
}

function renderPersonaStage() {
  if (!currentCase) return;
  $("#stagePersonaTitle").textContent = `${currentCase.persona_id || "Persona"} · ${currentCase.case_id}`;
  $("#stagePersonaText").textContent = currentCase.persona || "";
  $("#stageGoalText").textContent = currentCase.goal || "";
  const root = $("#stageHistory"); root.replaceChildren();
  (currentCase.persona_history || []).forEach((turn, index) => {
    const item = el("article", "timeline-item");
    item.append(el("h3", "", `Observation ${index + 1}`));
    item.append(el("p", "", turn.user || ""));
    const state = el("pre");
    state.textContent = typeof turn.persona_state === "string" ? turn.persona_state : JSON.stringify(turn.persona_state, null, 2);
    item.append(state); root.append(item);
  });
}

async function loadCase() {
  clearError($("#globalError"));
  const caseId = $("#caseSelect").value;
  if (!caseId) return;
  const history = $("#historyEnabled").checked ? "1" : "0";
  const run = encodeURIComponent($("#caseRun").value);
  try { renderCase(await api(`/api/cases/${encodeURIComponent(caseId)}?history=${history}&run=${run}`)); }
  catch (error) { showError($("#globalError"), error); }
}

async function searchPersonaPool() {
  const root = $("#poolResults"); root.textContent = "검색 중…";
  try {
    const value = await api(`/api/personas?q=${encodeURIComponent($("#personaQuery").value)}&limit=25`);
    root.replaceChildren();
    const table = el("table");
    const hr = el("tr"); ["Persona", "Background", "Concerns", "Style", "Source"].forEach(x => hr.append(el("th", "", x))); table.append(hr);
    for (const row of value.personas) {
      const tr = el("tr");
      [row.persona_id, row.background, JSON.stringify(row.concerns), JSON.stringify(row.communication_style), row.source]
        .forEach(x => tr.append(el("td", "", x == null ? "" : x)));
      table.append(tr);
    }
    root.append(table);
  } catch (error) { root.textContent = error.message; }
}

function populateSelect(select, rows, selected) {
  select.replaceChildren();
  for (const [value, info] of Object.entries(rows)) {
    const option = el("option"); option.value = value; option.textContent = info.label || value;
    if (value === selected) option.selected = true;
    select.append(option);
  }
}

function pricingFor(provider, model) {
  if (provider !== "openai") return null;
  const key = model.toLowerCase().startsWith("gpt-4o") ? "gpt-4o" : model.toLowerCase();
  return ((config.pricing_estimate || {}).models || {})[key] || null;
}

function estimateCost(summary, provider, model) {
  const price = pricingFor(provider, model);
  if (!price || !summary || !summary.observations) return null;
  const cached = summary.mean_cached_prompt_tokens || 0;
  const uncached = Math.max(0, summary.mean_prompt_tokens - cached);
  return uncached * price.input_per_million / 1e6 +
    cached * price.cached_input_per_million / 1e6 +
    summary.mean_completion_tokens * price.output_per_million / 1e6;
}

function costText(summary, provider, model) {
  if (!summary || !summary.observations) return "과거 기록 없음";
  const usd = estimateCost(summary, provider, model);
  return `${Number(summary.mean_total_tokens).toLocaleString()} tokens` +
    (usd == null ? " · 비용은 provider 요금에 따라 결정" : ` · 약 $${usd.toFixed(4)}`);
}

function renderCostPreview(node, session) {
  const root = $(".cost-preview", node); root.replaceChildren();
  const estimate = (config.usage_estimates || {})[session.historical_run];
  const history = session.history_enabled ? "with_history" : "no_history";
  const values = estimate && estimate.histories && estimate.histories[history];
  const provider = $(".provider", node).value;
  const model = $(".model", node).value.trim();
  for (const [label, key] of [
    ["다음 호출 1회 평균", "per_call"],
    ["샘플 1개 · 현재 분기", "one_sample_one_branch"],
    ["샘플 1개 · 4분기 전체", "one_sample_all_branches"],
  ]) {
    const card = el("div", "cost-item");
    card.append(el("strong", "", label), el("span", "", costText(values && values[key], provider, model)));
    if (values && values[key] && values[key].p95_total_tokens) {
      card.append(el("small", "", `과거 p95 ${Number(values[key].p95_total_tokens).toLocaleString()} tokens`));
    }
    root.append(card);
  }
  const source = (config.pricing_estimate || {}).source;
  const date = (config.pricing_estimate || {}).as_of;
  const note = el("p", "cost-note");
  note.textContent = `저장된 ${estimate ? estimate.label : "동일 조건"} 실제 usage 평균. ` +
    (pricingFor(provider, model) ? `OpenAI 공개 단가(${date})의 추정치이며 실제 청구액은 다를 수 있습니다.` : "달러 비용은 선택한 provider 단가를 확인하세요.");
  if (source && pricingFor(provider, model)) {
    const link = el("a", "", " 단가 출처"); link.href = source; link.target = "_blank"; link.rel = "noreferrer"; note.append(link);
  }
  root.append(note);
}

function confirmCost(node, session) {
  const estimate = (config.usage_estimates || {})[session.historical_run];
  const history = session.history_enabled ? "with_history" : "no_history";
  const summary = estimate && estimate.histories && estimate.histories[history] && estimate.histories[history].per_call;
  const message = costText(summary, $(".provider", node).value, $(".model", node).value.trim());
  return window.confirm(`지금 모델 호출 1회를 시작합니다.\n과거 동일 프로토콜 평균: ${message}\n\n계속 전송할까요?`);
}

async function addLane() {
  clearError($("#globalError"));
  if (!currentCase) return;
  try {
    const session = await api("/api/session", {method: "POST", body: JSON.stringify({
      case_id: currentCase.case_id,
      protocol: $("#protocol").value,
      branch_index: Number($("#branchIndex").value),
      history_enabled: $("#historyEnabled").checked,
      custom_goal: $("#customGoal").value,
      pcsa_strategy: $("#pcsaStrategy").value,
      historical_run: $("#historicalRun").value,
    })});
    createLane(session);
  } catch (error) { showError($("#globalError"), error); }
}

function createLane(session) {
  $("#lanesSection").classList.remove("hidden");
  const node = $("#laneTemplate").content.firstElementChild.cloneNode(true);
  node.dataset.sessionId = session.id;
  const historical = (config.historical_runs || {})[session.historical_run];
  $(".lane-protocol", node).textContent = session.protocol_metadata.fidelity +
    (historical ? ` · 저장 참조: ${historical.label}` : "");
  $(".lane-title", node).textContent = session.protocol_metadata.label;
  $(".lane-summary", node).textContent = session.protocol_metadata.summary;
  $(".lane-state", node).textContent = "ready";
  const provider = $(".provider", node);
  populateSelect(provider, config.providers, "openai");
  const model = $(".model", node);
  model.value = config.providers.openai.models[0];
  provider.addEventListener("change", () => {
    model.value = config.providers[provider.value].models[0];
    renderCostPreview(node, session);
  });
  model.addEventListener("input", () => renderCostPreview(node, session));
  $(".remove-lane", node).addEventListener("click", () => {
    lanes.delete(session.id); node.remove();
    if (focusedLaneId === session.id) focusedLaneId = lanes.size ? lanes.keys().next().value : "";
    refreshLaneView();
  });
  $(".focus-lane", node).addEventListener("click", () => focusLane(session.id));
  $(".prepare", node).addEventListener("click", () => prepareLane(node));
  $(".send", node).addEventListener("click", () => sendLane(node));
  $("#lanes").append(node);
  lanes.set(session.id, {node, session});
  focusedLaneId = session.id;
  renderCostPreview(node, session);
  renderLaneState(node, session);
  refreshLaneView();
}

function refreshLaneView() {
  const root = $("#lanes");
  root.classList.toggle("single-view", laneViewMode === "single");
  for (const [sessionId, lane] of lanes.entries()) {
    const selected = sessionId === focusedLaneId;
    lane.node.classList.toggle("is-focused", selected);
    lane.node.classList.toggle("focus-hidden", laneViewMode === "single" && !selected);
  }
  const select = $("#focusedLane");
  const previous = focusedLaneId;
  select.replaceChildren();
  for (const [sessionId, lane] of lanes.entries()) {
    const option = el("option"); option.value = sessionId;
    option.textContent = `${lane.session.protocol_metadata.label} · ${(config.historical_runs[lane.session.historical_run] || {}).target_model || "live"}`;
    option.selected = sessionId === previous; select.append(option);
  }
  select.disabled = laneViewMode !== "single" || !lanes.size;
  $("#viewAll").classList.toggle("active", laneViewMode === "all");
  $("#viewSingle").classList.toggle("active", laneViewMode === "single");
  renderProgressStage();
}

function setLaneView(mode) {
  laneViewMode = mode;
  if (!focusedLaneId && lanes.size) focusedLaneId = lanes.keys().next().value;
  refreshLaneView();
}

function focusLane(sessionId) {
  focusedLaneId = sessionId;
  laneViewMode = "single";
  refreshLaneView();
  $("#lanesSection").scrollIntoView({behavior: "smooth", block: "start"});
}

function renderProgressStage() {
  const root = $("#progressOverview"); root.replaceChildren();
  if (!lanes.size) {
    root.append(el("p", "empty-stage", "아직 실행 레인이 없습니다."));
    return;
  }
  for (const [sessionId, lane] of lanes.entries()) {
    const session = lane.session;
    const card = el("article", "progress-card");
    card.dataset.sessionId = sessionId;
    const head = el("div", "progress-card-head");
    const title = el("div");
    title.append(el("p", "eyebrow", (config.historical_runs[session.historical_run] || {}).label || "LIVE RUN"));
    title.append(el("h2", "", session.protocol_metadata.label));
    head.append(title, el("span", session.completed ? "status-complete" : "status-running", session.completed ? "완료" : "진행 중"));
    card.append(head);
    const total = session.protocol === "red_persona_compact" ? 3 :
      session.protocol === "red_persona_direct_final" ? 2 :
      session.protocol === "direct_baseline" ? 1 : null;
    const progress = el("div", "progress-meter");
    const fill = el("span");
    fill.style.width = `${total ? Math.min(100, session.completed_steps.length / total * 100) : (session.completed ? 100 : 18)}%`;
    progress.append(fill); card.append(progress);
    card.append(el("p", "progress-count", total ? `${session.completed_steps.length} / ${total} 단계` : `${session.completed_steps.length} 단계 완료`));
    const steps = el("div", "stage-step-list");
    for (const step of session.completed_steps) {
      const row = el("article", "stage-step done");
      row.append(el("strong", "", `${step.stage} · ${step.role}`));
      row.append(el("p", "", step.response.text || "")); steps.append(row);
    }
    if (!session.completed) {
      const pending = el("article", "stage-step current");
      pending.append(el("strong", "", session.pending ? `준비됨 · ${session.pending.stage}` : "다음 단계 준비 전"));
      pending.append(el("p", "", session.pending ? session.pending.prompt : "해당 레인에서 ‘다음 단계 준비’를 누르세요."));
      steps.append(pending);
    }
    card.append(steps);
    const focus = el("button", "secondary", "이 레인 집중 보기");
    focus.addEventListener("click", () => { $("#progressStage").close(); focusLane(sessionId); });
    card.append(focus); root.append(card);
  }
}

function renderMessages(root, messages) {
  root.replaceChildren();
  messages.forEach((message, index) => {
    const card = el("div", "message");
    card.append(el("strong", "", `${index + 1} · ${message.role}`));
    const pre = el("pre"); pre.textContent = message.content; card.append(pre); root.append(card);
  });
}

function renderTimeline(node, steps) {
  const root = $(".live-timeline", node); root.replaceChildren();
  steps.forEach((step, index) => {
    const item = el("div", "timeline-item");
    item.append(el("h4", "", `${index + 1}. ${step.stage} · ${step.role}`));
    const meta = el("p", "hint", `${step.response.provider} / ${step.response.model} · ${step.response.latency_seconds}s · ${step.response.finish_reason || ""}`);
    item.append(meta);
    const response = el("pre", "response"); response.textContent = step.response.text; item.append(response);
    const details = el("details"); const summary = el("summary", "", "실제 전송 messages"); details.append(summary, jsonBlock(step.messages)); item.append(details);
    root.append(item);
  });
}

function renderLaneState(node, session) {
  $(".lane-state", node).textContent = session.completed ? "complete" : `${session.completed_steps.length} steps completed`;
  $(".prepare", node).disabled = session.completed;
  renderTimeline(node, session.completed_steps);
  if (session.completed) $(".pending", node).classList.add("hidden");
  renderProgressStage();
}

async function prepareLane(node, quoteOverride = "") {
  const errorNode = $(".lane-error", node); clearError(errorNode);
  const button = $(".prepare", node); button.disabled = true; button.textContent = "준비 중…";
  try {
    const sessionId = node.dataset.sessionId;
    const value = await api(`/api/session/${sessionId}/prepare`, {
      method: "POST", body: JSON.stringify({quote_override: quoteOverride}),
    });
    lanes.get(sessionId).session = value.session;
    renderPending(node, value.step);
    renderLaneState(node, value.session);
  } catch (error) { showError(errorNode, error); }
  finally {
    button.textContent = "다음 단계 준비";
    const lane = lanes.get(node.dataset.sessionId);
    button.disabled = lane ? lane.session.completed : false;
  }
}

function renderPending(node, step) {
  const pending = $(".pending", node); pending.classList.remove("hidden");
  $(".stage-role", node).textContent = step.role;
  $(".stage-name", node).textContent = step.stage;
  const selection = $(".selection-box", node); selection.replaceChildren();
  selection.append(el("strong", "", "Prompt/질문 선택 근거"), jsonBlock(step.selection));
  renderMessages($(".message-list", node), step.messages);
  $(".prompt-editor", node).value = step.prompt;
  const runtime = step.runtime_parameters || {};
  if (runtime.temperature != null) $(".temperature", node).value = runtime.temperature;
  if (runtime.max_tokens) $(".max-tokens", node).value = runtime.max_tokens;
  $(".runtime-preset", node).textContent =
    `Historical preset · temperature=${runtime.temperature ?? "omitted"} · max_tokens=${runtime.max_tokens ?? "omitted"} · top_p=${runtime.top_p || "omitted"} · seed=${runtime.seed || "omitted"}`;
  $(".reference-response", node).textContent = step.historical_reference_response || "(저장된 비교 응답 없음)";
  const quoteBox = $(".quote-box", node); quoteBox.replaceChildren();
  const candidates = step.selection.quote_candidates || [];
  if (candidates.length) {
    quoteBox.classList.remove("hidden");
    quoteBox.append(el("h3", "", "Target-authored exact quote 후보"));
    candidates.forEach((row, index) => {
      const label = el("label", "quote-option");
      const input = el("input"); input.type = "radio"; input.name = `quote-${node.dataset.sessionId}`; input.value = row.quote; input.checked = index === 0;
      label.append(input, document.createTextNode(" " + row.quote));
      label.append(el("small", "", `score=${row.score}, coverage=${row.goal_token_coverage}, exact=${row.exact_substring_verified}`)); quoteBox.append(label);
    });
    const apply = el("button", "secondary", "선택 인용으로 final prompt 다시 만들기");
    apply.addEventListener("click", () => {
      const selected = $(`input[name="quote-${node.dataset.sessionId}"]:checked`, node);
      if (selected) prepareLane(node, selected.value);
    });
    quoteBox.append(apply);
  } else quoteBox.classList.add("hidden");
}

async function sendLane(node) {
  const errorNode = $(".lane-error", node); clearError(errorNode);
  if (!$("#consent").checked) { showError(errorNode, "먼저 통제된 안전성 평가 동의 체크박스를 선택하세요."); return; }
  const key = $(".api-key", node).value.trim();
  if (!key) { showError(errorNode, "이 단계에 사용할 API key 또는 HF token을 입력하세요."); return; }
  const current = lanes.get(node.dataset.sessionId).session;
  if (!confirmCost(node, current)) return;
  const send = $(".send", node); send.disabled = true; send.textContent = "전송 중…";
  try {
    const sessionId = node.dataset.sessionId;
    const value = await api(`/api/session/${sessionId}/send`, {method: "POST", body: JSON.stringify({
      confirm_send: true,
      provider: $(".provider", node).value,
      api_key: key,
      model: $(".model", node).value,
      temperature: Number($(".temperature", node).value),
      max_tokens: Number($(".max-tokens", node).value),
      prompt_override: $(".prompt-editor", node).value,
    })});
    lanes.get(sessionId).session = value.session;
    $(".pending", node).classList.add("hidden");
    renderLaneState(node, value.session);
  } catch (error) { showError(errorNode, error); }
  finally { send.disabled = false; send.textContent = "이 단계만 모델에 전송"; }
}

async function init() {
  config = await api("/api/config");
  populateSelect($("#protocol"), config.protocols, "red_persona_compact");
  populateRunSelect($("#caseRun"), "red_persona_compact");
  populateRunSelect($("#historicalRun"), $("#protocol").value);
  await loadCases();
  $("#searchCases").addEventListener("click", loadCases);
  $("#randomCase").addEventListener("click", randomCase);
  $("#loadCase").addEventListener("click", loadCase);
  $("#historyEnabled").addEventListener("change", async () => {
    populateRunSelect($("#caseRun"), "red_persona_compact");
    populateRunSelect($("#historicalRun"), $("#protocol").value,
      !$("#protocol").value.startsWith("red_persona_"));
    await loadCases();
  });
  $("#caseRun").addEventListener("change", loadCases);
  $("#protocol").addEventListener("change", () => {
    populateRunSelect($("#historicalRun"), $("#protocol").value,
      !$("#protocol").value.startsWith("red_persona_"));
  });
  $("#searchPersonas").addEventListener("click", searchPersonaPool);
  $("#addLane").addEventListener("click", addLane);
  $("#viewAll").addEventListener("click", () => setLaneView("all"));
  $("#viewSingle").addEventListener("click", () => setLaneView("single"));
  $("#focusedLane").addEventListener("change", event => focusLane(event.target.value));
  $("#openPersonaStage").addEventListener("click", () => { renderPersonaStage(); $("#personaStage").showModal(); });
  $("#openProgressStage").addEventListener("click", () => { renderProgressStage(); $("#progressStage").showModal(); });
  $$(".close-dialog").forEach(button => button.addEventListener("click", () => button.closest("dialog").close()));
  $$('dialog').forEach(dialog => dialog.addEventListener("click", event => {
    if (event.target === dialog) dialog.close();
  }));
  $$(".copy").forEach(button => button.addEventListener("click", async () => {
    await navigator.clipboard.writeText($("#" + button.dataset.copy).textContent);
    button.textContent = "복사됨"; setTimeout(() => button.textContent = "복사", 1000);
  }));
}

init().catch(error => showError($("#globalError"), error));
