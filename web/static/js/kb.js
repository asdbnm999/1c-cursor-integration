function apiAuthHeaders() {
  const headers = {};
  const token = sessionStorage.getItem("kb_api_token");
  if (token) headers.Authorization = "Bearer " + token;
  return headers;
}

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...apiAuthHeaders(),
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function el(id) {
  return document.getElementById(id);
}

async function refreshKbDockerBadge() {
  const badge = el("docker-badge");
  if (!badge) return;
  try {
    const s = await api("/kb/api/system");
    badge.textContent = s.docker_available ? "Docker OK" : "Docker недоступен";
    badge.className = "badge " + (s.docker_available ? "ok" : "err");
  } catch {
    badge.textContent = "Docker ?";
    badge.className = "badge err";
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderProfileCard(p) {
  const wf = p.workflow || {};
  const allDone = Boolean(wf.all_complete);
  const cardClass = allDone ? "card card--success" : "card";
  const job = p.index_job?.status === "running" ? " · индексация…" : "";
  const progress = wf.total_count
    ? `<span class="card-badge${allDone ? " success" : ""}">${allDone ? "Готов ✓" : `${wf.completed_count || 0}/${wf.total_count}`}</span>`
    : "";
  const dotClass = allDone ? "on" : p.docker?.running ? "on" : "off";
  return `
    <a class="${cardClass}" href="/kb/profile/${p.name}">
      <div class="card-top">
        <h3>${escapeHtml(p.display_name)}</h3>
        ${progress}
      </div>
      <div class="meta">
        <span class="status-dot ${dotClass}"></span>${p.format} · ${p.chunks} чанков · ${p.files} файлов${job}
      </div>
    </a>`;
}

function updateWorkflowGates(p) {
  const gates = p?.gates || {};
  const dockerEnabled = Boolean(gates.docker_enabled);
  const mcpEnabled = Boolean(gates.mcp_enabled);
  window.__profileGates = { docker_enabled: dockerEnabled, mcp_enabled: mcpEnabled };

  const dockerHint = el("docker-gate-hint");
  if (dockerHint) {
    dockerHint.classList.toggle("hidden", dockerEnabled);
    if (!dockerEnabled) {
      dockerHint.textContent =
        "Сначала выполните полную индексацию — Docker станет доступен после появления чанков в индексе.";
    }
  }

  const mcpHint = el("mcp-gate-hint");
  if (mcpHint) {
    mcpHint.classList.toggle("hidden", mcpEnabled);
    if (!mcpEnabled) {
      mcpHint.textContent =
        "Сначала соберите образ и запустите контейнер — подключение MCP доступно только после создания контейнера.";
    }
  }

  el("section-docker")?.classList.toggle("step--locked", !dockerEnabled);
  el("section-cursor")?.classList.toggle("step--locked", !mcpEnabled);

  [
    "btn-mcp-apply",
    "btn-cursor-check-auto",
    "btn-mcp-download",
    "btn-cursor-check",
    "btn-mcp-copy",
    "btn-cursor-pick-dir",
  ].forEach((id) => {
    const btn = el(id);
    if (btn) btn.disabled = !mcpEnabled;
  });
  const mcpToggle = el("mcp-mode-toggle");
  if (mcpToggle) mcpToggle.disabled = !mcpEnabled;
  const mcpFile = el("mcp-file");
  if (mcpFile) {
    mcpFile.disabled = !mcpEnabled;
    mcpFile.closest("label")?.classList.toggle("btn--disabled", !mcpEnabled);
  }
  loadCursorDirSettings().catch(() => {});
}

function setStepState(stepId, state, badgeText) {
  const panel = el(`section-${stepId}`);
  const badge = el(`badge-${stepId}`);
  if (!panel) return;
  panel.classList.remove("step--active", "step--success", "step--error");
  if (badge) {
    badge.classList.remove("active", "success", "error");
  }
  if (state === "active") {
    panel.classList.add("step--active");
    badge?.classList.add("active");
  } else if (state === "success") {
    panel.classList.add("step--success");
    badge?.classList.add("success");
  } else if (state === "error") {
    panel.classList.add("step--error");
    badge?.classList.add("error");
  }
  if (badge && badgeText) badge.textContent = badgeText;
}

async function loadProfiles() {
  const list = el("profiles-list");
  const profiles = await api("/kb/api/profiles");
  if (!profiles.length) {
    list.innerHTML = '<p class="hint">Профилей нет. Создайте первый.</p>';
    return;
  }
  list.innerHTML = profiles.map(renderProfileCard).join("");
}

function initDashboard() {
  refreshKbDockerBadge();
  loadProfiles().catch((e) => {
    el("profiles-list").textContent = "Ошибка: " + e.message;
  });

  const dialog = el("dialog-new-profile");
  const form = el("form-new-profile");
  el("btn-new-profile")?.addEventListener("click", () => {
    if (!dialog) return;
    dialog.showModal();
    requestAnimationFrame(() => syncFormatFields());
  });
  dialog?.querySelectorAll("[data-close]").forEach((b) =>
    b.addEventListener("click", () => dialog.close())
  );

  const formatSelect = form?.querySelector('[name="format"]');
  const labelSrc = el("label-src");

  function syncFormatFields() {
    const isEdt = formatSelect?.value === "edt";
    labelSrc?.classList.toggle("hidden", !isEdt);
  }

  formatSelect?.addEventListener("change", syncFormatFields);
  dialog?.addEventListener("close", () => {
    if (formatSelect) formatSelect.value = "edt";
    syncFormatFields();
  });
  syncFormatFields();

  el("btn-pick-root")?.addEventListener("click", async () => {
    const btn = el("btn-pick-root");
    const input = el("input-root");
    const fmt = form?.querySelector('[name="format"]')?.value || "edt";
    const title =
      fmt === "edt"
        ? "Выберите корень EDT-проекта (папка с src/)"
        : "Выберите каталог XML-выгрузки конфигурации";
    btn.disabled = true;
    btn.textContent = "Ожидание…";
    try {
      const r = await api("/kb/api/pick-directory", {
        method: "POST",
        body: JSON.stringify({ title }),
      });
      if (r.cancelled) return;
      if (r.path) input.value = r.path;
    } catch (e) {
      alert("Не удалось выбрать папку: " + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Выбрать…";
    }
  });

  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = el("form-error");
    err.classList.add("hidden");
    const fd = new FormData(form);
    const root = fd.get("root");
    try {
      const includeForms = Boolean(el("dialog-include-forms")?.checked);
      const preview = await api("/kb/api/wizard/preview", {
        method: "POST",
        body: JSON.stringify({ root, include_forms: includeForms }),
      });
      if (!confirm(`Формат: ${preview.detected_format}. Оценка: ${preview.estimate.human}. Создать профиль?`)) return;
      const res = await api("/kb/api/profiles", {
        method: "POST",
        body: JSON.stringify({
          name: fd.get("name"),
          display_name: fd.get("display_name"),
          format: preview.detected_format || fd.get("format"),
          root: root,
          src: fd.get("format") === "edt" ? fd.get("src") : "",
          docs_enabled: fd.get("docs_enabled") === "on",
          include_forms: includeForms,
        }),
      });
      dialog.close();
      location.href = "/kb/profile/" + res.profile;
    } catch (ex) {
      err.textContent = ex.message;
      err.classList.remove("hidden");
    }
  });

  initWizard();

  const dialogImport = el("dialog-import-index");
  el("btn-open-import")?.addEventListener("click", () => dialogImport?.showModal());
  dialogImport?.querySelectorAll("[data-close-import]").forEach((b) =>
    b.addEventListener("click", () => dialogImport.close())
  );

  el("import-file")?.addEventListener("change", () => {
    const file = el("import-file").files?.[0];
    const text = el("import-file-text");
    if (!text) return;
    if (file) {
      text.textContent = file.name;
      text.classList.add("is-selected");
    } else {
      text.textContent = "Выбрать файл…";
      text.classList.remove("is-selected");
    }
  });

  el("form-import-index")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = el("import-file").files?.[0];
    if (!file) return alert("Выберите файл");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("target_profile", el("import-target").value);
    fd.append("overwrite", el("import-overwrite").checked ? "1" : "");
    const res = await fetch("/kb/api/profiles/import", {
      method: "POST",
      body: fd,
      headers: apiAuthHeaders(),
    });
    const data = await res.json();
    if (!res.ok) return alert(data.error);
    location.href = "/kb/profile/" + data.profile;
  });

  loadHealthSummary();
}

async function loadHealthSummary() {
  const box = el("health-summary");
  const table = el("health-system-table");
  const tbody = el("health-system-body");
  if (!box) return;
  try {
    const h = await api("/kb/api/health");
    const issues = (h.profiles || []).filter((p) => !p.healthy).length;
    box.className = "runtime-line" + (issues ? "" : " ok");
    box.textContent = `Docker: ${h.docker_available ? "OK" : "нет"} · профилей: ${h.profiles_count} · с проблемами: ${issues}`;
    if (table && tbody && h.profiles?.length) {
      table.classList.remove("hidden");
      tbody.innerHTML = h.profiles
        .map(
          (p) =>
            `<tr><td>${escapeHtml(p.name)}</td><td class="${p.healthy ? "ok" : "fail"}">${
              p.healthy ? "ready" : "degraded"
            }</td><td>${p.issues_count ?? p.error ?? 0}</td></tr>`
        )
        .join("");
    }
  } catch (e) {
    box.textContent = "Health: " + e.message;
  }
}

function initWizard() {
  showWizardStep(1);

  el("btn-wizard-pick")?.addEventListener("click", async () => {
    try {
      const r = await api("/kb/api/pick-directory", {
        method: "POST",
        body: JSON.stringify({ title: "Каталог для мастера onboarding" }),
      });
      if (r.path) el("wizard-root").value = r.path;
    } catch (e) {
      alert(e.message);
    }
  });

  el("btn-wizard-next-1")?.addEventListener("click", async () => {
    const root = el("wizard-root")?.value?.trim();
    if (!root) return alert("Укажите путь");
    showWizardStep(2);
    const summary = el("wizard-preview-summary");
    const pre = el("wizard-result");
    summary.textContent = "Анализ…";
    pre?.classList.add("hidden");
    try {
      const r = await api("/kb/api/wizard/preview", {
        method: "POST",
        body: JSON.stringify({ root, include_forms: false }),
      });
      WIZARD_STATE.preview = r;
      summary.textContent = `${r.detected_format} · файлов ~${r.preview.total_indexable} · оценка ${r.estimate.human}`;
      if (pre) {
        pre.classList.remove("hidden");
        pre.textContent = JSON.stringify(r.preview, null, 2);
      }
    } catch (e) {
      summary.textContent = e.message;
      showWizardStep(1);
    }
  });

  el("btn-wizard-back-2")?.addEventListener("click", () => showWizardStep(1));
  el("btn-wizard-next-2")?.addEventListener("click", () => {
    if (!WIZARD_STATE.preview) return alert("Сначала выполните анализ");
    showWizardStep(3);
  });
  el("btn-wizard-back-3")?.addEventListener("click", () => showWizardStep(2));
  el("wizard-emb-provider")?.addEventListener("change", () => {
    const openai = el("wizard-emb-provider")?.value === "openai";
    el("wizard-openai-hint")?.classList.toggle("hidden", !openai);
    if (el("wizard-emb-device")) {
      el("wizard-emb-device").disabled = openai;
    }
  });

  el("btn-wizard-check-embeddings")?.addEventListener("click", async () => {
    const line = el("wizard-emb-check-result");
    if (!line) return;
    line.textContent = "Проверка…";
    try {
      const r = await api("/kb/api/wizard/embeddings/check", {
        method: "POST",
        body: JSON.stringify({
          provider: el("wizard-emb-provider")?.value || "local",
          device: el("wizard-emb-device")?.value || "auto",
        }),
      });
      line.className = "runtime-line " + (r.ok ? "ok" : "");
      line.textContent = r.message || (r.ok ? "OK" : "Ошибка");
    } catch (e) {
      line.className = "runtime-line";
      line.textContent = e.message;
    }
  });

  el("btn-wizard-next-3")?.addEventListener("click", () => showWizardStep(4));

  el("btn-wizard-back-4")?.addEventListener("click", () => showWizardStep(3));
  el("btn-wizard-create")?.addEventListener("click", async () => {
    const err = el("wizard-create-error");
    err?.classList.add("hidden");
    const name = el("wizard-profile-name")?.value?.trim();
    const root = el("wizard-root")?.value?.trim();
    if (!name || !root || !WIZARD_STATE.preview) return alert("Заполните имя и путь");
    try {
      const res = await api("/kb/api/profiles", {
        method: "POST",
        body: JSON.stringify({
          name,
          display_name: el("wizard-display-name")?.value?.trim() || name,
          format: WIZARD_STATE.preview.detected_format,
          root,
          src: WIZARD_STATE.preview.detected_format === "edt" ? "src" : "",
          docs_enabled: el("wizard-docs")?.checked,
          include_forms: el("wizard-include-forms")?.checked,
        }),
      });
      WIZARD_STATE.profileName = res.profile;
      const provider = el("wizard-emb-provider")?.value || "local";
      const device = el("wizard-emb-device")?.value || "auto";
      await api("/kb/api/profiles/" + res.profile + "/embeddings", {
        method: "PUT",
        body: JSON.stringify({ provider, device }),
      });
      el("wizard-done-msg").textContent = `Профиль «${res.profile}» создан`;
      el("wizard-open-profile").href = "/kb/profile/" + res.profile;
      showWizardStep(5);
    } catch (e) {
      if (err) {
        err.textContent = e.message;
        err.classList.remove("hidden");
      }
    }
  });

  el("btn-wizard-start-index")?.addEventListener("click", async () => {
    if (!WIZARD_STATE.profileName) return;
    try {
      await api("/kb/api/profiles/" + WIZARD_STATE.profileName + "/index", {
        method: "POST",
        body: JSON.stringify({ full: true }),
      });
      location.href = "/kb/profile/" + WIZARD_STATE.profileName;
    } catch (e) {
      alert(e.message);
    }
  });
}

function renderProfileDetail(p) {
  return `
    <section class="profile-header panel">
      <div class="profile-header-top">
        <h1>${escapeHtml(p.display_name)}</h1>
        <div class="profile-header-actions">
          <button type="button" class="btn-icon" id="btn-profile-tools" title="Экспорт, клон, сравнение" aria-label="Экспорт и инструменты">
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>
              <polyline points="16 6 12 2 8 6"/>
              <line x1="12" y1="2" x2="12" y2="15"/>
            </svg>
          </button>
          <button type="button" class="btn danger small" id="btn-delete-profile">Удалить</button>
        </div>
      </div>
      <dl>
        <dt>Профиль</dt><dd>${p.name}</dd>
        ${p.git_branch ? `<dt>Git ветка</dt><dd>${escapeHtml(p.git_branch)}</dd>` : ""}
        <dt>Формат</dt><dd>${p.format === "edt" ? "EDT" : "XML-выгрузка"}</dd>
        <dt>Исходники 1С</dt><dd>${escapeHtml(p.root)}</dd>
        <dt>Индекс (Chroma)</dt><dd><code>${escapeHtml(p.store_path || `data/profiles/${p.name}/chroma`)}</code></dd>
        <dt>Коллекция</dt><dd>${p.collection}</dd>
        <dt>Чанков в индексе</dt><dd>${p.chunks}</dd>
        <dt>MCP-сервер</dt><dd>${p.mcp_server_name}</dd>
        <dt>MCP URL</dt><dd>${p.mcp_url || "— (контейнер не запущен)"}</dd>
      </dl>
    </section>`;
}

let jobPollTimer = null;
let jobEventSource = null;
let lastCompareData = null;

const WIZARD_STATE = { preview: null, profileName: "" };

function formatEta(seconds) {
  if (!seconds || seconds <= 0) return "";
  const mins = Math.floor(seconds / 60);
  const secs = Math.ceil(seconds % 60);
  return mins ? `~${mins}м ${secs}с` : `~${secs}с`;
}

function formatChunksProgress(prog) {
  const written = prog.chunks_written || 0;
  const estimated = prog.chunks_estimated || 0;
  if (written <= 0) return "";
  if (estimated > written) return ` · чанки ${written}/${estimated}`;
  return ` · чанки ${written}`;
}

function healthCheckRows(checks) {
  const rows = [];
  const labels = {
    source: "Источник",
    scan: "Сканирование",
    chroma: "Chroma",
    embeddings: "Embeddings",
    docker: "Docker",
    cursor_mcp: "Cursor MCP",
    watcher: "Watch",
    disk: "Диск",
    manifest: "Manifest",
  };
  for (const [key, check] of Object.entries(checks || {})) {
    const ok = check.ok ?? check.active ?? (check.status === "connected");
    let details = "";
    if (key === "chroma") details = `${check.chunks ?? 0} чанков`;
    else if (key === "embeddings") details = check.message || check.model || "";
    else if (key === "docker") details = check.url || check.daemon_error || "";
    else if (key === "cursor_mcp") details = check.message || check.status || "";
    else if (key === "watcher") details = check.active ? "активен" : "выкл";
    else if (key === "disk") details = check.free_gb != null ? `${check.free_gb} GB` : "";
    else if (check.path) details = check.path;
    else if (check.error) details = check.error;
    else if (check.files != null) details = `${check.files} файлов`;
    rows.push({ name: labels[key] || key, ok, details });
  }
  return rows;
}

function renderHealthTable(tbody, checks) {
  if (!tbody) return;
  const rows = healthCheckRows(checks);
  if (!rows.length) {
    tbody.innerHTML = "<tr><td colspan='3'>Нет данных</td></tr>";
    return;
  }
  tbody.innerHTML = rows
    .map(
      (r) =>
        `<tr><td>${escapeHtml(r.name)}</td><td class="${r.ok ? "ok" : "fail"}">${
          r.ok ? "OK" : "FAIL"
        }</td><td>${escapeHtml(r.details)}</td></tr>`
    )
    .join("");
}

function showWizardStep(step) {
  for (let i = 1; i <= 5; i++) {
    el(`wizard-pane-${i}`)?.classList.toggle("hidden", i !== step);
    const badge = document.querySelector(`.wizard-step[data-step="${i}"]`);
    if (badge) {
      badge.classList.toggle("active", i === step);
      badge.classList.toggle("done", i < step);
    }
  }
}

function stopJobStream() {
  if (jobEventSource) {
    jobEventSource.close();
    jobEventSource = null;
  }
  clearInterval(jobPollTimer);
  jobPollTimer = null;
}

function startJobStream(jobId) {
  stopJobStream();
  if (typeof EventSource !== "undefined") {
    jobEventSource = new EventSource("/kb/api/jobs/" + jobId + "/stream");
    jobEventSource.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.job) showJob(data.job);
      } catch (_) {}
    };
    jobEventSource.onerror = () => {
      stopJobStream();
      jobPollTimer = setInterval(() => pollJob(jobId), 2000);
    };
    return;
  }
  jobPollTimer = setInterval(() => pollJob(jobId), 2000);
}

function showJob(job, chunks = null) {
  const box = el("job-status");
  const bar = el("job-progress");
  const fill = el("job-progress-fill");
  if (!job) {
    box?.classList.add("hidden");
    bar?.classList.add("hidden");
    return;
  }
  box.classList.remove("hidden");
  box.className = "job-status " + job.status;
  const mode = job.resume
    ? "возобновление"
    : job.incremental
      ? "инкрементальная"
      : job.full
        ? "полная"
        : "обычная";
  const prog = job.progress || {};
  const phaseEl = el("job-phase");
  const cancelBtn = el("btn-job-cancel");
  if (prog.total_files > 0 && (job.status === "running" || job.status === "pending")) {
    bar?.classList.remove("hidden");
    if (fill) fill.style.width = (prog.percent || 0) + "%";
    cancelBtn?.classList.remove("hidden");
  } else {
    bar?.classList.add("hidden");
    cancelBtn?.classList.add("hidden");
  }
  if (phaseEl) {
    if (prog.phase && (job.status === "running" || job.status === "pending")) {
      phaseEl.classList.remove("hidden");
      const chunks = formatChunksProgress(prog);
      phaseEl.textContent = `Фаза: ${prog.phase}${chunks}${prog.eta_seconds ? " · ETA " + formatEta(prog.eta_seconds) : ""}`;
    } else {
      phaseEl.classList.add("hidden");
    }
  }
  let statsHtml = "";
  if (prog.current_file && prog.total_files) {
    statsHtml += `<br><strong>Прогресс:</strong> ${prog.current_file}/${prog.total_files}`;
    if (prog.eta_seconds) statsHtml += ` · ETA ${formatEta(prog.eta_seconds)}`;
  }
  if (prog.current_path) {
    statsHtml += `<br><strong>Файл:</strong> ${escapeHtml(prog.current_path.split("/").slice(-2).join("/"))}`;
  }
  if (job.stats?.chunks_in_collection != null) {
    statsHtml += `<br><strong>Чанков в коллекции:</strong> ${job.stats.chunks_in_collection}`;
  } else if (job.stats?.chunks) {
    statsHtml += `<br><strong>Чанков в коллекции:</strong> ${job.stats.chunks}`;
  }
  if (job.stats?.files_processed != null) {
    statsHtml += `<br><strong>Обработано файлов:</strong> ${job.stats.files_processed}`;
  }
  if (job.stats?.files_deleted) {
    statsHtml += `<br><strong>Удалено из индекса:</strong> ${job.stats.files_deleted}`;
  }
  if (job.stats?.chunks_written != null) {
    statsHtml += `<br><strong>Записано чанков:</strong> ${job.stats.chunks_written}`;
  }
  box.innerHTML = `
    <strong>Режим:</strong> ${mode}<br>
    <strong>Статус:</strong> ${job.status}<br>
    <strong>Сообщение:</strong> ${escapeHtml(job.progress_message || prog.message || "")}<br>
    ${job.error ? `<strong>Ошибка:</strong> ${escapeHtml(job.error)}` : ""}
    ${statsHtml}
  `;
  if (job.status === "running" || job.status === "pending") {
    setStepState("index", "active", "Индексация…");
    if (job.id && !jobEventSource && !jobPollTimer) startJobStream(job.id);
  } else if (job.status === "completed") {
    if (chunks === 0) {
      setStepState("index", "active", "Не выполнено");
    } else {
      setStepState("index", "success", chunks != null ? `Выполнено ✓ (${chunks} чанков)` : "Выполнено ✓");
    }
    stopJobStream();
    loadProfileHealth(window.__profileName);
    if (window.__profileName) {
      refreshProfile(window.__profileName).catch(() => {});
    }
  } else if (job.status === "failed" || job.status === "cancelled") {
    setStepState("index", "error", job.status === "cancelled" ? "Отменено" : "Ошибка");
    stopJobStream();
    if (window.__profileName) {
      refreshProfile(window.__profileName).catch(() => {});
    }
  } else {
    stopJobStream();
  }
}

async function pollJob(jobId) {
  try {
    const { job } = await api("/kb/api/jobs/" + jobId);
    showJob(job);
  } catch (_) {}
}

let dockerBuildPoll = null;
let dockerLogUserToggled = false;
let savedComposeDir = "";
let lastDockerPanelState = {};

function updateDockerControls(p, buildState = {}) {
  const dockerEnabled = Boolean(p?.gates?.docker_enabled);
  const docker = p?.docker || {};
  const state = { ...lastDockerPanelState, ...buildState };
  const running = Boolean(docker.running || state.container_running);
  const imageReady = Boolean(state.image_exists ?? docker.image_exists);
  const building = state.status === "building";
  const buildBlocked = building;
  const composeDir = docker.compose_dir || savedComposeDir;

  const reason = {
    build: !dockerEnabled
      ? "Сначала выполните индексацию"
      : running
        ? "Остановите контейнер перед сборкой"
        : buildBlocked
          ? "Дождитесь окончания сборки"
          : "",
    start: !dockerEnabled
      ? "Сначала выполните индексацию"
      : buildBlocked
        ? "Дождитесь окончания сборки"
        : !imageReady
          ? "Сначала нажмите «Собрать образ»"
          : !composeDir
            ? "Укажите папку compose — «Стандартная папка» или выбор вручную"
            : running
              ? "Контейнер уже запущен"
              : "",
    stop: !dockerEnabled ? "Сначала выполните индексацию" : !running ? "Контейнер не запущен" : "",
    pick: !dockerEnabled ? "Сначала выполните индексацию" : running ? "Остановите контейнер" : "",
    default: !dockerEnabled ? "Сначала выполните индексацию" : running ? "Остановите контейнер" : "",
  };

  function setBtn(id, disabled, title) {
    const btn = el(id);
    if (!btn) return;
    if (id === "btn-docker-build" && btn.textContent === "Сборка…") return;
    btn.disabled = disabled;
    btn.title = title || "";
  }

  setBtn("btn-docker-build", !dockerEnabled || buildBlocked || running, reason.build);
  setBtn(
    "btn-docker-start",
    !(dockerEnabled && imageReady && composeDir && !running && !buildBlocked),
    reason.start
  );
  setBtn("btn-docker-stop", !dockerEnabled || !running, reason.stop);
  setBtn("btn-docker-pick-dir", !dockerEnabled || running, reason.pick);
  setBtn("btn-docker-use-default-compose", !dockerEnabled || running, reason.default);
  const rebuild = el("docker-rebuild");
  if (rebuild) {
    rebuild.disabled = !dockerEnabled || buildBlocked || running;
    rebuild.title = reason.build;
  }
}

function updateComposeDirDisplay(docker) {
  const line = el("docker-compose-dir");
  if (!line) return;
  if (docker?.compose_dir) {
    savedComposeDir = docker.compose_dir;
    line.className = "runtime-line";
    line.textContent = `Compose-проект: ${docker.compose_dir}`;
  } else if (docker?.compose_dir_suggested) {
    savedComposeDir = "";
    line.className = "runtime-line";
    line.textContent = `Директория не выбрана. Рекомендуется: ${docker.compose_dir_suggested}`;
  } else {
    savedComposeDir = "";
    line.textContent = "Директория compose будет запрошена при запуске контейнера";
  }
}

async function pickComposeDirectory(profileName, currentDir, suggestedDir) {
  const parts = [];
  if (currentDir) parts.push(`Текущая: ${currentDir}`);
  if (suggestedDir) parts.push(`Рекомендуется: ${suggestedDir}`);
  const hint = parts.length ? parts.join(". ") + ". " : "";
  const r = await api("/kb/api/pick-directory", {
    method: "POST",
    body: JSON.stringify({
      title: `${hint}Каталог compose для 1c-kb-${profileName}`,
    }),
  });
  if (r.cancelled) return null;
  return r.path;
}

async function saveComposeDirectory(profileName, composeDir) {
  const data = await api("/kb/api/profiles/" + profileName + "/docker/compose-dir", {
    method: "PUT",
    body: JSON.stringify({ compose_dir: composeDir }),
  });
  savedComposeDir = data.compose_dir;
  updateComposeDirDisplay({ compose_dir: data.compose_dir });
  const p = await api("/kb/api/profiles/" + profileName).catch(() => null);
  if (p) updateDockerControls(p, lastDockerPanelState);
  return data.compose_dir;
}

function dockerLogHasActiveSelection(box) {
  if (!box) return false;
  if (document.activeElement === box) return true;
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) return false;
  const anchor = sel.anchorNode;
  const focus = sel.focusNode;
  return (anchor && box.contains(anchor)) || (focus && box.contains(focus));
}

function renderDockerLogBox(state, { autoscroll = true } = {}) {
  const box = el("docker-status");
  if (!box) return;
  const wasAtBottom =
    box.scrollHeight - box.scrollTop - box.clientHeight < 48;

  const lines = [];

  if (state.log || state.status !== "idle") {
    lines.push("=== Сборка образа ===");
    if (state.message) lines.push(state.message);
    if (state.log) lines.push(state.log);
    if (state.error) lines.push("", "ОШИБКА: " + state.error);
    if (state.status === "completed") {
      lines.push("", "✓ Сборка завершена успешно — конец лога сборки.");
    } else if (state.status === "skipped") {
      lines.push("", "✓ Образ уже был собран — повторная сборка не выполнялась.");
    } else if (state.status === "interrupted") {
      lines.push("", "⚠ Сборка прервана — нажмите «Собрать образ» (лучше с «Пересобрать»).");
    }
  } else if (state.image_exists) {
    const imageName = state.image || `1c-kb-${window.__profileName || "profile"}-mcp`;
    if (state.build_history) {
      lines.push(
        `Образ ${imageName} уже собран через kb-web.`,
        "Лог прошлой сборки появится здесь после «Собрать образ» (или включите «Пересобрать»).",
      );
    } else {
      lines.push(
        `Образ ${imageName} найден в Docker.`,
        "Через этот интерфейс сборка ещё не запускалась — можно сразу нажать «Запустить контейнер».",
        "Если образ собирали вручную или на другой машине — это нормально.",
        "Чтобы собрать здесь и увидеть лог — нажмите «Собрать образ».",
      );
    }
  }

  if (state.container_running) {
    lines.push("", "=== Контейнер ===");
    if (state.url) {
      lines.push(`Запущен. MCP: ${state.url}`);
    } else {
      lines.push("Запущен.");
    }
    lines.push("Служебный лог MCP (запросы Cursor) в интерфейсе не показывается.");
  }

  if (state.compose_dir) {
    lines.push("", `Compose-директория: ${state.compose_dir}`);
  }

  if (!lines.length) {
    lines.push(
      "Шаги по порядку: 1) «Собрать образ» → 2) «Стандартная папка» или выбор compose → 3) «Запустить контейнер».",
    );
  }

  const newText = lines.join("\n");
  if (dockerLogHasActiveSelection(box)) {
    box.dataset.pendingLog = newText;
  } else {
    if (box.dataset.pendingLog) delete box.dataset.pendingLog;
    if (box.textContent !== newText) {
      box.textContent = newText;
    }
  }

  if (autoscroll && (wasAtBottom || state.status === "building")) {
    box.scrollTop = box.scrollHeight;
  }

  if (state.status === "building") {
    setStepState("docker", "active", "Сборка образа…");
  } else if (state.container_running) {
    setStepState("docker", "success", "Контейнер работает ✓");
  } else if (state.status === "failed" || state.status === "interrupted") {
    setStepState(
      "docker",
      "error",
      state.status === "interrupted" ? "Сборка прервана — запустите снова" : "Ошибка сборки",
    );
  } else if (state.status === "completed" || state.status === "skipped") {
    setStepState("docker", "active", "Образ готов — запустите контейнер");
  } else if (state.image_exists) {
    const label = state.build_history
      ? "Образ готов — запустите контейнер"
      : "Образ найден — запустите контейнер";
    setStepState("docker", "active", label);
  }

  updateDockerLogCollapse(state);
}

function updateDockerLogCollapse(state) {
  const wrap = el("docker-log-wrap");
  const summary = el("docker-log-summary");
  if (!wrap) return;

  const running = Boolean(state.container_running);
  const busy =
    state.status === "building" || state.status === "failed" || state.status === "interrupted";
  const collapse = running && !busy;

  wrap.classList.toggle("docker-log--running", collapse);
  if (summary) {
    summary.textContent = collapse
      ? "Лог Docker (контейнер работает — нажмите, чтобы развернуть)"
      : "Лог Docker";
  }
  if (!dockerLogUserToggled) {
    wrap.open = !collapse;
  }
}

async function loadDockerPanel(profileName) {
  try {
    const data = await api("/kb/api/profiles/" + profileName + "/docker/logs");
    const merged = {
      ...data.build,
      container_running: data.container_running,
      compose_dir: data.compose_dir,
      url: data.url,
    };
    lastDockerPanelState = merged;
    renderDockerLogBox(merged);
    return merged;
  } catch (e) {
    const build = await api("/kb/api/profiles/" + profileName + "/docker/build");
    lastDockerPanelState = build;
    renderDockerLogBox(build);
    return build;
  }
}

async function pollDockerBuild() {
  const name = window.__profileName;
  try {
    const r = await api("/kb/api/profiles/" + name + "/docker/build");
    lastDockerPanelState = { ...lastDockerPanelState, ...r };
    if (name) await loadDockerPanel(name);
    if (r.status === "building") {
      const p = await api("/kb/api/profiles/" + name).catch(() => null);
      if (p) updateDockerControls(p, r);
      return;
    }
    clearInterval(dockerBuildPoll);
    dockerBuildPoll = null;
    const buildBtn = el("btn-docker-build");
    if (buildBtn) {
      buildBtn.disabled = false;
      buildBtn.textContent = "Собрать образ";
    }
    if (name) {
      const p = await api("/kb/api/profiles/" + name).catch(() => null);
      if (p) updateDockerControls(p, r);
    }
  } catch (e) {
    const pre = el("docker-status");
    if (pre) pre.textContent = "Ошибка опроса сборки: " + e.message;
    setStepState("docker", "error", "Ошибка");
  }
}

function renderDockerBuild(state, opts) {
  renderDockerLogBox(state, opts);
}

function updateCursorStepState(cursor) {
  const line = el("cursor-status");
  if (!cursor) {
    if (line) line.textContent = "";
    return;
  }

  if (line) {
    line.className = "runtime-line" + (cursor.status === "connected" ? " ok" : "");
    line.textContent = cursor.message || "";
  }

  if (cursor.status === "connected") {
    setStepState("cursor", "success", "Подключён в Cursor ✓");
  } else if (cursor.status === "ready") {
    setStepState("cursor", "active", "Включите в Cursor");
  } else if (cursor.status === "configured") {
    setStepState("cursor", "active", "Запустите контейнер");
  } else if (cursor.status === "misconfigured" || cursor.status === "error") {
    setStepState("cursor", "error", "Проверьте настройку");
  } else if (cursor.in_mcp_json) {
    setStepState("cursor", "active", "В mcp.json");
  } else {
    setStepState("cursor", "active", "Не выполнено");
  }
}

async function pollCursorStatus(profileName, { full = false } = {}) {
  try {
    const q = full ? "?full=1" : "";
    const cursor = await api("/kb/api/profiles/" + profileName + "/mcp/cursor-status" + q);
    updateCursorStepState(cursor);
    if (cursor.status === "connected" && cursorStatusPoll) {
      clearInterval(cursorStatusPoll);
      cursorStatusPoll = null;
    }
    return cursor;
  } catch (e) {
    const line = el("cursor-status");
    if (line) line.textContent = "Не удалось проверить Cursor: " + e.message;
    return null;
  }
}

async function refreshProfile(name) {
  const p = await api("/kb/api/profiles/" + name);
  el("profile-detail").innerHTML = renderProfileDetail(p);
  const rulesLink = el("link-rules");
  if (rulesLink && p.root) {
    rulesLink.href = "/rules/?project_path=" + encodeURIComponent(p.root);
  }
  showJob(p.index_job, p.chunks);

  if (p.chunks > 0 && (!p.index_job || p.index_job.status === "completed")) {
    setStepState("index", "success", `Выполнено ✓ (${p.chunks} чанков)`);
  } else if (
    p.chunks <= 0 &&
    (!p.index_job || !["running", "pending"].includes(p.index_job.status))
  ) {
    setStepState("index", "active", "Не выполнено");
  }

  const runtime = el("docker-runtime");
  if (runtime) {
    if (p.docker?.running) {
      runtime.className = "runtime-line ok";
      runtime.textContent = `Контейнер запущен · ${p.mcp_url || ""}`;
    } else {
      runtime.className = "runtime-line";
      runtime.textContent = p.docker?.container_id
        ? "Контейнер остановлен"
        : "Контейнер не запущен";
    }
  }

  if (p.docker?.running) {
    setStepState("docker", "success", "Контейнер работает ✓");
  }

  updateComposeDirDisplay(p.docker);

  if (p.embeddings) {
    syncEmbeddingForm(p.embeddings);
  }
  if (el("idx-include-forms")) el("idx-include-forms").checked = Boolean(p.indexing?.include_forms);
  const watchToggle = el("watch-toggle");
  const w = p.watch || {};
  if (watchToggle) watchToggle.checked = Boolean(w.active);
  if (el("watch-status")) {
    const mode = w.mode ? ` · ${w.mode}` : "";
    el("watch-status").textContent = w.active
      ? `Автообновление включено${mode} · срабатываний: ${w.last_trigger || "—"}`
      : w.configured
        ? "Автообновление выключено (было включено ранее)"
        : "";
  }
  updateCheckpointUI(p.checkpoint, p.index_job);

  loadProfileHealth(name);

  updateWorkflowGates(p);

  const dockerPanel = await loadDockerPanel(name);
  lastDockerPanelState = dockerPanel || {};
  updateDockerControls(p, dockerPanel);
  updateCursorStepState(p.cursor_mcp);
  if (p.cursor_mcp?.status !== "connected") {
    pollCursorStatus(name);
  }
}

let cursorStatusPoll = null;
const MCP_MODE_KEY = "kb_mcp_update_mode";

function getMcpUpdateMode() {
  return localStorage.getItem(MCP_MODE_KEY) === "manual" ? "manual" : "auto";
}

function setMcpUpdateMode(mode) {
  localStorage.setItem(MCP_MODE_KEY, mode === "manual" ? "manual" : "auto");
  syncMcpModePanels();
}

function syncMcpModePanels() {
  const auto = getMcpUpdateMode() === "auto";
  const toggle = el("mcp-mode-toggle");
  if (toggle) toggle.checked = auto;
  el("mcp-panel-auto")?.classList.toggle("hidden", !auto);
  el("mcp-panel-manual")?.classList.toggle("hidden", auto);
}

function updateMcpRestoreButton(settings) {
  const btn = el("btn-mcp-restore");
  if (!btn) return;
  const name = settings?.latest_backup_name || "";
  const hasBackup = Boolean(settings?.latest_backup);
  const mcpEnabled = window.__profileGates?.mcp_enabled !== false;
  btn.disabled = !mcpEnabled || !hasBackup;
  btn.title = hasBackup
    ? `Восстановить ${name}`
    : "Бэкап появится после «Обновить mcp.json в Cursor»";
}

async function loadCursorDirSettings() {
  const line = el("cursor-dir-line");
  const pickRow = el("cursor-dir-pick-row");
  try {
    const s = await api("/kb/api/cursor/settings");
    updateMcpRestoreButton(s);
    if (s.cursor_home_found) {
      pickRow?.classList.add("hidden");
      if (line) {
        line.className = "runtime-line ok";
        line.textContent = `Каталог Cursor: ${s.cursor_dir} (найден в домашней папке)`;
      }
    } else {
      pickRow?.classList.remove("hidden");
      if (line) {
        if (s.cursor_dir_ready) {
          line.className = "runtime-line ok";
          line.textContent = `Каталог Cursor: ${s.cursor_dir}`;
        } else {
          line.className = "runtime-line";
          line.textContent =
            s.cursor_dir_error ||
            "Каталог ~/.cursor не найден — укажите, где лежит mcp.json";
        }
      }
    }
    return s;
  } catch (e) {
    if (line) {
      line.className = "runtime-line";
      line.textContent = "Не удалось определить каталог Cursor: " + e.message;
    }
    return null;
  }
}

async function pickCursorDirectory() {
  const r = await api("/kb/api/pick-directory", {
    method: "POST",
    body: JSON.stringify({
      title: "Каталог конфигурации Cursor (где будет mcp.json)",
    }),
  });
  if (r.cancelled) return null;
  return r.path;
}

async function loadIndexChangesPreview(profileName) {
  const line = el("index-changes");
  if (!line) return null;
  try {
    const data = await api("/kb/api/profiles/" + profileName + "/index/changes");
    if ((data.indexed_chunks ?? 0) <= 0) {
      line.className = "runtime-line";
      line.textContent = `${data.format_label}: индекс пуст — сначала выполните полную индексацию`;
      return data;
    }
    if (!data.has_changes) {
      line.className = "runtime-line ok";
      line.textContent = `${data.format_label}: изменений нет (${data.source_label})`;
      return data;
    }
    line.className = "runtime-line";
    const sample = [...(data.modified || []).slice(0, 3), ...(data.deleted || []).slice(0, 2)]
      .map((p) => p.split("/").slice(-2).join("/"))
      .join(", ");
    line.textContent =
      `${data.format_label}: изменено ${data.modified_count}, удалено ${data.deleted_count}` +
      ` · ${data.source_label}` +
      (sample ? ` · ${sample}${data.total_count > 5 ? "…" : ""}` : "");
    return data;
  } catch (e) {
    line.textContent = "Не удалось проверить изменения: " + e.message;
    line.className = "runtime-line";
    return null;
  }
}

async function startIndex(profileName, { full = false, incremental = false, resume = false } = {}) {
  const { job } = await api("/kb/api/profiles/" + profileName + "/index", {
    method: "POST",
    body: JSON.stringify({ full, incremental, resume }),
  });
  showJob(job);
  if (job.id) startJobStream(job.id);
}

function syncEmbeddingForm(emb) {
  const provider = emb.provider || "local";
  if (el("emb-provider")) el("emb-provider").value = provider;
  if (el("emb-device")) {
    el("emb-device").value = emb.device || "auto";
    el("emb-device").disabled = provider === "openai";
  }
  const modelSelect = el("emb-model-select");
  if (modelSelect && emb.model) {
    const has = [...modelSelect.options].some((o) => o.value === emb.model);
    if (!has) {
      const opt = document.createElement("option");
      opt.value = emb.model;
      opt.textContent = emb.model;
      modelSelect.add(opt);
    }
    modelSelect.value = emb.model;
  }
  if (el("emb-batch")) el("emb-batch").value = emb.batch_size || "";
  el("emb-openai-hint")?.classList.toggle("hidden", provider !== "openai");
}

function syncEmbeddingModelOptions() {
  const provider = el("emb-provider")?.value || "local";
  const select = el("emb-model-select");
  if (!select) return;
  [...select.options].forEach((opt) => {
    const group = opt.parentElement?.label;
    if (!group) return;
    const isOpenai = group.includes("OpenAI");
    opt.hidden = provider === "openai" ? !isOpenai : isOpenai;
  });
  const visible = [...select.options].find((o) => !o.hidden);
  if (visible && select.selectedOptions[0]?.hidden) select.value = visible.value;
}

async function openProfileToolsDialog(profileName) {
  const dialog = el("dialog-profile-tools");
  const list = el("profile-names-list");
  if (list) {
    try {
      const profiles = await api("/kb/api/profiles");
      list.innerHTML = profiles
        .map((p) => p.name)
        .filter((n) => n !== profileName)
        .map((n) => `<option value="${escapeHtml(n)}">`)
        .join("");
    } catch (_) {}
  }
  dialog?.showModal();
}

function updateCheckpointUI(checkpoint, indexJob) {
  const hint = el("checkpoint-hint");
  const resumeBtn = el("btn-index-resume");
  const clearBtn = el("btn-checkpoint-clear");
  const busy = indexJob && (indexJob.status === "running" || indexJob.status === "pending");
  if (!checkpoint?.available || busy) {
    hint?.classList.add("hidden");
    resumeBtn?.classList.add("hidden");
    clearBtn?.classList.add("hidden");
    return;
  }
  hint?.classList.remove("hidden");
  hint.className = "runtime-line";
  const phase = checkpoint.phase ? ` · фаза ${checkpoint.phase}` : "";
  hint.textContent =
    `Незавершённая полная индексация: обработано ${checkpoint.processed_count} файлов${phase}`;
  resumeBtn?.classList.remove("hidden");
  clearBtn?.classList.remove("hidden");
}

function initProfilePage(name) {
  window.__profileName = name;

  el("docker-log-wrap")?.addEventListener("toggle", () => {
    dockerLogUserToggled = true;
  });

  el("btn-docker-log-copy")?.addEventListener("click", async (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    const box = el("docker-status");
    const text = (box?.dataset.pendingLog || box?.textContent || "").trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      const btn = el("btn-docker-log-copy");
      if (btn) {
        const prev = btn.textContent;
        btn.textContent = "Скопировано";
        setTimeout(() => {
          btn.textContent = prev;
        }, 1500);
      }
    } catch (_) {
      const range = document.createRange();
      range.selectNodeContents(box);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
      document.execCommand("copy");
      sel?.removeAllRanges();
    }
  });

  const dialogSettings = el("dialog-index-settings");
  const dialogTools = el("dialog-profile-tools");
  const dialogDelete = el("dialog-delete-profile");

  el("btn-index-settings")?.addEventListener("click", () => dialogSettings?.showModal());
  dialogSettings?.querySelectorAll("[data-close-settings]").forEach((b) =>
    b.addEventListener("click", () => dialogSettings.close())
  );
  dialogTools?.querySelectorAll("[data-close-tools]").forEach((b) =>
    b.addEventListener("click", () => dialogTools.close())
  );
  dialogDelete?.querySelectorAll("[data-close-delete]").forEach((b) =>
    b.addEventListener("click", () => dialogDelete.close())
  );

  el("emb-provider")?.addEventListener("change", () => {
    syncEmbeddingModelOptions();
    el("emb-openai-hint")?.classList.toggle("hidden", el("emb-provider").value !== "openai");
    if (el("emb-device")) el("emb-device").disabled = el("emb-provider").value === "openai";
  });

  const deleteConfirm = el("delete-confirm-name");
  const deleteBtn = el("btn-delete-profile-confirm");
  deleteConfirm?.addEventListener("input", () => {
    if (deleteBtn) deleteBtn.disabled = deleteConfirm.value.trim() !== name;
  });

  deleteBtn?.addEventListener("click", async () => {
    if (deleteConfirm?.value.trim() !== name) return;
    try {
      await api("/kb/api/profiles/" + name, { method: "DELETE" });
      location.href = "/";
    } catch (e) {
      alert(e.message);
    }
  });

  document.getElementById("profile-detail")?.addEventListener("click", (ev) => {
    if (ev.target.closest("#btn-profile-tools")) {
      openProfileToolsDialog(name);
    }
    if (ev.target.closest("#btn-delete-profile")) {
      const deleteConfirm = el("delete-confirm-name");
      const deleteBtn = el("btn-delete-profile-confirm");
      if (deleteConfirm) deleteConfirm.value = "";
      if (deleteBtn) deleteBtn.disabled = true;
      dialogDelete?.showModal();
    }
  });

  el("watch-toggle")?.addEventListener("change", async (ev) => {
    const on = ev.target.checked;
    try {
      await api("/kb/api/profiles/" + name + "/watch/" + (on ? "start" : "stop"), { method: "POST" });
      await refreshProfile(name);
    } catch (e) {
      ev.target.checked = !on;
      alert(e.message);
    }
  });

  syncEmbeddingModelOptions();
  refreshKbDockerBadge();
  refreshProfile(name).catch((e) => {
    el("profile-detail").textContent = "Ошибка: " + e.message;
  });

  el("btn-scan")?.addEventListener("click", async () => {
    const pre = el("scan-result");
    pre.classList.remove("hidden");
    pre.textContent = "Сканирование…";
    try {
      const r = await api("/kb/api/profiles/" + name + "/scan", { method: "POST" });
      pre.textContent = "Файлов: " + r.total + "\n" + JSON.stringify(r.kinds, null, 2);
    } catch (e) {
      pre.textContent = e.message;
    }
  });

  el("btn-index-resume")?.addEventListener("click", async () => {
    try {
      await startIndex(name, { resume: true });
    } catch (e) {
      alert(e.message);
    }
  });

  el("btn-checkpoint-clear")?.addEventListener("click", async () => {
    if (!confirm("Сбросить checkpoint? Следующая полная индексация начнётся с нуля.")) return;
    try {
      await api("/kb/api/profiles/" + name + "/checkpoint", { method: "DELETE" });
      updateCheckpointUI(null, null);
    } catch (e) {
      alert(e.message);
    }
  });

  el("btn-index-full")?.addEventListener("click", async () => {
    const p = await api("/kb/api/profiles/" + name);
    const hasCheckpoint = Boolean(p.checkpoint?.available);
    const msg = hasCheckpoint
      ? "Полная индексация пересоздаст коллекцию и удалит checkpoint. Продолжить?"
      : "Полная индексация пересоздаст коллекцию. Продолжить?";
    if (!confirm(msg)) return;
    try {
      await startIndex(name, { full: true });
    } catch (e) {
      alert(e.message);
    }
  });

  el("btn-index-incremental")?.addEventListener("click", async () => {
    try {
      const preview = await loadIndexChangesPreview(name);
      if (preview?.indexed_chunks === 0) {
        alert("Сначала выполните полную индексацию");
        return;
      }
      if (!preview?.has_changes) {
        alert("Нет изменённых файлов для обновления");
        return;
      }
      await startIndex(name, { incremental: true });
    } catch (e) {
      alert(e.message);
    }
  });

  el("btn-index-changes-preview")?.addEventListener("click", () => {
    loadIndexChangesPreview(name);
  });

  el("btn-job-cancel")?.addEventListener("click", async () => {
    const job = (await api("/kb/api/profiles/" + name)).index_job;
    if (!job?.id) return;
    if (!confirm("Отменить индексацию?")) return;
    try {
      const r = await api("/kb/api/jobs/" + job.id + "/cancel", { method: "POST" });
      showJob(r.job);
    } catch (e) {
      alert(e.message);
    }
  });

  loadIndexChangesPreview(name);

  el("btn-docker-build")?.addEventListener("click", async () => {
    const btn = el("btn-docker-build");
    if (btn?.disabled) {
      alert(btn.title || "Сначала выполните шаги по порядку");
      return;
    }
    if (!window.__profileGates?.docker_enabled) {
      alert("Сначала выполните полную индексацию");
      return;
    }
    const force = el("docker-rebuild")?.checked || false;
    const pre = el("docker-status");
    btn.disabled = true;
    btn.textContent = "Сборка…";
    if (pre) {
      pre.textContent = force
        ? "Запуск пересборки образа… (10–20 мин, смотрите лог ниже)"
        : "Проверка образа / сборка…";
    }
    try {
      const r = await api("/kb/api/profiles/" + name + "/docker/build", {
        method: "POST",
        body: JSON.stringify({ force }),
      });
      renderDockerBuild(r);
      lastDockerPanelState = { ...lastDockerPanelState, ...r };
      if (r.status === "building") {
        updateDockerControls(
          await api("/kb/api/profiles/" + name).catch(() => ({ gates: window.__profileGates })),
          r,
        );
        if (!dockerBuildPoll) dockerBuildPoll = setInterval(pollDockerBuild, 2000);
      } else {
        btn.disabled = false;
        btn.textContent = "Собрать образ";
        const p = await api("/kb/api/profiles/" + name).catch(() => null);
        if (p) updateDockerControls(p, r);
      }
    } catch (e) {
      if (pre) pre.textContent = "Ошибка: " + e.message;
      btn.disabled = false;
      btn.textContent = "Собрать образ";
    }
  });

  loadDockerPanel(name).then((r) => {
    const buildBtn = el("btn-docker-build");
    if (r.status === "building" && !dockerBuildPoll) {
      if (buildBtn) buildBtn.textContent = "Сборка…";
      dockerBuildPoll = setInterval(pollDockerBuild, 2000);
    } else if (buildBtn && buildBtn.textContent === "Сборка…") {
      buildBtn.disabled = false;
      buildBtn.textContent = "Собрать образ";
    }
  });

  pollCursorStatus(name);
  if (!cursorStatusPoll) {
    cursorStatusPoll = setInterval(() => pollCursorStatus(name), 30000);
  }

  el("btn-docker-start")?.addEventListener("click", async () => {
    const startBtn = el("btn-docker-start");
    if (startBtn?.disabled) {
      alert(startBtn.title || "Сначала соберите образ и укажите папку compose");
      return;
    }
    if (!window.__profileGates?.docker_enabled) {
      alert("Сначала выполните полную индексацию");
      return;
    }
    try {
      const p = await api("/kb/api/profiles/" + name);
      let composeDir = p.docker?.compose_dir || savedComposeDir;
      if (!composeDir) {
        const saved = await api("/kb/api/profiles/" + name + "/docker/compose-dir", {
          method: "PUT",
          body: JSON.stringify({ use_default: true }),
        });
        composeDir = saved.compose_dir;
        updateComposeDirDisplay({ compose_dir: composeDir });
      }
      setStepState("docker", "active", "Запуск…");
      const rebuild = el("docker-rebuild")?.checked || false;
      const startResult = await api("/kb/api/profiles/" + name + "/docker/start", {
        method: "POST",
        body: JSON.stringify({ compose_dir: composeDir, rebuild }),
      });
      if (startResult.port_auto_assigned && startResult.message) {
        setStepState("docker", "active", startResult.message);
      }
      await refreshProfile(name);
      await loadDockerPanel(name);
    } catch (e) {
      setStepState("docker", "error", "Ошибка запуска");
      alert(e.message);
    }
  });

  el("btn-docker-use-default-compose")?.addEventListener("click", async () => {
    const btn = el("btn-docker-use-default-compose");
    if (btn?.disabled) {
      alert(btn.title || "Сначала выполните шаги по порядку");
      return;
    }
    try {
      await api("/kb/api/profiles/" + name + "/docker/compose-dir", {
        method: "PUT",
        body: JSON.stringify({ use_default: true }),
      });
      const p = await api("/kb/api/profiles/" + name);
      updateComposeDirDisplay(p.docker);
      updateDockerControls(p, lastDockerPanelState);
    } catch (e) {
      alert(e.message);
    }
  });

  el("btn-docker-pick-dir")?.addEventListener("click", async () => {
    const btn = el("btn-docker-pick-dir");
    if (btn?.disabled) {
      alert(btn.title || "Остановите контейнер перед сменой папки");
      return;
    }
    if (!window.__profileGates?.docker_enabled) {
      alert("Сначала выполните полную индексацию");
      return;
    }
    try {
      const p = await api("/kb/api/profiles/" + name);
      const composeDir = await pickComposeDirectory(
        name,
        p.docker?.compose_dir || savedComposeDir,
        p.docker?.compose_dir_suggested,
      );
      if (!composeDir) return;
      await saveComposeDirectory(name, composeDir);
    } catch (e) {
      alert(e.message);
    }
  });

  el("btn-docker-stop")?.addEventListener("click", async () => {
    const btn = el("btn-docker-stop");
    if (btn?.disabled) {
      alert(btn.title || "Контейнер не запущен");
      return;
    }
    if (!window.__profileGates?.docker_enabled) {
      alert("Сначала выполните полную индексацию");
      return;
    }
    try {
      await api("/kb/api/profiles/" + name + "/docker/stop", { method: "POST" });
      dockerLogUserToggled = false;
      await refreshProfile(name);
      setStepState("docker", "active", "Контейнер остановлен");
    } catch (e) {
      alert(e.message);
    }
  });

  syncMcpModePanels();
  loadCursorDirSettings();

  el("mcp-mode-toggle")?.addEventListener("change", (ev) => {
    setMcpUpdateMode(ev.target.checked ? "auto" : "manual");
    if (ev.target.checked) loadCursorDirSettings();
  });

  el("btn-cursor-pick-dir")?.addEventListener("click", async () => {
    const picked = await pickCursorDirectory();
    if (!picked) return;
    try {
      await api("/kb/api/cursor/dir", {
        method: "PUT",
        body: JSON.stringify({ cursor_dir: picked }),
      });
      await loadCursorDirSettings();
    } catch (e) {
      alert(e.message);
    }
  });

  el("btn-mcp-apply")?.addEventListener("click", async () => {
    if (!window.__profileGates?.mcp_enabled) {
      alert("Сначала соберите образ и запустите контейнер");
      return;
    }
    let settings = await loadCursorDirSettings();
    if (!settings?.cursor_dir_ready) {
      const picked = await pickCursorDirectory();
      if (!picked) return;
      try {
        await api("/kb/api/cursor/dir", {
          method: "PUT",
          body: JSON.stringify({ cursor_dir: picked }),
        });
        settings = await loadCursorDirSettings();
      } catch (e) {
        alert(e.message);
        return;
      }
    }
    if (!settings?.cursor_dir_ready) {
      alert("Сначала укажите каталог Cursor");
      return;
    }
    try {
      const data = await api("/kb/api/profiles/" + name + "/mcp/apply", { method: "POST" });
      const line = el("cursor-status");
      if (line) {
        line.className = "runtime-line ok";
        const backup = data.backup_name
          ? ` · бэкап: data/cursor-mcp-backups/${data.backup_name}`
          : "";
        line.textContent = `Записано в ${data.mcp_json_path}${backup}. Включите сервер в Cursor → Settings → MCP`;
      }
      await loadCursorDirSettings();
      await pollCursorStatus(name);
    } catch (e) {
      alert(e.message);
    }
  });

  el("btn-cursor-check-auto")?.addEventListener("click", () => {
    pollCursorStatus(name);
  });

  el("btn-mcp-restore")?.addEventListener("click", async () => {
    if (!window.__profileGates?.mcp_enabled) {
      alert("Сначала соберите образ и запустите контейнер");
      return;
    }
    const settings = await loadCursorDirSettings();
    if (!settings?.latest_backup) {
      alert("Бэкап mcp.json не найден");
      return;
    }
    const backupName = settings.latest_backup_name || "бэкап";
    if (
      !confirm(
        `Восстановить mcp.json из файла ${backupName}?\nТекущий mcp.json будет перезаписан.`,
      )
    ) {
      return;
    }
    try {
      const data = await api("/kb/api/cursor/mcp/restore", {
        method: "POST",
        body: JSON.stringify({ backup_path: settings.latest_backup }),
      });
      const line = el("cursor-status");
      if (line) {
        line.className = "runtime-line ok";
        line.textContent = `Восстановлено из ${data.backup_name}`;
      }
      await loadCursorDirSettings();
      await pollCursorStatus(name);
    } catch (e) {
      alert(e.message);
    }
  });

  el("mcp-file")?.addEventListener("change", async (ev) => {
    if (!window.__profileGates?.mcp_enabled) {
      ev.target.value = "";
      alert("Сначала соберите образ и запустите контейнер");
      return;
    }
    const file = ev.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch("/kb/api/profiles/" + name + "/mcp/merge", {
        method: "POST",
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      el("mcp-result").value = data.mcp_json;
      await pollCursorStatus(name);
    } catch (e) {
      alert(e.message);
    }
    ev.target.value = "";
  });

  el("btn-mcp-download")?.addEventListener("click", async () => {
    if (!window.__profileGates?.mcp_enabled) {
      alert("Сначала соберите образ и запустите контейнер");
      return;
    }
    window.location.href = "/kb/api/profiles/" + name + "/mcp/download";
    setTimeout(() => pollCursorStatus(name), 1500);
  });

  el("btn-cursor-check")?.addEventListener("click", () => {
    pollCursorStatus(name);
  });

  el("btn-mcp-copy")?.addEventListener("click", () => {
    const ta = el("mcp-result");
    ta.select();
    navigator.clipboard.writeText(ta.value);
  });

  el("btn-save-settings")?.addEventListener("click", async () => {
    try {
      const emb = await api("/kb/api/profiles/" + name + "/embeddings", {
        method: "PUT",
        body: JSON.stringify({
          provider: el("emb-provider")?.value || "local",
          device: el("emb-device").value,
          model: el("emb-model-select")?.value || "",
          batch_size: Number(el("emb-batch")?.value) || undefined,
        }),
      });
      const idx = await api("/kb/api/profiles/" + name + "/indexing", {
        method: "PUT",
        body: JSON.stringify({ include_forms: el("idx-include-forms").checked }),
      });
      let msg = "Настройки сохранены";
      if (emb.embeddings?.needs_reindex || idx.indexing?.needs_reindex) {
        msg += "\n\nТребуется полная переиндексация (смена модели или include_forms).";
      }
      alert(msg);
      dialogSettings?.close();
      await refreshProfile(name);
    } catch (e) {
      alert(e.message);
    }
  });

  el("btn-export-index")?.addEventListener("click", () => {
    window.location.href = "/kb/api/profiles/" + name + "/export";
  });

  el("btn-check-embeddings")?.addEventListener("click", async () => {
    const box = el("emb-check-result");
    box?.classList.remove("hidden");
    box.textContent = "Проверка…";
    try {
      const r = await api("/kb/api/profiles/" + name + "/embeddings/check");
      box.className = "runtime-line" + (r.ok ? " ok" : "");
      box.textContent = `${r.provider} · ${r.model} · ${r.device || ""} — ${r.message}`;
    } catch (e) {
      box.className = "runtime-line";
      box.textContent = e.message;
    }
  });

  el("btn-clone-profile")?.addEventListener("click", async () => {
    const target = el("clone-target-name")?.value?.trim();
    if (!target) return alert("Укажите имя нового профиля");
    const copyIndex = Boolean(el("clone-copy-index")?.checked);
    try {
      const r = await api("/kb/api/profiles/" + name + "/clone", {
        method: "POST",
        body: JSON.stringify({ target_name: target, copy_index: copyIndex }),
      });
      const msg = r.copy_index ? "Профиль и индекс скопированы." : "Профиль создан (пустой индекс).";
      if (confirm(msg + " Перейти?")) location.href = "/kb/profile/" + r.profile;
    } catch (e) {
      alert(e.message);
    }
  });

  el("btn-compare")?.addEventListener("click", async () => {
    const other = el("compare-with").value.trim();
    if (!other) return alert("Укажите профиль для сравнения");
    const pre = el("compare-result");
    const wrap = el("compare-table-wrap");
    pre.classList.remove("hidden");
    try {
      const r = await api("/kb/api/profiles/compare", {
        method: "POST",
        body: JSON.stringify({ profile_a: name, profile_b: other }),
      });
      lastCompareData = { ...r, profile_a: name, profile_b: other };
      let summaryText = JSON.stringify(r.summary, null, 2);
      if (r.bsl?.summary) {
        summaryText +=
          "\n\nBSL:\n" +
          JSON.stringify(r.bsl.summary, null, 2);
        if (r.bsl.changed?.length) {
          summaryText +=
            "\n\nПример diff:\n" + (r.bsl.changed[0].diff_preview || "");
        }
      }
      pre.textContent = summaryText;
      el("btn-compare-export-json")?.classList.remove("hidden");
      el("btn-compare-export-csv")?.classList.remove("hidden");
      if (wrap && (r.changed?.length || r.bsl?.changed?.length)) {
        wrap.classList.remove("hidden");
        const metaRows = (r.changed || [])
          .slice(0, 30)
          .map((row) => {
            const a = row.a || {};
            const b = row.b || {};
            return `<tr><td>${escapeHtml(row.key)}</td><td>meta: ${escapeHtml((row.diff_fields || []).join(", "))}</td>` +
              `<td>${escapeHtml(a.synonym || "")} (${a.attributes_count ?? 0})</td>` +
              `<td>${escapeHtml(b.synonym || "")} (${b.attributes_count ?? 0})</td></tr>`;
          })
          .join("");
        const bslRows = (r.bsl?.changed || [])
          .slice(0, 20)
          .map((row) =>
            `<tr><td>${escapeHtml(row.path)}</td><td>BSL +${row.lines_added}/-${row.lines_removed}</td>` +
              `<td colspan="2"><pre class="diff-preview">${escapeHtml(row.diff_preview || "")}</pre></td></tr>`,
          )
          .join("");
        wrap.innerHTML =
          `<table class="compare-table"><thead><tr><th>Объект / путь</th><th>Изменения</th><th>A</th><th>B</th></tr></thead><tbody>` +
          metaRows +
          bslRows +
          "</tbody></table>";
      } else if (wrap) {
        wrap.classList.add("hidden");
      }
    } catch (e) {
      pre.textContent = e.message;
    }
  });

  async function downloadCompare(fmt) {
    if (!lastCompareData) return alert("Сначала выполните сравнение");
    const res = await fetch("/kb/api/profiles/compare/export", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...apiAuthHeaders() },
      body: JSON.stringify({
        profile_a: lastCompareData.profile_a,
        profile_b: lastCompareData.profile_b,
        format: fmt,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return alert(err.error || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `compare-${lastCompareData.profile_a}-${lastCompareData.profile_b}.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  el("btn-compare-export-json")?.addEventListener("click", () => downloadCompare("json"));
  el("btn-compare-export-csv")?.addEventListener("click", () => downloadCompare("csv"));
}

function initApiSecurityDialog() {
  const dialog = el("dialog-api-security");
  const input = el("api-token-input");
  const saved = sessionStorage.getItem("kb_api_token");
  if (input && saved) input.value = saved;

  el("btn-api-security")?.addEventListener("click", () => {
    refreshApiTokenHint();
    dialog?.showModal();
  });
  dialog?.querySelectorAll("[data-close-api]").forEach((b) =>
    b.addEventListener("click", () => dialog.close())
  );

  el("btn-api-token-save")?.addEventListener("click", () => {
    const value = input?.value?.trim() || "";
    if (value) sessionStorage.setItem("kb_api_token", value);
    else sessionStorage.removeItem("kb_api_token");
    refreshApiTokenHint();
    dialog?.close();
  });

  el("btn-api-token-clear")?.addEventListener("click", () => {
    sessionStorage.removeItem("kb_api_token");
    if (input) input.value = "";
    refreshApiTokenHint();
  });

  refreshKbDockerBadge().then(() => refreshApiTokenHint()).catch(() => {});
}

async function refreshApiTokenHint() {
  const btn = el("btn-api-security");
  if (!btn) return;
  try {
    const s = await api("/kb/api/system");
    if (s.api_token_required && !sessionStorage.getItem("kb_api_token")) {
      btn.classList.add("warn-outline");
    } else {
      btn.classList.remove("warn-outline");
    }
  } catch (_) {}
}

function initDialogScrollLock() {
  function syncBodyLock() {
    document.body.classList.toggle("dialog-open", Boolean(document.querySelector("dialog[open]")));
  }

  function isInsideOpenDialog(target) {
    return Boolean(target?.closest?.("dialog[open]"));
  }

  function blockBackgroundScroll(e) {
    if (!document.querySelector("dialog[open]")) return;
    if (!isInsideOpenDialog(e.target)) e.preventDefault();
  }

  document.addEventListener("wheel", blockBackgroundScroll, { passive: false });
  document.addEventListener("touchmove", blockBackgroundScroll, { passive: false });

  document.querySelectorAll("dialog").forEach((dialog) => {
    dialog.addEventListener("toggle", syncBodyLock);
    dialog.addEventListener("close", syncBodyLock);
  });
}

initDialogScrollLock();
initApiSecurityDialog();

async function loadProfileHealth(name) {
  const tbody = el("profile-health-body");
  const badge = el("health-state-badge");
  if (!tbody) return;
  try {
    const h = await api("/kb/api/profiles/" + name + "/health");
    renderHealthTable(tbody, h.checks);
    if (badge) {
      badge.textContent = h.state || (h.healthy ? "ready" : "degraded");
      badge.className = "step-badge " + (h.healthy ? "success" : "error");
    }
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3">${escapeHtml(e.message)}</td></tr>`;
  }
}
