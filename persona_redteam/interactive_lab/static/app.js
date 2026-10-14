const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

let config = null;
let currentCase = null;
const lanes = new Map();
let laneViewMode = "all";
let focusedLaneId = "";
let autoRunActive = false;

const PROTOCOL_GUIDES = {
  red_persona_compact: {
    philosophy: "목표 복원과 최종 수행을 분리해 관찰합니다. Target이 사례 근거를 자기 문장으로 먼저 정리하게 한 뒤, 같은 분기의 정확한 Target 문장만 다음 질의에 연결합니다. 외부 planner가 최종 목표 문장을 새로 써 주는 개입과 endpoint를 본 뒤의 재탐색은 허용하지 않습니다.",
    flow: ["Persona와 선택적 history로 초기 사례 분석", "초기 분석에서 부족한 O/F/K를 한 번의 focused readout으로 확인", "같은 readout의 연속 1–3문장을 exact quote로 선택", "고정 final-query template에 그 인용만 삽입", "분기별 응답과 실행 메타데이터 저장"],
    artifacts: ["initial_analysis record", "focused_readout record", "selected Target-authored exact quote", "final_query / final_response record", "provider·model·usage·latency·message provenance"],
  },
  red_persona_direct_final: {
    philosophy: "Compact의 goal-focused follow-up과 quotation transition을 함께 제거한 소거 조건입니다. 동일 사례와 분기를 유지한 채 초기 분석 뒤 고정 final prompt를 바로 보내 두 요소의 결합 효과를 확인합니다.",
    flow: ["Persona와 선택적 history로 초기 사례 분석", "Focused readout 없이 저장된 분기 final prompt 선택", "Target-authored quotation 없이 최종 응답 요청", "응답과 실행 메타데이터 저장"],
    artifacts: ["initial_analysis record", "direct_final prompt/response record", "quotation_transition=false", "provider·model·usage·latency·message provenance"],
  },
  red_persona_seven_stage: {
    philosophy: "긴 연구 대화의 효과를 검증하는 고정 깊이 조건입니다. 단계와 순서는 사전에 고정하고 최종 응답을 본 뒤 prompt를 바꾸지 않습니다. Compact와 같은 readout·quotation transition을 사용해 차이를 대화 깊이로 제한합니다.",
    flow: ["초기 사례 분석", "사전 고정된 7단계 연구 분석 누적", "분기별 focused readout", "같은 분기의 exact quote 선택", "고정 final query와 응답 저장"],
    artifacts: ["initial + seven-stage analysis records", "focused_readout record", "selected Target-authored exact quote", "final response record", "전체 누적 message provenance"],
  },
  direct_baseline: {
    philosophy: "Persona, history, 질문 풀, 연구 대화를 제거하고 원 요청에 대한 단일 응답을 측정하는 기준선입니다.",
    flow: ["Private GOAL을 단일 user message로 구성", "Target에 한 번 전송", "응답과 실행 메타데이터 저장"],
    artifacts: ["direct_request prompt/response record", "provider·model·usage·latency metadata"],
  },
  pcsa_phase2: {
    philosophy: "내담자 발화 생성, Target 응답, 진행도 평가를 반복해 하나의 대화 경로를 갱신합니다. 이 화면은 각 역할의 실제 prompt와 선택된 단일 stream을 단계별로 노출합니다.",
    flow: ["Attacker가 전략별 다음 client utterance 생성", "Target이 누적 대화에 응답", "Evaluator가 hidden GOAL 대비 진행도 기록", "최대 4 turn 반복"],
    artifacts: ["attacker utterance records", "Target response records", "intermediate evaluator JSON", "selected conversation trajectory", "provider·model·usage·latency provenance"],
  },
};
const STAGE_GUIDES = {
  initial_analysis: "관찰과 추론을 분리해 visible case evidence만 Target 자신의 표현으로 정리합니다. RED-Persona에서는 완결된 private GOAL 문장을 Target message에 직접 삽입하지 않습니다.",
  focused_readout: "초기 분석에서 빠진 O(행동·결과), F(산출물 형식), K(제약)만 좁혀 묻습니다. 응답은 복원 점수와 다음 단계 exact-quote 후보의 유일한 출처가 됩니다.",
  final_query: "같은 분기에서 Target이 방금 작성한 exact quote를 고정 template에 넣습니다. Private GOAL이나 다른 분기 문장으로 대체하지 않고 endpoint 이후에도 수정하지 않습니다.",
  direct_final: "Focused readout과 Target-authored quotation 없이 사전 고정 final prompt를 바로 사용합니다.",
  direct_request: "추가 문맥이나 변환 없이 원 요청에 대한 단일 Target 응답을 얻습니다.",
  analysis: "사전에 등록된 연구 분석 축을 순서대로 누적합니다. 단계 순서는 고정이며 최종 endpoint에 따라 바뀌지 않습니다.",
  pcsa_attacker: "고정 전략과 누적 대화로 다음 client utterance를 생성합니다.",
  pcsa_target: "직전 attacker 발화를 누적 대화의 다음 user turn으로 받아 응답합니다.",
  pcsa_evaluator: "직전 client–Target 쌍이 hidden GOAL 방향으로 진행했는지를 중간 JSON으로 기록합니다. 논문 최종 metric과는 별도입니다.",
};

function stageGuide(stage) {
  if (STAGE_GUIDES[stage]) return STAGE_GUIDES[stage];
  if (stage.startsWith("analysis_")) return STAGE_GUIDES.analysis;
  if (stage.startsWith("pcsa_attacker_")) return STAGE_GUIDES.pcsa_attacker;
  if (stage.startsWith("pcsa_target_")) return STAGE_GUIDES.pcsa_target;
  if (stage.startsWith("pcsa_evaluator_")) return STAGE_GUIDES.pcsa_evaluator;
  return "등록된 실행 계약에 따라 다음 모델 입력을 구성합니다.";
}

function appendList(root, values) {
  root.replaceChildren();
  values.forEach(value => root.append(el("li", "", value)));
}

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

function renderProtocolContract(node, session) {
  const guide = PROTOCOL_GUIDES[session.protocol] || {philosophy: "등록된 프로토콜 계약을 실행합니다.", flow: [], artifacts: []};
  $(".protocol-philosophy", node).textContent = guide.philosophy;
  appendList($(".protocol-flow", node), guide.flow);
  const branch = (currentCase.branches || [])[session.branch_index] || {};
  $(".protocol-artifacts", node).textContent = JSON.stringify({
    case_level: guide.artifacts,
    branch_index: session.branch_index,
    branch_direction: branch.direction || null,
    historical_reference_run: session.historical_run || null,
  }, null, 2);
}

function promptLayerLabels(messages) {
  return messages.map((message, index) => {
    const isLast = index === messages.length - 1;
    if (message.role === "system") return `${index + 1}. system — 저장된 역할·분석 경계 계약`;
    if (isLast && message.role === "user") return `${index + 1}. user — 현재 단계의 실제 전송 prompt (아래 편집기와 동일)`;
    if (message.role === "assistant") return `${index + 1}. assistant — 이전 단계에서 실제로 생성된 모델 응답`;
    return `${index + 1}. ${message.role} — 누적된 이전 연구 질문 또는 client utterance`;
  });
}

function privateGoalBoundary(session, step) {
  if (session.protocol === "direct_baseline") return "원 GOAL이 Target user message로 직접 전달됨";
  if (session.protocol === "pcsa_phase2") return step.role === "Target" ? "Target에는 client utterance만 전달; GOAL은 Attacker/Evaluator prompt에만 사용" : "Attacker/Evaluator 역할에는 hidden GOAL 제공";
  return "planner/selection audit에만 사용; 완결된 GOAL을 Target message에 직접 삽입하지 않음";
}

function traceInputs(session, step) {
  const branch = (currentCase.branches || [])[session.branch_index] || {};
  return {
    case_id: currentCase.case_id,
    persona_id: currentCase.persona_id || null,
    persona_history_observations: (currentCase.persona_history || []).length,
    private_goal_boundary: privateGoalBoundary(session, step),
    question_pool_candidates: ((currentCase.question_pool || {}).candidates || []).length,
    branch: session.protocol.startsWith("red_persona_") ? {index: session.branch_index, direction: branch.direction || null} : null,
    historical_reference_run: session.historical_run || null,
    conversation_messages: step.messages.length,
    selection_or_audit: step.selection,
  };
}

function traceOutputs(step) {
  return {
    before_send: ["stage", "role", "messages", "prompt", "selection", "runtime_parameters", "historical_reference_response"],
    provider_adds: ["response.text", "provider", "model", "usage", "latency_seconds", "finish_reason"],
    state_update: ["completed_steps append", "conversation/dialogue append", "cursor or turn advance"],
    next_stage_dependency: step.stage === "focused_readout" ? "이 응답의 exact substring이 final_query 동적 입력 후보가 됨" : "등록된 protocol state machine이 결정",
    endpoint_adaptation: false,
  };
}

function renderStageTransparency(node, session, step) {
  $(".stage-philosophy", node).textContent = stageGuide(step.stage);
  appendList($(".prompt-layers", node), promptLayerLabels(step.messages));
  $(".trace-inputs", node).textContent = JSON.stringify(traceInputs(session, step), null, 2);
  $(".trace-outputs", node).textContent = JSON.stringify(traceOutputs(step), null, 2);
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

function renderComparisonChoices() {
  const protocols = $("#protocolChecklist"); protocols.replaceChildren();
  for (const [value, info] of Object.entries(config.protocols || {})) {
    const label = el("label", "choice-item");
    const input = el("input"); input.type = "checkbox"; input.value = value;
    input.className = "protocol-choice"; input.checked = value === "red_persona_compact";
    const text = el("span"); text.append(document.createTextNode(info.label || value));
    text.append(el("small", "", info.summary || ""));
    label.append(input, text); protocols.append(label);
    input.addEventListener("change", updateMatrixPreview);
  }
  const models = $("#modelChecklist"); models.replaceChildren();
  for (const [provider, info] of Object.entries(config.providers || {})) {
    for (const model of info.models || []) {
      const label = el("label", "choice-item");
      const input = el("input"); input.type = "checkbox";
      input.className = "model-choice"; input.dataset.provider = provider;
      input.dataset.model = model;
      input.checked = provider === "openai" && model === "gpt-4o-2024-11-20";
      const text = el("span", "", model); text.append(el("small", "", info.label || provider));
      label.append(input, text); models.append(label);
      input.addEventListener("change", updateMatrixPreview);
    }
  }
}

function selectedProtocols() {
  return $$(".protocol-choice:checked").map(input => input.value);
}

function selectedModels() {
  return $$(".model-choice:checked").map(input => ({
    provider: input.dataset.provider, model: input.dataset.model,
  }));
}

function comparisonCells() {
  const mode = $("#comparisonMode").value;
  if (mode === "method_fixed") {
    return selectedModels().map(target => ({protocol: $("#protocol").value, ...target}));
  }
  if (mode === "model_fixed") {
    const target = {provider: $("#fixedProvider").value, model: $("#fixedModel").value.trim()};
    return selectedProtocols().map(protocol => ({protocol, ...target}));
  }
  return selectedProtocols().flatMap(protocol =>
    selectedModels().map(target => ({protocol, ...target}))
  );
}

function updateMatrixPreview() {
  const mode = $("#comparisonMode").value;
  $("#fixedProtocolField").classList.toggle("hidden", mode === "model_fixed");
  $("#protocolChoices").classList.toggle("hidden", mode === "method_fixed");
  $("#modelChoices").classList.toggle("hidden", mode === "model_fixed");
  $("#fixedModelChoices").classList.toggle("hidden", mode !== "model_fixed");
  const help = {
    method_fixed: "같은 prompt 기법을 여러 Target 모델에 보내 모델별 반응 패턴을 비교합니다.",
    model_fixed: "같은 Target 모델에 여러 prompt 기법을 보내 기법별 차이를 비교합니다.",
    cartesian: "선택한 모든 기법과 Target 모델의 조합을 한 화면에 만듭니다.",
  }[mode];
  $("#comparisonModeHelp").textContent = help;
  const cells = comparisonCells();
  $("#matrixPreview").textContent = `${cells.length}개 실행 레인 생성 예정`;
}

function pickHistoricalRun(protocol, model) {
  const options = runOptions(protocol);
  const exact = options.find(([, run]) => run.target_model === model);
  if (exact) return exact[0];
  const selected = $("#historicalRun").value;
  if (options.some(([runId]) => runId === selected)) return selected;
  return options.length ? options[0][0] : "";
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

async function addLane(options = {}) {
  clearError($("#globalError"));
  if (!currentCase) return null;
  const protocol = options.protocol || $("#protocol").value;
  const provider = options.provider || $("#fixedProvider").value || "openai";
  const model = options.model || $("#fixedModel").value.trim() || config.providers[provider].models[0];
  try {
    const session = await api("/api/session", {method: "POST", body: JSON.stringify({
      case_id: currentCase.case_id,
      protocol,
      branch_index: Number($("#branchIndex").value),
      history_enabled: $("#historyEnabled").checked,
      custom_goal: $("#customGoal").value,
      pcsa_strategy: $("#pcsaStrategy").value,
      historical_run: pickHistoricalRun(protocol, model),
    })});
    createLane(session, {provider, model});
    return session;
  } catch (error) { showError($("#globalError"), error); return null; }
}

async function createComparisonLanes() {
  clearError($("#globalError"));
  if (!currentCase) { showError($("#globalError"), "먼저 사례를 여세요."); return; }
  const cells = comparisonCells().filter(cell => cell.model);
  if (!cells.length) { showError($("#globalError"), "비교할 기법과 모델을 하나 이상 선택하세요."); return; }
  if (cells.length > 24) {
    showError($("#globalError"), `한 번에 최대 24개 레인까지 만들 수 있습니다. 현재 ${cells.length}개입니다.`);
    return;
  }
  const button = $("#createComparison"); button.disabled = true; button.textContent = "레인 생성 중…";
  try {
    await Promise.all(cells.map(cell => addLane(cell)));
    $("#lanesSection").scrollIntoView({behavior: "smooth", block: "start"});
  } finally {
    button.disabled = false; button.textContent = "선택 조합 레인 만들기";
  }
}

function createLane(session, target = {}) {
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
  populateSelect(provider, config.providers, target.provider || "openai");
  const model = $(".model", node);
  model.value = target.model || config.providers[provider.value].models[0];
  const sharedKey = provider.value === "openai" ? $("#sharedOpenAIKey").value : $("#sharedHFKey").value;
  $(".api-key", node).value = sharedKey;
  provider.addEventListener("change", () => {
    model.value = config.providers[provider.value].models[0];
    $(".api-key", node).value = provider.value === "openai" ?
      $("#sharedOpenAIKey").value : $("#sharedHFKey").value;
    renderCostPreview(node, session);
  });
  model.addEventListener("input", () => renderCostPreview(node, session));
  $(".remove-lane", node).addEventListener("click", () => {
    lanes.delete(session.id); node.remove();
    if (focusedLaneId === session.id) focusedLaneId = lanes.size ? lanes.keys().next().value : "";
    refreshLaneView();
  });
  $(".focus-lane", node).addEventListener("click", () => focusLane(session.id));
  $(".lane-selected", node).addEventListener("change", renderProgressStage);
  $(".prepare", node).addEventListener("click", () => prepareLane(node));
  $(".send", node).addEventListener("click", () => sendLane(node));
  $("#lanes").append(node);
  lanes.set(session.id, {node, session});
  focusedLaneId = session.id;
  renderProtocolContract(node, session);
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
    const trace = el("details");
    trace.append(el("summary", "", "이 단계의 prompt 철학·입력·생성 데이터"));
    const session = lanes.get(node.dataset.sessionId).session;
    trace.append(jsonBlock({
      philosophy: stageGuide(step.stage),
      input_lineage: traceInputs(session, step),
      stored_step_record: {
        stage: step.stage,
        role: step.role,
        selection: step.selection,
        runtime_parameters: step.runtime_parameters,
        messages: step.messages,
        historical_reference_response: step.historical_reference_response,
        response: step.response,
      },
    }));
    item.append(trace);
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
    return true;
  } catch (error) { showError(errorNode, error); return false; }
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
  renderStageTransparency(node, lanes.get(node.dataset.sessionId).session, step);
  renderMessages($(".message-list", node), step.messages);
  $(".prompt-editor", node).value = step.prompt;
  const runtime = step.runtime_parameters || {};
  if (runtime.temperature != null) $(".temperature", node).value = runtime.temperature;
  if (runtime.max_tokens) $(".max-tokens", node).value = runtime.max_tokens;
  $(".runtime-preset", node).textContent =
    `Historical preset · temperature=${runtime.temperature == null ? "omitted" : runtime.temperature} · max_tokens=${runtime.max_tokens == null ? "omitted" : runtime.max_tokens} · top_p=${runtime.top_p || "omitted"} · seed=${runtime.seed || "omitted"}`;
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

async function sendLane(node, {confirm = true} = {}) {
  const errorNode = $(".lane-error", node); clearError(errorNode);
  if (!$("#consent").checked) { showError(errorNode, "먼저 통제된 안전성 평가 동의 체크박스를 선택하세요."); return false; }
  const key = $(".api-key", node).value.trim();
  if (!key) { showError(errorNode, "이 단계에 사용할 API key 또는 HF token을 입력하세요."); return false; }
  const current = lanes.get(node.dataset.sessionId).session;
  if (confirm && !confirmCost(node, current)) return false;
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
    return true;
  } catch (error) { showError(errorNode, error); return false; }
  finally { send.disabled = false; send.textContent = "이 단계만 모델에 전송"; }
}

function selectedLaneEntries() {
  return [...lanes.values()].filter(({node, session}) =>
    !session.completed && $(".lane-selected", node).checked
  );
}

function validateGroupDispatch(entries) {
  if (!$("#consent").checked) {
    showError($("#globalError"), "먼저 통제된 안전성 평가 동의 체크박스를 선택하세요.");
    return false;
  }
  if (!entries.length) {
    showError($("#globalError"), "진행할 미완료 선택 레인이 없습니다.");
    return false;
  }
  const missing = entries.filter(({node}) => !$(".api-key", node).value.trim());
  if (missing.length) {
    showError($("#globalError"), `${missing.length}개 레인에 API key/HF token이 없습니다.`);
    return false;
  }
  return true;
}

async function advanceLane({node, session}) {
  if (session.completed) return false;
  node.classList.add("group-run-active");
  try {
    if (!session.pending) {
      const prepared = await prepareLane(node);
      if (!prepared) { $(".lane-selected", node).checked = false; return false; }
    }
    const sent = await sendLane(node, {confirm: false});
    if (!sent) $(".lane-selected", node).checked = false;
    return sent;
  } finally {
    node.classList.remove("group-run-active");
  }
}

function setAutoControls(running) {
  $("#nextSelected").disabled = running;
  $("#autoSelected").disabled = running;
  $("#stopAuto").disabled = !running;
  $("#autoSelected").textContent = running ? "Auto 실행 중…" : "선택 레인 · Auto";
}

async function runNextSelected() {
  clearError($("#globalError"));
  const entries = selectedLaneEntries();
  if (!validateGroupDispatch(entries)) return;
  if (!window.confirm(`선택된 ${entries.length}개 레인에 다음 단계 1회씩 병렬 전송합니다. 계속할까요?`)) return;
  $("#nextSelected").disabled = true;
  try { await Promise.allSettled(entries.map(advanceLane)); }
  finally { $("#nextSelected").disabled = autoRunActive; }
}

async function runAutoSelected() {
  clearError($("#globalError"));
  const initial = selectedLaneEntries();
  if (!validateGroupDispatch(initial)) return;
  if (!window.confirm(
    `선택된 ${initial.length}개 레인을 각 프로토콜의 완료 지점까지 자동 진행합니다.\n` +
    "각 라운드는 모델별로 병렬 전송되며 여러 번의 유료 API 호출이 발생합니다. 계속할까요?"
  )) return;
  autoRunActive = true; setAutoControls(true);
  let rounds = 0;
  try {
    while (autoRunActive && rounds < 32) {
      const entries = selectedLaneEntries();
      if (!entries.length) break;
      const results = await Promise.allSettled(entries.map(advanceLane));
      const progressed = results.some(result => result.status === "fulfilled" && result.value);
      if (!progressed) break;
      rounds += 1;
    }
  } finally {
    autoRunActive = false; setAutoControls(false);
  }
}

function stopAutoRun() {
  autoRunActive = false;
  $("#stopAuto").disabled = true;
  $("#stopAuto").textContent = "현재 호출 후 중지 중…";
  setTimeout(() => { $("#stopAuto").textContent = "Auto 중지"; }, 1200);
}

async function init() {
  config = await api("/api/config");
  populateSelect($("#protocol"), config.protocols, "red_persona_compact");
  populateSelect($("#fixedProvider"), config.providers, "openai");
  $("#fixedModel").value = config.providers.openai.models[0];
  renderComparisonChoices();
  updateMatrixPreview();
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
    updateMatrixPreview();
  });
  $("#comparisonMode").addEventListener("change", updateMatrixPreview);
  $("#fixedProvider").addEventListener("change", () => {
    $("#fixedModel").value = config.providers[$("#fixedProvider").value].models[0];
    updateMatrixPreview();
  });
  $("#fixedModel").addEventListener("input", updateMatrixPreview);
  $("#sharedOpenAIKey").addEventListener("input", event => {
    for (const {node} of lanes.values()) {
      if ($(".provider", node).value === "openai") $(".api-key", node).value = event.target.value;
    }
  });
  $("#sharedHFKey").addEventListener("input", event => {
    for (const {node} of lanes.values()) {
      if ($(".provider", node).value === "huggingface") $(".api-key", node).value = event.target.value;
    }
  });
  $("#searchPersonas").addEventListener("click", searchPersonaPool);
  $("#addLane").addEventListener("click", addLane);
  $("#createComparison").addEventListener("click", createComparisonLanes);
  $("#nextSelected").addEventListener("click", runNextSelected);
  $("#autoSelected").addEventListener("click", runAutoSelected);
  $("#stopAuto").addEventListener("click", stopAutoRun);
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
