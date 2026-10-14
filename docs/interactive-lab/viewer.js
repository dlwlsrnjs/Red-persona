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
  renderModelResults();
  renderQuestions();
  renderProtocols();
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
