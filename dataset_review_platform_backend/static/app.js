const state = {
  runs: [],
  tasks: [],
  currentRunId: null,
  currentTaskId: null,
  items: [],
  currentItemId: null,
  currentItem: null,
  currentDisplayImageSrc: "",
  currentReportType: "audit",
  currentRunReports: null,
  currentAgentAnalysis: null,
  currentAutoFixRecords: null,
  currentTaskLog: "",
  lastExportSummary: null,
  activeQueue: null,
  imageDisplay: {
    preferRaw: true,
  },
  filters: {
    riskBucket: "",
    decisionStatus: "",
    split: "",
    action: "",
    issueSource: "",
    owner: "",
    q: "",
  },
  pagination: {
    page: 1,
    limit: 20,
    total: 0,
  },
};

const els = {
  intakePathInput: document.getElementById("intakePathInput"),
  intakeDatasetNameInput: document.getElementById("intakeDatasetNameInput"),
  intakeRunNameInput: document.getElementById("intakeRunNameInput"),
  intakeSubmitBtn: document.getElementById("intakeSubmitBtn"),
  importStatus: document.getElementById("importStatus"),
  refreshRunsBtn: document.getElementById("refreshRunsBtn"),
  refreshTasksBtn: document.getElementById("refreshTasksBtn"),
  startAuditBtn: document.getElementById("startAuditBtn"),
  runsList: document.getElementById("runsList"),
  runsCount: document.getElementById("runsCount"),
  tasksList: document.getElementById("tasksList"),
  tasksCount: document.getElementById("tasksCount"),
  riskBucketFilter: document.getElementById("riskBucketFilter"),
  decisionStatusFilter: document.getElementById("decisionStatusFilter"),
  splitFilter: document.getElementById("splitFilter"),
  actionFilter: document.getElementById("actionFilter"),
  issueSourceFilter: document.getElementById("issueSourceFilter"),
  searchInput: document.getElementById("searchInput"),
  applyFiltersBtn: document.getElementById("applyFiltersBtn"),
  currentRunSummary: document.getElementById("currentRunSummary"),
  itemsCount: document.getElementById("itemsCount"),
  queueStatus: document.getElementById("queueStatus"),
  queueTitle: document.getElementById("queueTitle"),
  queueMeta: document.getElementById("queueMeta"),
  queuePrevBtn: document.getElementById("queuePrevBtn"),
  queueNextBtn: document.getElementById("queueNextBtn"),
  queueExitBtn: document.getElementById("queueExitBtn"),
  prevPageBtn: document.getElementById("prevPageBtn"),
  nextPageBtn: document.getElementById("nextPageBtn"),
  pageStatus: document.getElementById("pageStatus"),
  itemsList: document.getElementById("itemsList"),
  detailTitle: document.getElementById("detailTitle"),
  detailMeta: document.getElementById("detailMeta"),
  detailImage: document.getElementById("detailImage"),
  imageEmpty: document.getElementById("imageEmpty"),
  cleanViewToggle: document.getElementById("cleanViewToggle"),
  openImageBtn: document.getElementById("openImageBtn"),
  exportCleanedBtn: document.getElementById("exportCleanedBtn"),
  reauditExportBtn: document.getElementById("reauditExportBtn"),
  refreshReportsBtn: document.getElementById("refreshReportsBtn"),
  refreshAgentBtn: document.getElementById("refreshAgentBtn"),
  agentStateBadge: document.getElementById("agentStateBadge"),
  agentHeadline: document.getElementById("agentHeadline"),
  agentMetrics: document.getElementById("agentMetrics"),
  agentFindings: document.getElementById("agentFindings"),
  agentPlan: document.getElementById("agentPlan"),
  agentActions: document.getElementById("agentActions"),
  showAuditReportBtn: document.getElementById("showAuditReportBtn"),
  showLlmReportBtn: document.getElementById("showLlmReportBtn"),
  reportViewer: document.getElementById("reportViewer"),
  selectedTaskTitle: document.getElementById("selectedTaskTitle"),
  resumeTaskBtn: document.getElementById("resumeTaskBtn"),
  stopTaskBtn: document.getElementById("stopTaskBtn"),
  showTaskLogBtn: document.getElementById("showTaskLogBtn"),
  taskLogViewer: document.getElementById("taskLogViewer"),
  autoFixSummary: document.getElementById("autoFixSummary"),
  autoFixRecords: document.getElementById("autoFixRecords"),
  goldJson: document.getElementById("goldJson"),
  predJson: document.getElementById("predJson"),
  staticIssues: document.getElementById("staticIssues"),
  consistencyIssues: document.getElementById("consistencyIssues"),
  modelIssues: document.getElementById("modelIssues"),
  modelValidationIssues: document.getElementById("modelValidationIssues"),
  historyCount: document.getElementById("historyCount"),
  decisionHistory: document.getElementById("decisionHistory"),
  decisionInput: document.getElementById("decisionInput"),
  actionInput: document.getElementById("actionInput"),
  ownerInput: document.getElementById("ownerInput"),
  notesInput: document.getElementById("notesInput"),
  statusInput: document.getElementById("statusInput"),
  skipReasonInput: document.getElementById("skipReasonInput"),
  l2PrimaryInput: document.getElementById("l2PrimaryInput"),
  customerCountInput: document.getElementById("customerCountInput"),
  groupGenderInput: document.getElementById("groupGenderInput"),
  containsChildInput: document.getElementById("containsChildInput"),
  childAgeBucketInput: document.getElementById("childAgeBucketInput"),
  containsElderInput: document.getElementById("containsElderInput"),
  youngGroupInput: document.getElementById("youngGroupInput"),
  reasoningInput: document.getElementById("reasoningInput"),
  confidenceInput: document.getElementById("confidenceInput"),
  correctedPreview: document.getElementById("correctedPreview"),
  fillGoldBtn: document.getElementById("fillGoldBtn"),
  fillPredBtn: document.getElementById("fillPredBtn"),
  saveDecisionBtn: document.getElementById("saveDecisionBtn"),
  markPassBtn: document.getElementById("markPassBtn"),
  openLabelEditorBtn: document.getElementById("openLabelEditorBtn"),
  saveLabelCorrectionBtn: document.getElementById("saveLabelCorrectionBtn"),
  generateAcceptanceReportBtn: document.getElementById("generateAcceptanceReportBtn"),
  savedDecisionHint: document.getElementById("savedDecisionHint"),
  exportSummary: document.getElementById("exportSummary"),
  advancedFiltersPanel: document.getElementById("advancedFiltersPanel"),
  reportsPanel: document.getElementById("reportsPanel"),
  issuePanel: document.getElementById("issuePanel"),
  historyPanel: document.getElementById("historyPanel"),
  labelEditorPanel: document.getElementById("labelEditorPanel"),
  exportPanel: document.getElementById("exportPanel"),
  toast: document.getElementById("toast"),
  imageModal: document.getElementById("imageModal"),
  modalImage: document.getElementById("modalImage"),
  closeImageModalBtn: document.getElementById("closeImageModalBtn"),
};

function pretty(value) {
  return JSON.stringify(value ?? null, null, 2);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function shortPath(value, keepSegments = 3) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const normalized = raw.replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length <= keepSegments) return raw;
  return `.../${parts.slice(-keepSegments).join("/")}`;
}

function pathDisplayHtml(label, value, options = {}) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const short = shortPath(raw, options.keepSegments || 3);
  const codeClass = options.compact ? "path-chip" : "path-chip block";
  const copyLabel = options.copyLabel || "复制";
  return `
    <div class="path-line">
      <strong>${escapeHtml(label)}：</strong>
      <code class="${codeClass}" title="${escapeHtml(raw)}">${escapeHtml(short)}</code>
      <button
        type="button"
        class="copy-path-btn"
        onclick='window.copyTextToClipboard(${JSON.stringify(raw)})'
      >${escapeHtml(copyLabel)}</button>
    </div>
  `;
}

async function copyTextToClipboard(value) {
  const text = String(value || "");
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    showToast("路径已复制");
  } catch (error) {
    showToast("复制失败，请手动复制", "error", 1800);
  }
}

window.copyTextToClipboard = copyTextToClipboard;

function setStatus(text, isError = false) {
  els.importStatus.textContent = text || "";
  els.importStatus.style.color = isError ? "#c2410c" : "";
}

let toastTimer = null;

function showToast(text, type = "success", duration = 1600) {
  if (!els.toast) return;
  window.clearTimeout(toastTimer);
  els.toast.textContent = text;
  els.toast.className = `toast ${type}`;
  toastTimer = window.setTimeout(() => {
    els.toast.classList.add("hidden");
  }, duration);
}

window.showToast = showToast;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status}`);
  }
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function currentRun() {
  return state.runs.find((item) => item.id === state.currentRunId) || null;
}

function currentTask() {
  return state.tasks.find((item) => item.id === state.currentTaskId) || null;
}

function issueSourcesForItem(item) {
  return [
    item.static_issues?.length ? "static" : null,
    item.consistency_issues?.length ? "consistency" : null,
    item.model_issues?.length ? "model" : null,
    item.model_validation_issues?.length ? "validation" : null,
  ].filter(Boolean);
}

function renderTags(container, values) {
  container.innerHTML = "";
  if (!values || values.length === 0) {
    const span = document.createElement("span");
    span.className = "tag empty";
    span.textContent = "none";
    container.appendChild(span);
    return;
  }
  for (const value of values) {
    const span = document.createElement("span");
    span.className = "tag";
    span.textContent = value;
    container.appendChild(span);
  }
}

function renderDecisionHistory(history) {
  const items = history || [];
  els.decisionHistory.innerHTML = "";
  els.historyCount.textContent = items.length ? `${items.length} 条记录` : "暂无历史";
  if (!items.length) {
    els.decisionHistory.className = "history-list empty-state";
    els.decisionHistory.textContent = "当前样本还没有历史记录。";
    return;
  }
  els.decisionHistory.className = "history-list";
  for (const entry of items) {
    const block = document.createElement("div");
    block.className = "history-item";
    block.innerHTML = `
      <div class="history-item-head">
        <div class="history-item-title">${escapeHtml(entry.action)} / ${escapeHtml(entry.decision)}</div>
        <div class="history-item-meta">${escapeHtml(entry.updated_at || "")}</div>
      </div>
      <div class="history-item-meta">owner=${escapeHtml(entry.owner || "-")}${entry.created_at ? ` | created=${escapeHtml(entry.created_at)}` : ""}</div>
      <div class="history-item-notes">${escapeHtml(entry.notes || "无备注")}</div>
    `;
    els.decisionHistory.appendChild(block);
  }
}

async function updateDisplayedImage(item) {
  const endpoint =
    state.imageDisplay.preferRaw && item.has_raw_image
      ? `/api/items/${item.id}/raw-image`
      : `/api/items/${item.id}/image`;
  els.detailImage.style.display = "none";
  els.imageEmpty.style.display = "block";
  els.imageEmpty.textContent = "图片加载中...";
  els.openImageBtn.disabled = true;
  try {
    state.currentDisplayImageSrc = endpoint;
    els.detailImage.src = endpoint;
    els.detailImage.style.display = "block";
    els.imageEmpty.style.display = "none";
    els.openImageBtn.disabled = false;
  } catch (error) {
    state.currentDisplayImageSrc = "";
    els.imageEmpty.style.display = "block";
    els.imageEmpty.textContent = "图片加载失败";
  }
}

function buildCorrectedLabelFromForm() {
  return {
    status: els.statusInput.value,
    skip_reason: els.skipReasonInput.value,
    l2_relationship: { primary: els.l2PrimaryInput.value },
    l3_scene: { scene_tag: "dining" },
    l4_auxiliary_tags: {
      customer_count: Number(els.customerCountInput.value || 0),
      group_gender: els.groupGenderInput.value,
      contains_child: els.containsChildInput.value === "true",
      child_age_bucket: els.childAgeBucketInput.value,
      contains_elder: els.containsElderInput.value === "true",
      young_group: els.youngGroupInput.value === "true",
    },
    ops_tags: [],
    service_actions: [],
    reasoning: els.reasoningInput.value,
    confidence: Number(els.confidenceInput.value || 0),
  };
}

function updatePreview() {
  els.correctedPreview.textContent = pretty(buildCorrectedLabelFromForm());
}

function fillFormFromLabel(label) {
  const l2 = label?.l2_relationship || {};
  const l4 = label?.l4_auxiliary_tags || {};
  els.statusInput.value = label?.status || "VALID";
  els.skipReasonInput.value = label?.skip_reason || "OTHER";
  els.l2PrimaryInput.value = l2.primary || "unknown";
  els.customerCountInput.value = l4.customer_count ?? 0;
  els.groupGenderInput.value = l4.group_gender || "unknown";
  els.containsChildInput.value = String(Boolean(l4.contains_child));
  els.childAgeBucketInput.value = l4.child_age_bucket || "none";
  els.containsElderInput.value = String(Boolean(l4.contains_elder));
  els.youngGroupInput.value = String(Boolean(l4.young_group));
  els.reasoningInput.value = label?.reasoning || "";
  els.confidenceInput.value = label?.confidence ?? 0;
  updatePreview();
}

function isRemotePath(value) {
  return String(value || "").trim().startsWith("/");
}

function sourceBadgeHtml(kind) {
  const label = kind === "server" ? "服务器" : "本地";
  return `<span class="source-badge ${kind}">${label}</span>`;
}

function renderRuns() {
  els.runsList.innerHTML = "";
  if (els.runsCount) {
    els.runsCount.textContent = String(state.runs.length);
  }
  if (state.runs.length === 0) {
    els.runsList.innerHTML = `<div class="empty-state">还没有导入任何 run</div>`;
    return;
  }
  for (const run of state.runs) {
    const div = document.createElement("div");
    div.className = "run-card" + (run.id === state.currentRunId ? " active" : "");
    const sourceKind = isRemotePath(run.dataset_dir) ? "server" : "local";
    const issueSummary = [
      run.summary?.auto_fix_enabled
        ? `auto-fix=${run.summary?.auto_fix_initial_static_issue_count ?? 0}->${run.summary?.auto_fix_final_static_issue_count ?? 0}`
        : "auto-fix=off",
      `static=${run.static_issue_count}`,
      `consistency=${run.consistency_issue_count}`,
      `model=${run.model_flagged_rows}`,
    ].join(" · ");
    div.innerHTML = `
      <div class="run-card-title-row">
        <div class="run-card-title">${escapeHtml(run.run_name)}</div>
        ${sourceBadgeHtml(sourceKind)}
      </div>
      <div class="run-card-meta">
        dataset=${escapeHtml(run.dataset_name)}<br />
        imported=${run.imported_item_count} · decided=${run.decided_item_count}<br />
        ${escapeHtml(issueSummary)}
      </div>
    `;
    div.onclick = async () => {
      state.currentTaskId = null;
      await selectRun(run.id);
    };
    els.runsList.appendChild(div);
  }
}

function renderTasks() {
  els.tasksList.innerHTML = "";
  if (els.tasksCount) {
    els.tasksCount.textContent = String(state.tasks.length);
  }
  if (!state.tasks.length) {
    els.tasksList.innerHTML = `<div class="empty-state">还没有审计任务</div>`;
    return;
  }
  for (const task of state.tasks) {
    const div = document.createElement("div");
    div.className = `run-card task-card ${task.status}` + (task.id === state.currentTaskId ? " active" : "");
    const sourceKind = isRemotePath(task.dataset_dir) ? "server" : "local";
    const actionButtons = [];
    if (task.status === "running" || task.status === "pending") {
      actionButtons.push(`<button class="task-stop-btn" data-task-id="${task.id}" type="button">停止</button>`);
    }
    if (task.can_resume) {
      actionButtons.push(`<button class="task-resume-btn" data-task-id="${task.id}" type="button">继续运行</button>`);
    }
    const actionBlock = actionButtons.length
      ? `<div class="task-card-actions">${actionButtons.join("")}</div>`
      : "";
    const progressBlock = task.status === "running" || task.status === "pending"
      ? `
        <div class="task-progress-meta">
          <span>${escapeHtml(task.progress_stage || "")}</span>
          <span>${escapeHtml(task.progress_label || "")}</span>
        </div>
        <div class="task-progress-track">
          <div class="task-progress-fill ${escapeHtml(task.status)}" style="width:${Number(task.progress_percent || 0)}%"></div>
        </div>
        ${task.progress_updated_at ? `<div class="task-progress-updated">最近进度：${escapeHtml(task.progress_updated_at)}</div>` : ""}
      `
      : "";
    div.innerHTML = `
      <div class="run-card-title-row">
        <div class="run-card-title">${escapeHtml(task.run_name)}</div>
        ${sourceBadgeHtml(sourceKind)}
      </div>
      <div class="run-card-meta">
        status=${escapeHtml(task.status)}<br />
        dataset=${escapeHtml(task.dataset_name || "-")}<br />
        ${task.error_message ? `note=${escapeHtml(task.error_message)}` : `source_run=${task.source_run_id || "-"}`}
      </div>
      ${progressBlock}
      ${actionBlock}
    `;
    div.addEventListener("click", async () => {
      state.currentTaskId = task.id;
      renderTasks();
      await loadTaskLog(task.id);
      if (task.result_run_id) {
        await selectRun(task.result_run_id);
      } else {
        clearRunContextForPendingTask(task);
        els.selectedTaskTitle.textContent = `${task.run_name} (${task.status})`;
      }
    });
    els.tasksList.appendChild(div);
  }
  els.tasksList.querySelectorAll(".task-resume-btn").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const taskId = Number(button.getAttribute("data-task-id"));
      if (!Number.isFinite(taskId)) return;
      await resumeTaskById(taskId);
    });
  });
  els.tasksList.querySelectorAll(".task-stop-btn").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const taskId = Number(button.getAttribute("data-task-id"));
      if (!Number.isFinite(taskId)) return;
      await stopTaskById(taskId);
    });
  });
}

function renderItems() {
  els.itemsList.innerHTML = "";
  els.itemsCount.textContent = `共 ${state.pagination.total} 条`;
  const totalPages = Math.max(1, Math.ceil(state.pagination.total / state.pagination.limit));
  els.pageStatus.textContent = `第 ${state.pagination.page} / ${totalPages} 页`;
  els.prevPageBtn.disabled = state.pagination.page <= 1;
  els.nextPageBtn.disabled = state.pagination.page >= totalPages;
  renderQueueStatus();

  if (!state.items.length) {
    els.itemsList.className = "items-list empty-state";
    els.itemsList.textContent = "当前筛选条件下没有样本";
    return;
  }

  els.itemsList.className = "items-list";
  for (const item of state.items) {
    const decisionText = item.decision ? `${item.decision.action} / ${item.decision.owner || "未署名"}` : "未处理";
    const issueSources = issueSourcesForItem(item);
    const issueText = issueSources.join(", ") || "-";
    const orderText = item.order_id || "-";
    const sceneText = item.scene_id || "-";
    const div = document.createElement("div");
    div.className = "item-row" + (item.id === state.currentItemId ? " active" : "");
    div.innerHTML = `
      <div class="item-title">#${item.id} ${escapeHtml(item.risk_bucket)}</div>
      <div class="item-meta">
        r=${item.risk_score} | ${escapeHtml(item.split)}:${item.line_no} | ${escapeHtml(decisionText)}<br />
        order=${escapeHtml(orderText)} | scene=${escapeHtml(sceneText)}<br />
        issue=${escapeHtml(issueText)}
      </div>
    `;
    div.onclick = () => selectItem(item.id);
    els.itemsList.appendChild(div);
  }
  renderQueueStatus();
}

function renderQueueStatus() {
  if (!els.queueStatus) return;
  if (!state.activeQueue) {
    els.queueStatus.classList.add("hidden");
    return;
  }
  els.queueStatus.classList.remove("hidden");
  const currentIndex = state.items.findIndex((item) => item.id === state.currentItemId);
  const absoluteIndex = currentIndex >= 0
    ? (state.pagination.page - 1) * state.pagination.limit + currentIndex + 1
    : Math.min((state.pagination.page - 1) * state.pagination.limit + 1, state.pagination.total);
  const totalPages = Math.max(1, Math.ceil(state.pagination.total / state.pagination.limit));
  els.queueTitle.textContent = state.activeQueue.title || "当前复核队列";
  els.queueMeta.textContent = `第 ${absoluteIndex || 0} / ${state.pagination.total || 0} 条，页 ${state.pagination.page} / ${totalPages}`;
  els.queuePrevBtn.disabled = state.pagination.total === 0 || (state.pagination.page <= 1 && currentIndex <= 0);
  els.queueNextBtn.disabled = state.pagination.total === 0 || (state.pagination.page >= totalPages && currentIndex >= state.items.length - 1);
}

function updateReportTabState() {
  els.showAuditReportBtn.classList.toggle("active", state.currentReportType === "audit");
  els.showLlmReportBtn.classList.toggle("active", state.currentReportType === "llm");
}

function renderCurrentReport() {
  updateReportTabState();
  const reports = state.currentRunReports;
  const hasReports = Boolean(reports);
  els.showAuditReportBtn.disabled = !hasReports;
  els.showLlmReportBtn.disabled = !hasReports;
  if (!reports) {
    els.reportViewer.textContent = "当前还没有可显示的报告。任务完成后，审计报告和模型报告会出现在这里。";
    return;
  }
  const content = state.currentReportType === "llm" ? reports.llm_report_content : reports.audit_report_content;
  els.reportViewer.textContent = content || "当前报告尚未生成。";
}

function renderAutoFixSummary(run = null, analysis = null) {
  if (!els.autoFixSummary) return;
  if (!run) {
    els.autoFixSummary.className = "summary-block muted";
    els.autoFixSummary.textContent = "选择 run 后，这里会显示自动修复摘要。";
    return;
  }
  const summary = run.summary || {};
  const autoFix = analysis?.auto_fix || {};
  const enabled = Boolean(summary.auto_fix_enabled || autoFix.enabled);
  if (!enabled) {
    els.autoFixSummary.className = "summary-block muted";
    els.autoFixSummary.innerHTML = `
      <div><strong>状态：</strong>本轮没有启用自动修复。</div>
      ${pathDisplayHtml("数据集目录", run.dataset_dir || "", { keepSegments: 4 })}
    `;
    return;
  }
  const initial = Number(summary.auto_fix_initial_static_issue_count ?? autoFix.initial_static_issue_count ?? 0);
  const final = Number(summary.auto_fix_final_static_issue_count ?? autoFix.final_static_issue_count ?? 0);
  const changed = Number(summary.auto_fix_changed_rows ?? autoFix.changed_rows ?? 0);
  const rounds = Number(summary.auto_fix_rounds ?? autoFix.rounds ?? 0);
  const effectiveDir = summary.effective_dataset_dir || autoFix.effective_dataset_dir || run.dataset_dir || "";
  const reduced = Math.max(0, initial - final);
  const verdict = final === 0 ? "静态冲突已清零" : `静态冲突仍剩 ${final} 个`;
  els.autoFixSummary.className = "summary-block";
  els.autoFixSummary.innerHTML = `
    <div><strong>自动修复轮数：</strong>${rounds}</div>
    <div><strong>静态问题变化：</strong>${initial} -> ${final}（减少 ${reduced}）</div>
    <div><strong>被修样本数：</strong>${changed}</div>
    <div><strong>当前结论：</strong>${escapeHtml(verdict)}</div>
    ${pathDisplayHtml("修后数据集", effectiveDir, { keepSegments: 4 })}
  `;
}

function labelSnapshotText(label) {
  const l2 = label?.l2_relationship || {};
  const l4 = label?.l4_auxiliary_tags || {};
  return [
    `status=${label?.status ?? "-"}`,
    `skip=${label?.skip_reason ?? "-"}`,
    `l2=${l2.primary ?? "-"}`,
    `count=${l4.customer_count ?? "-"}`,
    `gender=${l4.group_gender ?? "-"}`,
  ].join(" | ");
}

function renderAutoFixRecords() {
  if (!els.autoFixRecords) return;
  const payload = state.currentAutoFixRecords;
  if (!payload) {
    els.autoFixRecords.className = "summary-block muted";
    els.autoFixRecords.textContent = "选择 run 后，这里会显示模型自动改标记录。";
    return;
  }

  const summary = payload.summary || {};
  const changes = Array.isArray(payload.changes) ? payload.changes : [];
  const modelChanges = changes.filter((item) => item.change_source === "model");
  if (!modelChanges.length) {
    els.autoFixRecords.className = "summary-block muted";
    const attemptCount = Number(summary.model_attempt_rows || 0);
    const acceptedCount = Number(summary.accepted_model_rows || 0);
    els.autoFixRecords.innerHTML = `
      <div><strong>模型尝试改标：</strong>${attemptCount}</div>
      <div><strong>模型接受改标：</strong>${acceptedCount}</div>
      <div>当前 run 里还没有可展示的模型自动改标明细。</div>
    `;
    return;
  }

  const topRows = modelChanges.slice(0, 12);
  const acceptedCount = modelChanges.filter((item) => item.status === "accepted").length;
  const rejectedCount = modelChanges.filter((item) => item.status === "rejected").length;
  const failedCount = modelChanges.filter((item) => item.status === "request_failed").length;
  els.autoFixRecords.className = "summary-block auto-fix-records";
  els.autoFixRecords.innerHTML = `
    <div class="auto-fix-records-meta">
      <span><strong>模型尝试：</strong>${modelChanges.length}</span>
      <span><strong>接受：</strong>${acceptedCount}</span>
      <span><strong>拒绝：</strong>${rejectedCount}</span>
      <span><strong>失败：</strong>${failedCount}</span>
    </div>
    ${pathDisplayHtml("修后目录", payload.fixed_dataset_dir || "", { keepSegments: 4 })}
    <div class="auto-fix-record-list">
      ${topRows
        .map((item) => {
          const beforeIssues = (item.before_issues || []).join(", ") || "-";
          const afterIssues = (item.after_issues || []).join(", ") || "-";
          const status = item.status || "accepted";
          const actions = Array.isArray(item.change_actions) ? item.change_actions.join(", ") : "";
          const beforeLabel = item.before_label ? labelSnapshotText(item.before_label) : "";
          const afterLabel = item.after_label ? labelSnapshotText(item.after_label) : "";
          return `
            <div class="auto-fix-record-item">
              <div class="auto-fix-record-head">
                <strong>${escapeHtml(`${item.split || "-"}:${item.line_no || "-"}`)}</strong>
                <span class="tag">${escapeHtml(status)}</span>
              </div>
              <div class="auto-fix-record-path">${escapeHtml(item.image || "")}</div>
              <div class="auto-fix-record-issues"><strong>修前：</strong>${escapeHtml(beforeIssues)}</div>
              <div class="auto-fix-record-issues"><strong>修后：</strong>${escapeHtml(afterIssues)}</div>
              ${beforeLabel ? `<div class="auto-fix-record-issues"><strong>改前标签：</strong>${escapeHtml(beforeLabel)}</div>` : ""}
              ${afterLabel ? `<div class="auto-fix-record-issues"><strong>改后标签：</strong>${escapeHtml(afterLabel)}</div>` : ""}
              ${actions ? `<div class="auto-fix-record-issues"><strong>规则动作：</strong>${escapeHtml(actions)}</div>` : ""}
              ${item.error ? `<div class="auto-fix-record-error">${escapeHtml(item.error)}</div>` : ""}
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function clearRunContextForPendingTask(task) {
  state.currentRunId = null;
  state.currentRunReports = null;
  state.currentAgentAnalysis = null;
  state.currentAutoFixRecords = null;
  state.activeQueue = null;
  state.items = [];
  state.pagination.total = 0;
  renderRuns();
  renderRunSummary(null);
  renderAutoFixSummary(null, null);
  renderAutoFixRecords();
  renderAgentAnalysis();
  renderItems();
  clearDetail();
  els.exportCleanedBtn.disabled = true;
  els.reportViewer.textContent = task
    ? `${task.run_name} 当前${task.status === "running" ? "正在运行" : "等待执行"}，报告会在任务完成后显示在这里。`
    : "当前没有可显示的报告。";
  updateSelectedTaskActions();
}

function updateSelectedTaskActions() {
  const task = currentTask();
  if (!task || !els.resumeTaskBtn || !els.stopTaskBtn) {
    if (els.resumeTaskBtn) {
      els.resumeTaskBtn.disabled = true;
      els.resumeTaskBtn.textContent = "继续运行";
    }
    if (els.stopTaskBtn) {
      els.stopTaskBtn.disabled = true;
    }
    return;
  }
  els.resumeTaskBtn.disabled = !task.can_resume;
  els.resumeTaskBtn.textContent = task.source_kind === "server" ? "继续运行（服务器）" : "继续运行（本地）";
  els.stopTaskBtn.disabled = !(task.status === "running" || task.status === "pending");
}

function clearDetail() {
  state.currentItemId = null;
  state.currentItem = null;
  state.currentDisplayImageSrc = "";
  els.detailTitle.textContent = "样本详情";
  els.detailMeta.textContent = "暂无选中样本";
  els.detailImage.style.display = "none";
  els.detailImage.src = "";
  els.imageEmpty.style.display = "block";
  els.imageEmpty.textContent = "选中样本后显示图片";
  els.openImageBtn.disabled = true;
  els.goldJson.textContent = "";
  els.predJson.textContent = "";
  renderTags(els.staticIssues, []);
  renderTags(els.consistencyIssues, []);
  renderTags(els.modelIssues, []);
  renderTags(els.modelValidationIssues, []);
  renderDecisionHistory([]);
  els.savedDecisionHint.textContent = "";
  updatePreview();
}

function renderDetail(item) {
  state.currentItem = item;
  state.currentItemId = item.id;
  els.detailTitle.textContent = `样本 #${item.id}`;
  els.detailMeta.textContent = `risk=${item.risk_score} | ${item.split}:${item.line_no} | order=${item.order_id || "-"} | scene=${item.scene_id || "-"}`;
  els.goldJson.textContent = pretty(item.label_json);
  els.predJson.textContent = pretty(item.model_prediction_json);
  renderTags(els.staticIssues, item.static_issues);
  renderTags(els.consistencyIssues, item.consistency_issues);
  renderTags(els.modelIssues, item.model_issues);
  renderTags(els.modelValidationIssues, item.model_validation_issues);
  renderDecisionHistory(item.decision_history);
  updateDisplayedImage(item);

  const decision = item.decision;
  if (decision) {
    els.decisionInput.value = decision.decision === "needs_rework" ? "acceptance_issue" : decision.decision;
    els.actionInput.value = decision.action;
    els.ownerInput.value = decision.owner || "";
    els.notesInput.value = decision.notes || "";
    els.savedDecisionHint.textContent = `最近保存：${decision.updated_at || "未知时间"}`;
    fillFormFromLabel(decision.corrected_label_json || item.label_json);
  } else {
    els.decisionInput.value = "acceptance_pass";
    els.actionInput.value = "keep";
    els.ownerInput.value = "";
    els.notesInput.value = "";
    els.savedDecisionHint.textContent = "";
    fillFormFromLabel(item.label_json);
  }
  renderQueueStatus();
}

function openLabelEditor(prefill = true) {
  if (!state.currentItemId) return;
  if (els.labelEditorPanel) {
    els.labelEditorPanel.open = true;
    els.labelEditorPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  els.decisionInput.value = "label_corrected";
  els.actionInput.value = "replace_label";
  if (!els.notesInput.value.trim()) {
    els.notesInput.value = "人工修正标签后通过";
  }
  if (prefill) {
    fillFormFromLabel(state.currentItem?.decision?.corrected_label_json || state.currentItem?.label_json);
  }
  updatePreview();
}

function openImageModal() {
  if (!state.currentItemId) return;
  els.modalImage.src = state.currentDisplayImageSrc || `/api/items/${state.currentItemId}/image`;
  els.imageModal.classList.remove("hidden");
}

function closeImageModal() {
  els.imageModal.classList.add("hidden");
  els.modalImage.src = "";
}

function renderRunSummary(run) {
  if (!run) {
    els.currentRunSummary.textContent = "请选择一个 run";
    return;
  }
  const summary = run.summary || {};
  const autoFixText = summary.auto_fix_enabled
    ? `auto-fix: ${summary.auto_fix_initial_static_issue_count ?? 0}->${summary.auto_fix_final_static_issue_count ?? 0}`
    : "auto-fix: off";
  els.currentRunSummary.innerHTML = `
    <span class="summary-pill">run: ${escapeHtml(run.run_name)}</span>
    <span class="summary-pill">dataset: ${escapeHtml(run.dataset_name)}</span>
    <span class="summary-pill">imported: ${run.imported_item_count}</span>
    <span class="summary-pill">decided: ${run.decided_item_count}</span>
    <span class="summary-pill">${escapeHtml(autoFixText)}</span>
    <span class="summary-pill">static: ${run.static_issue_count}</span>
    <span class="summary-pill">consistency: ${run.consistency_issue_count}</span>
    <span class="summary-pill">model: ${run.model_flagged_rows}</span>
  `;
}

function agentStateLabel(value) {
  const labels = {
    BLOCKED: "验收不通过",
    HUMAN_REVIEWING: "待人工抽查",
    READY_TO_EXPORT: "可直接导出",
    AUDIT_DONE: "审计完成",
  };
  return labels[value] || value || "未选择 run";
}

function renderAgentAnalysis() {
  if (!els.agentStateBadge) return;
  const analysis = state.currentAgentAnalysis;
  if (!analysis) {
    els.agentStateBadge.textContent = "未选择 run";
    els.agentStateBadge.className = "agent-state-badge";
    els.agentHeadline.textContent = "选择 run 后生成分析。";
    els.agentMetrics.innerHTML = "";
    els.agentFindings.className = "agent-list empty-state";
    els.agentFindings.textContent = "暂无";
    els.agentPlan.className = "agent-list empty-state";
    els.agentPlan.textContent = "暂无";
    els.agentActions.className = "agent-list empty-state";
    els.agentActions.textContent = "暂无";
    return;
  }

  els.agentStateBadge.textContent = agentStateLabel(analysis.lifecycle_state);
  els.agentStateBadge.className = `agent-state-badge ${String(analysis.lifecycle_state || "").toLowerCase()}`;
  els.agentHeadline.textContent = analysis.headline || "Agent 已完成当前 run 分析。";

  const metrics = analysis.metrics || {};
  const decisionTypes = analysis.decision_type_counts || {};
  const decisionActions = analysis.decision_counts || {};
  const queueMetricLabel =
    analysis.lifecycle_state === "READY_TO_EXPORT" && (analysis.acceptance?.verdict || "") === "通过"
      ? "可选抽查"
      : "待抽查";
  const metricItems = [
    ["风险样本", metrics.risk_items],
    [queueMetricLabel, metrics.undecided_items],
    ["已抽查", metrics.decided_items],
    ["自动修复", metrics.auto_fix_changed_rows],
    ["已改标", decisionTypes.label_corrected || decisionActions.replace_label || 0],
    ["静态问题", metrics.static_issue_count],
    ["一致性问题", metrics.consistency_issue_count],
    ["模型标记", metrics.model_flagged_rows],
  ];
  els.agentMetrics.innerHTML = metricItems
    .map(([label, value]) => `<span class="agent-metric"><strong>${escapeHtml(value ?? 0)}</strong>${escapeHtml(label)}</span>`)
    .join("");

  const findings = [
    ...((analysis.priority_findings?.p0 || []).map((text) => ({ level: "P0", text }))),
    ...((analysis.priority_findings?.p1 || []).map((text) => ({ level: "P1", text }))),
  ];
  renderAgentFindings(findings);
  renderAgentPlan(analysis.review_plan || []);
  renderAutoFixSummary(currentRun(), analysis);
  const acceptanceActions = [
    ...(analysis.next_actions || []),
    { action: "acceptance_report", label: "生成验收报告", detail: "生成中文 .md 报告，说明是否建议训练以及需要继续处理的问题。" },
  ].sort((a, b) => {
    const weight = (item) => {
      if (item.action === "export") return 0;
      if (item.action === "acceptance_report") return 1;
      if (item.action === "spot_check") return 2;
      return 9;
    };
    return weight(a) - weight(b);
  });
  renderAgentActions(acceptanceActions);
}

function renderAgentFindings(items) {
  els.agentFindings.innerHTML = "";
  if (!items.length) {
    els.agentFindings.className = "agent-list empty-state";
    els.agentFindings.textContent =
      state.currentAgentAnalysis?.lifecycle_state === "READY_TO_EXPORT"
        ? "当前没有阻塞项，已经可以导出 cleaned dataset。"
        : "暂无明确阻塞项，按抽查计划推进即可。";
    return;
  }
  els.agentFindings.className = "agent-list";
  for (const item of items) {
    const div = document.createElement("div");
    div.className = `agent-list-item ${item.level.toLowerCase()}`;
    div.innerHTML = `<span class="agent-level">${escapeHtml(item.level)}</span><span>${escapeHtml(item.text)}</span>`;
    els.agentFindings.appendChild(div);
  }
}

function renderAgentPlan(plans) {
  els.agentPlan.innerHTML = "";
  if (!plans.length) {
    els.agentPlan.className = "agent-list empty-state";
    els.agentPlan.textContent = "暂无计划";
    return;
  }
  els.agentPlan.className = "agent-list";
  for (const plan of plans) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "agent-plan-item";
    button.innerHTML = `
      <span class="agent-plan-title">${escapeHtml(plan.title)}</span>
      <span class="agent-plan-meta">建议查看 ${escapeHtml(plan.target_count ?? 0)} 条</span>
      <span class="agent-plan-reason">${escapeHtml(plan.reason || "")}</span>
    `;
    button.onclick = () => startReviewQueue(plan);
    els.agentPlan.appendChild(button);
  }
}

function renderAgentActions(actions) {
  els.agentActions.innerHTML = "";
  if (!actions.length) {
    els.agentActions.className = "agent-list empty-state";
    els.agentActions.textContent = "暂无动作";
    return;
  }
  els.agentActions.className = "agent-list";
  for (const action of actions) {
    const button = document.createElement("button");
    button.type = "button";
    const primary = ["export", "acceptance_report"].includes(action.action) && state.currentAgentAnalysis?.lifecycle_state === "READY_TO_EXPORT";
    button.className = `agent-action-item${primary ? " primary-action" : ""}`;
    button.innerHTML = `<strong>${escapeHtml(action.label || action.action)}</strong><span>${escapeHtml(action.detail || "")}</span>`;
    button.onclick = () => runAgentAction(action);
    els.agentActions.appendChild(button);
  }
}

async function applyAgentFilter(filter, options = {}) {
  if (!filter) return;
  if (options.queueTitle) {
    els.riskBucketFilter.value = "";
    els.decisionStatusFilter.value = "";
    els.splitFilter.value = "";
    els.actionFilter.value = "";
    els.issueSourceFilter.value = "";
    els.searchInput.value = "";
  }
  state.activeQueue = options.queueTitle ? { title: options.queueTitle, filter: { ...filter } } : state.activeQueue;
  if (Object.prototype.hasOwnProperty.call(filter, "risk_bucket")) {
    els.riskBucketFilter.value = filter.risk_bucket || "";
  }
  if (Object.prototype.hasOwnProperty.call(filter, "decision_status")) {
    els.decisionStatusFilter.value = filter.decision_status || "";
  }
  if (Object.prototype.hasOwnProperty.call(filter, "issue_source")) {
    els.issueSourceFilter.value = filter.issue_source || "";
  }
  if (Object.prototype.hasOwnProperty.call(filter, "q")) {
    els.searchInput.value = filter.q || "";
  }
  await applyFilters({ keepQueue: Boolean(options.queueTitle) });
}

async function startReviewQueue(plan) {
  if (!plan) return;
  setStatus(`已进入复核队列：${plan.title}`);
  await applyAgentFilter(plan.filter || {}, { queueTitle: plan.title || "Agent 推荐队列" });
}

function firstReviewPlan(predicate = () => true) {
  const plans = state.currentAgentAnalysis?.review_plan || [];
  return plans.find(predicate) || plans[0] || null;
}

async function runAgentAction(action) {
  const actionName = action?.action || "";
  if (actionName === "acceptance_report") {
    await generateAcceptanceReport();
    return;
  }
  if (actionName === "export") {
    await exportCleaned();
    if (els.exportPanel) els.exportPanel.open = true;
    return;
  }
  if (actionName === "compare") {
    if (els.reportsPanel) els.reportsPanel.open = true;
    await refreshReports();
    return;
  }
  if (actionName === "fix_blocker") {
    const plan = firstReviewPlan((item) => String(item.title || "").includes("静态问题专项"));
    if (plan) {
      await startReviewQueue(plan);
      return;
    }
  }
  const plan = firstReviewPlan();
  if (plan) await startReviewQueue(plan);
}

async function generateAcceptanceReport() {
  if (!state.currentRunId) return;
  try {
    const result = await api(`/api/runs/${state.currentRunId}/acceptance-report`, { method: "POST" });
    if (els.exportPanel) els.exportPanel.open = true;
    els.exportSummary.innerHTML = `
      ${pathDisplayHtml("验收报告", result.path, { keepSegments: 4, copyLabel: "复制路径" })}
      <div><strong>验收结论：</strong>${escapeHtml(result.analysis?.acceptance?.verdict || "-")}</div>
      <div><strong>是否建议训练：</strong>${result.analysis?.acceptance?.train_ready ? "是" : "否"}</div>
      <div><strong>说明：</strong>${escapeHtml(result.analysis?.acceptance?.reason || "")}</div>
    `;
    showToast("验收报告已生成");
  } catch (error) {
    alert(`生成验收报告失败：${error.message}`);
  }
}

async function loadRuns() {
  const data = await api("/api/runs");
  state.runs = data.items || [];
  renderRuns();
  renderRunSummary(currentRun());
  renderAutoFixSummary(currentRun(), state.currentAgentAnalysis);
  renderAutoFixRecords();
}

async function loadTasks() {
  const data = await api("/api/tasks");
  state.tasks = data.items || [];
  renderTasks();
}

async function loadRunReports(runId) {
  state.currentRunReports = await api(`/api/runs/${runId}/reports`);
  renderCurrentReport();
}

async function loadAgentAnalysis(runId) {
  state.currentAgentAnalysis = await api(`/api/runs/${runId}/agent-analysis`);
  renderAgentAnalysis();
}

async function loadAutoFixRecords(runId) {
  state.currentAutoFixRecords = await api(`/api/runs/${runId}/auto-fix-records`);
  renderAutoFixRecords();
}

async function loadTaskLog(taskId) {
  const data = await api(`/api/tasks/${taskId}/log`);
  state.currentTaskLog = data.content || "";
  const task = currentTask();
  els.selectedTaskTitle.textContent = task ? `${task.run_name} (${task.status})` : "";
  els.taskLogViewer.textContent = state.currentTaskLog || "当前任务还没有日志。";
  updateSelectedTaskActions();
}

async function selectRun(runId) {
  state.currentRunId = runId;
  state.activeQueue = null;
  state.pagination.page = 1;
  renderRuns();
  const run = currentRun();
  renderRunSummary(run);
  renderAutoFixSummary(run, state.currentAgentAnalysis);
  renderAutoFixRecords();
  if (run) {
    els.exportCleanedBtn.disabled = false;
    els.startAuditBtn.disabled = false;
  }
  await loadRunReports(runId);
  await loadAgentAnalysis(runId);
  await loadAutoFixRecords(runId);
  await loadItems();
}

function syncFiltersFromUI() {
  state.filters.riskBucket = els.riskBucketFilter.value;
  state.filters.decisionStatus = els.decisionStatusFilter.value;
  state.filters.split = els.splitFilter.value;
  state.filters.action = els.actionFilter.value;
  state.filters.issueSource = els.issueSourceFilter.value;
  state.filters.q = els.searchInput.value.trim();
}

async function loadItems(preferredItemId = null) {
  if (!state.currentRunId) return;

  const params = new URLSearchParams();
  if (state.filters.riskBucket) params.set("risk_bucket", state.filters.riskBucket);
  if (state.filters.decisionStatus) params.set("decision_status", state.filters.decisionStatus);
  if (state.filters.split) params.set("split", state.filters.split);
  if (state.filters.action) params.set("action", state.filters.action);
  if (state.filters.issueSource) params.set("issue_source", state.filters.issueSource);
  if (state.filters.owner) params.set("owner", state.filters.owner);
  if (state.filters.q) params.set("q", state.filters.q);
  params.set("limit", String(state.pagination.limit));
  params.set("offset", String((state.pagination.page - 1) * state.pagination.limit));

  const data = await api(`/api/runs/${state.currentRunId}/items?${params.toString()}`);
  state.items = data.items || [];
  state.pagination.total = data.total || 0;
  renderItems();

  const candidateId = preferredItemId && state.items.some((item) => item.id === preferredItemId)
    ? preferredItemId
    : state.items[0]?.id || null;

  if (candidateId) {
    await selectItem(candidateId);
  } else {
    clearDetail();
  }
}

async function selectItem(itemId) {
  const data = await api(`/api/items/${itemId}`);
  renderDetail(data);
  renderItems();
}

async function submitIntake() {
  const path = els.intakePathInput.value.trim();
  const datasetName = els.intakeDatasetNameInput.value.trim();
  const runName = els.intakeRunNameInput.value.trim();
  if (!path) {
    setStatus("请先输入目录路径", true);
    return;
  }
  setStatus("平台正在识别目录类型...");
  try {
    const result = await api("/api/intake", {
      method: "POST",
      body: JSON.stringify({
        path,
        dataset_name: datasetName || undefined,
        run_name: runName || undefined,
      }),
    });
    els.intakePathInput.value = "";
    els.intakeDatasetNameInput.value = "";
    els.intakeRunNameInput.value = "";
    if (result.mode === "imported_run") {
      const remoteHint = String(result.path_kind || "").startsWith("server_") ? "服务器" : "本地";
      setStatus(`已识别为${remoteHint} audit run，导入完成：${result.run.run_name}`);
      await loadRuns();
      await loadTasks();
      await selectRun(result.run.run_id);
      return;
    }
    const remoteHint = String(result.path_kind || "").startsWith("server_") ? "服务器" : "本地";
    setStatus(`已识别为${remoteHint}原始数据集，审计任务已发起：${result.task.run_name}`);
    state.currentTaskId = result.task.id;
    await loadTasks();
    clearRunContextForPendingTask(result.task);
    await loadTaskLog(result.task.id);
  } catch (error) {
    setStatus(`接入失败：${error.message}`, true);
  }
}

function nextItemCandidateAfterSave() {
  if (!state.currentItemId || !state.items.length) return null;
  const currentIndex = state.items.findIndex((item) => item.id === state.currentItemId);
  if (currentIndex < 0) return null;
  if (state.filters.decisionStatus === "undecided") {
    return state.items[currentIndex + 1]?.id || state.items[currentIndex - 1]?.id || null;
  }
  return state.items[currentIndex + 1]?.id || state.items[currentIndex]?.id || state.items[currentIndex - 1]?.id || null;
}

async function saveDecision() {
  if (!state.currentItemId) return;
  const nextCandidateId = nextItemCandidateAfterSave();
  const payload = {
    decision: els.decisionInput.value,
    action: els.actionInput.value,
    corrected_label_json: els.actionInput.value === "replace_label" ? buildCorrectedLabelFromForm() : null,
    owner: els.ownerInput.value.trim(),
    notes: els.notesInput.value.trim(),
  };
  try {
    await api(`/api/items/${state.currentItemId}/decision`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setStatus("保存成功");
    showToast("保存成功");
    await loadRuns();
    if (state.currentRunId) {
      await loadAgentAnalysis(state.currentRunId);
    }
    await loadItems(nextCandidateId);
  } catch (error) {
    alert(`保存失败：${error.message}`);
  }
}

async function markAcceptance(decision, action, note) {
  if (!state.currentItemId) return;
  els.decisionInput.value = decision;
  els.actionInput.value = action;
  if (note && !els.notesInput.value.trim()) {
    els.notesInput.value = note;
  }
  await saveDecision();
}

async function saveLabelCorrection() {
  if (!state.currentItemId) return;
  els.decisionInput.value = "label_corrected";
  els.actionInput.value = "replace_label";
  if (!els.notesInput.value.trim()) {
    els.notesInput.value = "人工修正标签后通过";
  }
  await saveDecision();
}

async function exportCleaned() {
  if (!state.currentRunId) return;
  try {
    const result = await api(`/api/runs/${state.currentRunId}/export-cleaned`, {
      method: "POST",
      body: JSON.stringify({ export_name: "" }),
    });
    state.lastExportSummary = result;
    els.reauditExportBtn.disabled = false;
    els.exportSummary.innerHTML = `
      <div><strong>导出目录：</strong><code>${escapeHtml(result.cleaned_dataset_dir)}</code></div>
      <div><strong>标签修改：</strong>${result.label_change_count} 条</div>
      <div><strong>删除样本：</strong>${result.dropped_count} 条</div>
      <div><strong>决策统计：</strong>keep=${result.decision_counts.keep}, replace=${result.decision_counts.replace_label}, drop=${result.decision_counts.drop}, hold=${result.decision_counts.hold}</div>
    `;
  } catch (error) {
    alert(`导出失败：${error.message}`);
  }
}

async function startAudit(datasetDir, datasetName, runName) {
  if (!state.currentRunId) return;
  try {
    const isRemote = String(datasetDir || "").trim().startsWith("/");
    setStatus(`已发起${isRemote ? "服务器" : "本地"}审计任务`);
    const task = await api(`/api/runs/${state.currentRunId}/start-audit`, {
      method: "POST",
      body: JSON.stringify({
        dataset_dir: datasetDir,
        dataset_name: datasetName,
        run_name: runName,
        execution_mode: isRemote ? "server" : "auto",
      }),
    });
    state.currentTaskId = task.id;
    await loadTasks();
    clearRunContextForPendingTask(task);
    await loadTaskLog(task.id);
  } catch (error) {
    alert(`发起审计失败：${error.message}`);
  }
}

async function startCurrentAudit() {
  const run = currentRun();
  if (!run) return;
  await startAudit(run.dataset_dir, run.dataset_name, `${run.dataset_name}_audit_${Date.now()}`);
}

async function reauditExportedDataset() {
  const run = currentRun();
  if (!run || !state.lastExportSummary) return;
  await startAudit(
    state.lastExportSummary.cleaned_dataset_dir,
    `${run.dataset_name}_cleaned`,
    `${run.dataset_name}_cleaned_audit_${Date.now()}`
  );
}

async function refreshReports() {
  if (!state.currentRunId) return;
  await loadRunReports(state.currentRunId);
}

async function refreshAgent() {
  if (!state.currentRunId) return;
  await loadAgentAnalysis(state.currentRunId);
}

async function maybeRefreshCompletedTask() {
  const task = currentTask();
  if (!task) return;
  const freshTask = await api(`/api/tasks/${task.id}`);
  const previousStatus = task.status;
  state.tasks = state.tasks.map((item) => (item.id === freshTask.id ? freshTask : item));
  renderTasks();
  if (state.currentTaskId === freshTask.id) {
    await loadTaskLog(freshTask.id);
    if (!freshTask.result_run_id) {
      clearRunContextForPendingTask(freshTask);
    }
  }
  if (freshTask.status === "completed" && previousStatus !== "completed") {
    await loadRuns();
    if (freshTask.result_run_id) {
      await selectRun(freshTask.result_run_id);
    }
  }
}

async function resumeCurrentTask() {
  const task = currentTask();
  if (!task || !task.can_resume) return;
  await resumeTaskById(task.id);
}

async function stopCurrentTask() {
  const task = currentTask();
  if (!task || !(task.status === "running" || task.status === "pending")) return;
  await stopTaskById(task.id);
}


async function resumeTaskById(taskId) {
  const task = state.tasks.find((item) => item.id === taskId);
  if (!task || !task.can_resume) return;
  try {
    setStatus(`已发起续跑任务：${task.run_name}`);
    const freshTask = await api(`/api/tasks/${task.id}/resume`, { method: "POST" });
    state.currentTaskId = freshTask.id;
    await loadTasks();
    clearRunContextForPendingTask(freshTask);
    await loadTaskLog(freshTask.id);
  } catch (error) {
    alert(`续跑失败：${error.message}`);
  }
}


async function stopTaskById(taskId) {
  const task = state.tasks.find((item) => item.id === taskId);
  if (!task || !(task.status === "running" || task.status === "pending")) return;
  try {
    setStatus(`已停止任务：${task.run_name}`);
    const freshTask = await api(`/api/tasks/${task.id}/stop`, { method: "POST" });
    state.currentTaskId = freshTask.id;
    await loadTasks();
    clearRunContextForPendingTask(freshTask);
    await loadTaskLog(freshTask.id);
  } catch (error) {
    alert(`停止失败：${error.message}`);
  }
}

async function applyFilters(options = {}) {
  syncFiltersFromUI();
  if (!options.keepQueue) state.activeQueue = null;
  state.pagination.page = 1;
  await loadItems();
}

async function goPrevPage() {
  if (state.pagination.page <= 1) return;
  state.pagination.page -= 1;
  await loadItems();
}

async function goNextPage() {
  const totalPages = Math.max(1, Math.ceil(state.pagination.total / state.pagination.limit));
  if (state.pagination.page >= totalPages) return;
  state.pagination.page += 1;
  await loadItems();
}

async function selectRelativeQueueItem(direction) {
  if (!state.currentRunId) return;
  const currentIndex = state.items.findIndex((item) => item.id === state.currentItemId);
  if (direction > 0) {
    const next = state.items[currentIndex + 1];
    if (next) {
      await selectItem(next.id);
      return;
    }
    const totalPages = Math.max(1, Math.ceil(state.pagination.total / state.pagination.limit));
    if (state.pagination.page < totalPages) {
      state.pagination.page += 1;
      await loadItems();
    }
    return;
  }
  const prev = state.items[currentIndex - 1];
  if (prev) {
    await selectItem(prev.id);
    return;
  }
  if (state.pagination.page > 1) {
    state.pagination.page -= 1;
    await loadItems();
    const last = state.items[state.items.length - 1];
    if (last) await selectItem(last.id);
  }
}

async function exitQueue() {
  state.activeQueue = null;
  renderQueueStatus();
  setStatus("已退出复核队列");
}

function bindEvents() {
  els.intakeSubmitBtn.addEventListener("click", submitIntake);
  els.refreshRunsBtn.addEventListener("click", loadRuns);
  els.refreshTasksBtn.addEventListener("click", loadTasks);
  els.startAuditBtn.addEventListener("click", startCurrentAudit);
  els.reauditExportBtn.addEventListener("click", reauditExportedDataset);
  els.refreshReportsBtn.addEventListener("click", refreshReports);
  if (els.refreshAgentBtn) {
    els.refreshAgentBtn.addEventListener("click", refreshAgent);
  }
  els.showAuditReportBtn.addEventListener("click", () => {
    state.currentReportType = "audit";
    renderCurrentReport();
  });
  els.showLlmReportBtn.addEventListener("click", () => {
    state.currentReportType = "llm";
    renderCurrentReport();
  });
  els.showTaskLogBtn.addEventListener("click", async () => {
    if (state.currentTaskId) {
      await loadTaskLog(state.currentTaskId);
    }
  });
  if (els.resumeTaskBtn) {
    els.resumeTaskBtn.addEventListener("click", resumeCurrentTask);
  }
  if (els.stopTaskBtn) {
    els.stopTaskBtn.addEventListener("click", stopCurrentTask);
  }

  els.applyFiltersBtn.addEventListener("click", applyFilters);
  els.prevPageBtn.addEventListener("click", goPrevPage);
  els.nextPageBtn.addEventListener("click", goNextPage);
  if (els.queuePrevBtn) {
    els.queuePrevBtn.addEventListener("click", () => selectRelativeQueueItem(-1));
  }
  if (els.queueNextBtn) {
    els.queueNextBtn.addEventListener("click", () => selectRelativeQueueItem(1));
  }
  if (els.queueExitBtn) {
    els.queueExitBtn.addEventListener("click", exitQueue);
  }
  [els.searchInput, els.intakePathInput, els.intakeDatasetNameInput, els.intakeRunNameInput]
    .filter(Boolean)
    .forEach((element) => {
      element.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        if (
          element === els.intakePathInput ||
          element === els.intakeDatasetNameInput ||
        element === els.intakeRunNameInput
      ) {
        submitIntake();
      } else {
        applyFilters();
      }
    });
    });

  els.fillGoldBtn.addEventListener("click", () => fillFormFromLabel(state.currentItem?.label_json));
  els.fillPredBtn.addEventListener("click", () => fillFormFromLabel(state.currentItem?.model_prediction_json || state.currentItem?.label_json));
  els.saveDecisionBtn.addEventListener("click", saveDecision);
  els.actionInput.addEventListener("change", () => {
    if (els.actionInput.value === "replace_label") {
      openLabelEditor(false);
    }
  });
  if (els.markPassBtn) {
    els.markPassBtn.addEventListener("click", () => markAcceptance("acceptance_pass", "keep", "人工抽查通过"));
  }
  if (els.openLabelEditorBtn) {
    els.openLabelEditorBtn.addEventListener("click", () => openLabelEditor(true));
  }
  if (els.saveLabelCorrectionBtn) {
    els.saveLabelCorrectionBtn.addEventListener("click", saveLabelCorrection);
  }
  if (els.generateAcceptanceReportBtn) {
    els.generateAcceptanceReportBtn.addEventListener("click", generateAcceptanceReport);
  }
  els.exportCleanedBtn.addEventListener("click", exportCleaned);
  els.openImageBtn.addEventListener("click", openImageModal);
  els.detailImage.addEventListener("click", openImageModal);
  els.cleanViewToggle.addEventListener("change", async () => {
    state.imageDisplay.preferRaw = els.cleanViewToggle.checked;
    if (state.currentItem) {
      await updateDisplayedImage(state.currentItem);
    }
  });
  els.closeImageModalBtn.addEventListener("click", closeImageModal);
  els.imageModal.querySelector(".image-modal-backdrop").addEventListener("click", closeImageModal);

  [
    els.statusInput,
    els.skipReasonInput,
    els.l2PrimaryInput,
    els.customerCountInput,
    els.groupGenderInput,
    els.containsChildInput,
    els.childAgeBucketInput,
    els.containsElderInput,
    els.youngGroupInput,
    els.reasoningInput,
    els.confidenceInput,
  ].forEach((element) => element.addEventListener("input", updatePreview));
}

async function boot() {
  bindEvents();
  updatePreview();
  clearDetail();
  updateReportTabState();
  renderAgentAnalysis();
  await loadRuns();
  await loadTasks();
  if (state.runs.length > 0) {
    await selectRun(state.runs[0].id);
  } else {
    renderRunSummary(null);
  }
  setInterval(() => {
    loadTasks().then(maybeRefreshCompletedTask).catch(() => {});
  }, 5000);
}

boot();
