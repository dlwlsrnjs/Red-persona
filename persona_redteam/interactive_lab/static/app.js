const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

let config = null;
let currentCase = null;
const lanes = new Map();

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
  provider.addEventListener("change", () => { model.value = config.providers[provider.value].models[0]; });
  $(".remove-lane", node).addEventListener("click", () => { lanes.delete(session.id); node.remove(); });
  $(".prepare", node).addEventListener("click", () => prepareLane(node));
  $(".send", node).addEventListener("click", () => sendLane(node));
  $("#lanes").append(node);
  lanes.set(session.id, {node, session});
  renderLaneState(node, session);
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
  $$(".copy").forEach(button => button.addEventListener("click", async () => {
    await navigator.clipboard.writeText($("#" + button.dataset.copy).textContent);
    button.textContent = "복사됨"; setTimeout(() => button.textContent = "복사", 1000);
  }));
}

init().catch(error => showError($("#globalError"), error));
