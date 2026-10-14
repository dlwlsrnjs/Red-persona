const $ = (selector, root = document) => root.querySelector(selector);
let caseIndex = [];
let currentCase = null;

function node(tag, className = "", text = "") {
  const value = document.createElement(tag);
  if (className) value.className = className;
  if (text !== "") value.textContent = String(text);
  return value;
}

function fail(target, error) {
  target.textContent = error.message || String(error);
  target.classList.remove("hidden");
}

async function json(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
  return response.json();
}

async function loadIndex() {
  const value = await json("data/index.json");
  caseIndex = value.cases;
  renderCaseList();
}

function renderCaseList() {
  const query = $("#query").value.trim().toLowerCase();
  const outcome = $("#outcome").value;
  const rows = caseIndex.filter(row =>
    (outcome === "all" || row.outcome === outcome) &&
    (!query || JSON.stringify(row).toLowerCase().includes(query))
  );
  const select = $("#caseSelect");
  select.replaceChildren();
  rows.forEach(row => {
    const option = node("option");
    option.value = row.file;
    option.textContent = `${row.case_id} · ${row.outcome} · ${row.persona_id || ""} · ${row.crisis_label || ""}`;
    select.append(option);
  });
  $("#caseCount").textContent = `${rows.length} cases`;
  return rows;
}

async function openCase(file = $("#caseSelect").value) {
  if (!file) return;
  currentCase = await json(`data/${file}`);
  renderCase();
}

function historyCards(root, history) {
  root.replaceChildren();
  (history || []).forEach((turn, index) => {
    const card = node("article", "timeline-item");
    card.append(node("h3", "", `Observation ${index + 1}`), node("p", "", turn.user || ""));
    const state = node("pre");
    state.textContent = typeof turn.persona_state === "string" ? turn.persona_state : JSON.stringify(turn.persona_state, null, 2);
    card.append(state);
    root.append(card);
  });
}

function openProtocol(protocol, run = null) {
  window.REDPersonaProtocolDetail.open({caseData: currentCase, protocol, run});
}

function renderCase() {
  const value = currentCase;
  $("#casePanel").classList.remove("hidden");
  $("#caseTitle").textContent = `${value.case_id} · ${value.persona_id || ""}`;
  $("#persona").textContent = value.persona || "";
  $("#goal").textContent = value.goal || "";
  const badges = $("#caseBadges");
  badges.replaceChildren();
  [value.crisis_label, value.source_dataset, value.historical_score.status].forEach(text => badges.append(node("span", "", text || "—")));
  historyCards($("#history"), value.persona_history);
  historyCards($("#dialogHistory"), value.persona_history);
  $("#dialogPersonaTitle").textContent = `${value.persona_id || "Persona"} · ${value.case_id}`;
  $("#dialogPersona").textContent = value.persona || "";
  $("#dialogGoal").textContent = value.goal || "";
  renderModelEndpoints();
  renderModelResults();
  renderQuestions();
  renderProtocols();
}

function outcomeState(value) {
  return value === true ? "success" : value === false ? "failure" : "unknown";
}

function outcomeText(value, success = "성공", failure = "실패") {
  return value === true ? success : value === false ? failure : "미평가";
}

function endpointMetrics(score = {}) {
  const root = node("div", "endpoint-metrics");
  [
    ["R", score.R, /^R[34]$/.test(score.R || "")],
    ["B", score.B, /^B[45]$/.test(score.B || "")],
    ["HB", score.harmbench_positive === true ? "+" : score.harmbench_positive === false ? "−" : "—", score.harmbench_positive],
    ["Joint", outcomeText(score.joint_success), score.joint_success],
  ].forEach(([label, value, positive]) => root.append(node("span", `metric-badge ${value === "—" || value === undefined ? "unknown" : positive ? "success" : "failure"}`, `${label} ${value == null ? "—" : value}`)));
  return root;
}

function renderModelEndpoints() {
  const root = $("#modelEndpointCards");
  root.replaceChildren();
  (currentCase.model_results || []).forEach(run => {
    const score = run.score || {};
    const endpoints = run.endpoint_responses || [];
    const branchScores = score.branches || [];
    const card = node("article", `endpoint-card run-${score.status || "unscored"}`);
    const head = node("div", "endpoint-head");
    const identity = node("div");
    identity.append(node("h3", "", run.target_model || run.label || "Target"), node("p", "", run.label || run.protocol || ""));
    const overall = node("span", `overall-outcome ${score.status || "unscored"}`, score.status === "success" ? "전체 성공" : score.status === "failure" ? "전체 실패" : "미평가");
    head.append(identity, overall);
    card.append(head);

    const summary = node("div", "endpoint-summary");
    [["R3+", score.r3_plus], ["B4+", score.b4_plus], ["HB+", score.harmbench_positive], ["Joint", score.strict_joint]].forEach(([label, value]) => summary.append(node("span", `metric-badge ${outcomeState(value)}`, `${label} ${value === true ? "✓" : value === false ? "×" : "—"}`)));
    card.append(summary);

    if (!endpoints.length) {
      card.append(node("p", "empty", "이 실행의 최종답변은 공개 스냅샷에 저장되지 않았습니다."));
      root.append(card);
      return;
    }

    const tabs = node("div", "endpoint-tabs");
    const answerHead = node("div", "endpoint-answer-head");
    const answerTitle = node("strong");
    const answer = node("pre", "endpoint-answer");
    const metrics = node("div");
    answerHead.append(answerTitle, metrics);
    const selectBranch = index => {
      [...tabs.children].forEach((button, buttonIndex) => button.classList.toggle("active", buttonIndex === index));
      const endpoint = endpoints[index] || {};
      const branchScore = branchScores[index] || {};
      answerTitle.textContent = `B${index + 1} · ${endpoint.direction || branchScore.direction || "branch"}`;
      answer.textContent = endpoint.response || "(빈 응답)";
      metrics.replaceChildren(endpointMetrics(branchScore));
    };
    endpoints.forEach((endpoint, index) => {
      const branchScore = branchScores[index] || {};
      const button = node("button", `endpoint-tab ${outcomeState(branchScore.joint_success)}`, `B${index + 1} ${outcomeText(branchScore.joint_success, "✓", "×")}`);
      button.type = "button";
      button.title = `${endpoint.direction || branchScore.direction || "branch"} · Joint ${outcomeText(branchScore.joint_success)}`;
      button.onclick = () => selectBranch(index);
      tabs.append(button);
    });
    card.append(tabs, answerHead, answer);
    const treeButton = node("button", "endpoint-tree-button", "이 모델·프로토콜의 실행 트리 보기");
    treeButton.type = "button";
    treeButton.onclick = () => openProtocol(run.protocol, run);
    card.append(treeButton);
    const preferred = branchScores.findIndex(value => value && value.joint_success === true);
    selectBranch(preferred >= 0 ? preferred : 0);
    root.append(card);
  });
}

function renderModelResults() {
  const table = node("table");
  const head = node("tr");
  ["Run", "Target", "Protocol", "R3+", "B4+", "HB+", "Joint"].forEach(value => head.append(node("th", "", value)));
  table.append(head);
  (currentCase.model_results || []).forEach(row => {
    const score = row.score || {};
    const tr = node("tr");
    tr.append(node("td", "", row.label || "—"), node("td", "", row.target_model || "—"));
    const protocolCell = node("td", "protocol-cell");
    protocolCell.append(window.REDPersonaProtocolDetail.createButton(row.protocol, () => openProtocol(row.protocol, row)));
    tr.append(protocolCell);
    [score.r3_plus, score.b4_plus, score.harmbench_positive, score.strict_joint].forEach(value => tr.append(node("td", "", value === true ? "✓" : value === false ? "×" : "—")));
    table.append(tr);
  });
  $("#modelResults").replaceChildren(table);
}

function renderQuestions() {
  const root = $("#questionPool");
  root.replaceChildren();
  ((currentCase.question_pool || {}).candidates || []).forEach((value, index) => {
    const card = node("article", "question");
    card.append(node("strong", "", `${index + 1}. ${value.focus || "candidate"}`), node("p", "", `Case A: ${value.similar_case || ""}`), node("p", "", `Case B: ${value.contrast_case || ""}`));
    const prompt = node("pre");
    prompt.textContent = value.research_question || "";
    card.append(prompt);
    root.append(card);
  });
}

function renderProtocols() {
  const root = $("#protocolRecords");
  root.replaceChildren();
  Object.entries(currentCase.protocol_scaffolds || {}).forEach(([protocol, scaffold]) => {
    const card = node("article", "question protocol-record-card");
    card.append(window.REDPersonaProtocolDetail.createButton(protocol, () => openProtocol(protocol), window.REDPersonaProtocolDetail.guideFor(protocol).label));
    if (!scaffold) {
      card.append(node("p", "", "저장 기록 없음"));
      root.append(card);
      return;
    }
    card.append(node("p", "", `Target: ${scaffold.target_model || "—"} · turns ${(scaffold.turns || []).length} · branches ${(scaffold.branches || []).length}`));
    const button = node("button", "primary protocol-open-button", "개괄표·트리·전체 prompt 보기");
    button.onclick = () => openProtocol(protocol);
    card.append(button);
    root.append(card);
  });
}

$("#search").onclick = renderCaseList;
$("#outcome").onchange = renderCaseList;
$("#openCase").onclick = () => openCase().catch(error => fail($("#error"), error));
$("#random").onclick = () => {
  const rows = renderCaseList();
  if (rows.length) openCase(rows[Math.floor(Math.random() * rows.length)].file).catch(error => fail($("#error"), error));
};
$("#personaStageButton").onclick = () => { if (currentCase) $("#personaDialog").showModal(); };
$("#personaDialog .close").onclick = () => $("#personaDialog").close();
$("#protocolDialog .close").onclick = () => $("#protocolDialog").close();
[$("#personaDialog"), $("#protocolDialog")].forEach(dialog => dialog.onclick = event => { if (event.target === dialog) dialog.close(); });

loadIndex().catch(error => fail($("#error"), error));
