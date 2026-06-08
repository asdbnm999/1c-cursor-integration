/**
 * §2 Стандартные MCP-серверы
 */

(function () {
  const statusLabels = {
    not_started: "Не начато",
    in_progress: "В процессе",
    ready: "Готово",
  };

  let lastStatus = null;
  let activeServerForErrors = "searxng";
  let deployEventSource = null;
  let deployPollTimer = null;
  let activeDeployJobId = null;
  let activeDeployServer = null;
  let deployUiSettled = true;
  let lastDeployJob = null;
  let lastDeployResult = null;
  let lastDeployResultServer = null;

  function $(id) {
    return document.getElementById(id);
  }

  function syncSliderFill(sl) {
    const min = Number(sl.min);
    const max = Number(sl.max);
    const val = Number(sl.value);
    const pct = max > min ? ((val - min) / (max - min)) * 100 : 0;
    sl.style.setProperty("--pct", `${pct}%`);
  }

  function applyResourceValues(values) {
    Object.entries(values).forEach(([key, val]) => {
      const inp = document.querySelector(`.res-input[data-key="${key}"]`);
      const sl = document.querySelector(`.res-slider[data-key="${key}"]`);
      if (inp) inp.value = val;
      if (sl) {
        sl.value = val;
        syncSliderFill(sl);
      }
    });
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok && !data.message && !data.deploy) {
      throw new Error(data.error || "Ошибка запроса");
    }
    return data;
  }

  function setBadge(status) {
    const badge = $("section-badge");
    if (!badge) return;
    badge.textContent = statusLabels[status] || status;
    badge.className = "card-badge status-" + status;
  }

  function clearMcpBlockHighlights() {
    ["mcp-block-docker-root", "mcp-block-resources", "mcp-block-mcp-json", "mcp-block-diagnostics"].forEach(
      (id) => {
        const el = $(id);
        if (el) el.classList.remove("mcp-block--ready");
      }
    );
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  const DEPLOY_STEP_LABELS = {
    pull: "Загрузка образов",
    build: "Сборка",
    up: "Запуск контейнеров",
    clone: "Клонирование репозитория",
    patch: "Патч MCP",
    health: "Health-check",
    mcp_protocol: "MCP протокол",
    container: "Статус контейнера",
  };

  function deployStepStatus(step) {
    const name = step.step || step.action || "";
    if (name === "clone") return step.status === "error" ? "failed" : "ok";
    if (name === "patch") return step.status === "error" ? "failed" : "ok";
    if (name === "container") return step.running ? "ok" : "failed";
    if (name === "mcp_protocol") {
      if ((step.ping || {}).ok === false || (step.cancelled || {}).ok === false) return "failed";
      if (step.index && step.index.ok === false) return "failed";
      return "ok";
    }
    if (step.ok === false) return "failed";
    if (step.ok === true) return "ok";
    return "skipped";
  }

  function deployStepDetail(step) {
    const name = step.step || step.action || "";
    if (step.message && step.message !== "OK") return step.message;
    if (name === "clone") {
      if (step.status === "exists") return "Уже есть локально";
      if (step.status === "cloned") return "Склонирован";
      if (step.status === "error") return step.message || "Ошибка";
      return step.status || "";
    }
    if (name === "patch") return step.status === "error" ? step.message || "Ошибка" : "Применён";
    if (name === "health") {
      if (step.ok) return step.url ? `${step.url} → HTTP ${step.status_code || 200}` : "OK";
      return step.error || "Не ответил";
    }
    if (name === "container") return step.detail || (step.running ? "running" : "не запущен");
    if (name === "mcp_protocol") {
      const bits = [];
      if (step.ping) bits.push(`ping: ${step.ping.ok ? "OK" : step.ping.detail || "ошибка"}`);
      if (step.cancelled) bits.push(`cancel: ${step.cancelled.ok ? "OK" : step.cancelled.detail || "ошибка"}`);
      if (step.index) bits.push(`index: ${step.index.ok ? "готов" : step.index.error || "ожидание"}`);
      return bits.join(" · ") || "OK";
    }
    if (step.error) return step.error;
    return step.message || "OK";
  }

  function formatDeployReport(res) {
    const deploy = res.deploy || {};
    const steps = deploy.steps || [];
    const lines = [];

    steps.forEach((step) => {
      const label = DEPLOY_STEP_LABELS[step.step] || step.step || step.action || "Шаг";
      const status = deployStepStatus(step);
      const icon = status === "ok" ? "✓" : status === "failed" ? "✗" : "–";
      const detail = deployStepDetail(step);
      lines.push(
        `<div class="report-line report-${status === "failed" ? "failed" : status}">` +
          `<strong>${icon}</strong> ${escapeHtml(label)}` +
          (detail ? `<span class="deploy-step-detail">${escapeHtml(detail)}</span>` : "") +
          `</div>`
      );
    });

    if (res.mcp_apply) {
      const ma = res.mcp_apply;
      const maMsg = ma.ok ? "mcp.json обновлён" : ma.message || "Ошибка обновления mcp.json";
      lines.push(
        `<div class="report-line report-${ma.ok ? "ok" : "failed"}">` +
          `<strong>${ma.ok ? "✓" : "✗"}</strong> Cursor MCP` +
          `<span class="deploy-step-detail">${escapeHtml(maMsg)}</span>` +
          `</div>`
      );
    }

    const extras = [];
    if (deploy.mcp_url) {
      extras.push(`<p class="deploy-meta">MCP: <code>${escapeHtml(deploy.mcp_url)}</code></p>`);
    }
    if (res.refresh_hint) {
      extras.push(`<p class="hint deploy-hint">${escapeHtml(res.refresh_hint)}</p>`);
    }

    const hasFailedStep = steps.some((step) => deployStepStatus(step) === "failed");
    const deployOk = deploy.ok !== false;
    const overallOk = res.ok !== false && deployOk && !hasFailedStep;
    const mainMsg =
      deploy.message || res.message || (overallOk ? "Deploy завершён" : "Deploy с ошибками — см. шаги");
    let html = extras.join("");
    if (lines.length) {
      html += `<div class="deploy-steps">${lines.join("")}</div>`;
    } else if (res.message) {
      html += `<p class="hint">${escapeHtml(res.message)}</p>`;
    }

    return {
      message: mainMsg,
      summaryClass: overallOk ? "deploy-summary-ok" : "deploy-summary-fail",
      html,
      raw: JSON.stringify(res, null, 2),
    };
  }

  function stopDeployStream() {
    if (deployEventSource) {
      deployEventSource.close();
      deployEventSource = null;
    }
    if (deployPollTimer) {
      clearInterval(deployPollTimer);
      deployPollTimer = null;
    }
  }

  function setDeployButtonsDisabled(disabled) {
    document.querySelectorAll(".btn-deploy").forEach((btn) => {
      btn.disabled = disabled;
    });
  }

  function serverDeployed(data, server) {
    const srv = (data?.servers || []).find((s) => s.slug === server);
    return !!(srv?.container?.running || srv?.ready || srv?.deployed);
  }

  async function refreshAfterDeploy(server) {
    const attempts = 12;
    let data = null;
    for (let i = 0; i < attempts; i += 1) {
      data = await refresh();
      if (serverDeployed(data, server)) return data;
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    return data || refresh();
  }

  function deployBox(server) {
    return document.querySelector(`.server-panel[data-slug="${server}"] .server-deploy-box`);
  }

  function renderDeployProgress(server, job) {
    const box = deployBox(server);
    if (!box || !job) return;

    const terminal = job.status === "completed" || job.status === "failed";
    box.classList.toggle("is-done", terminal);
    box.classList.remove("hidden");

    const msgEl = box.querySelector(".deploy-inline-message");
    if (msgEl) {
      if (terminal) {
        msgEl.textContent = job.error || job.progress_message || "";
        msgEl.className =
          "deploy-inline-message deploy-summary " + (job.status === "completed" ? "deploy-summary-ok" : "deploy-summary-fail");
      } else {
        msgEl.textContent = "";
        msgEl.className = "deploy-inline-message";
      }
    }

    const fill = box.querySelector(".deploy-progress-fill");
    const pctEl = box.querySelector(".deploy-progress-pct");
    const stepEl = box.querySelector(".deploy-progress-step");
    const bars = box.querySelector(".deploy-step-bars");
    const head = box.querySelector(".deploy-progress-head");
    const bar = box.querySelector(".deploy-progress-bar");

    if (!terminal) {
      head?.classList.remove("hidden");
      bar?.classList.remove("hidden");
      bars?.classList.remove("hidden");
      if (pctEl) pctEl.textContent = `${job.percent || 0}%`;
      if (stepEl) stepEl.textContent = job.progress_message || "";
      if (fill) fill.style.width = `${job.percent || 0}%`;
    } else if (fill) {
      fill.style.width = "100%";
    }

    if (bars && Array.isArray(job.steps) && !terminal) {
      bars.innerHTML = job.steps
        .map((step) => {
          const status = step.status || "pending";
          const rowClass =
            status === "done"
              ? "step-done"
              : status === "failed"
                ? "step-failed"
                : status === "running"
                  ? "step-running"
                  : "";
          const detail = step.detail
            ? `<span class="step-detail">${escapeHtml(step.detail)}</span>`
            : "";
          return (
            `<div class="deploy-step-row ${rowClass}">` +
            `<span class="step-label">${escapeHtml(step.label || step.id)}</span>` +
            `<div class="step-bar" aria-hidden="true"><div class="step-bar-fill"></div></div>` +
            detail +
            `</div>`
          );
        })
        .join("");
    }
  }

  function showDeployResult(server, res) {
    const box = deployBox(server);
    if (!box) return;
    const report = formatDeployReport(res);
    box.classList.remove("hidden");
    box.classList.add("is-done");

    const msgEl = box.querySelector(".deploy-inline-message");
    if (msgEl) {
      msgEl.textContent = report.message;
      msgEl.className = "deploy-inline-message deploy-summary " + report.summaryClass;
    }

    const details = box.querySelector(".deploy-inline-details");
    const reportEl = box.querySelector(".deploy-inline-report");
    if (details && reportEl) {
      reportEl.innerHTML = report.html || "";
      details.classList.toggle("hidden", !report.html);
      details.open = !res.ok;
    }

    box.querySelector(".deploy-progress-head")?.classList.add("hidden");
    box.querySelector(".deploy-progress-bar")?.classList.add("hidden");
    box.querySelector(".deploy-step-bars")?.classList.add("hidden");
  }

  function openDeployProgress(server) {
    stopDeployStream();
    lastDeployResult = null;
    lastDeployResultServer = null;
    lastDeployJob = {
      status: "running",
      percent: 0,
      progress_message: "Подготовка…",
      steps: [],
    };
    const box = deployBox(server);
    if (box) {
      box.classList.remove("is-done", "hidden");
      const msg = box.querySelector(".deploy-inline-message");
      const report = box.querySelector(".deploy-inline-report");
      if (msg) msg.textContent = "";
      if (report) report.innerHTML = "";
      box.querySelector(".deploy-inline-details")?.classList.add("hidden");
      box.querySelector(".deploy-progress-head")?.classList.remove("hidden");
      box.querySelector(".deploy-progress-bar")?.classList.remove("hidden");
      box.querySelector(".deploy-step-bars")?.classList.remove("hidden");
    }
    renderDeployProgress(server, lastDeployJob);
  }

  function restoreDeployUi() {
    if (activeDeployServer && !deployUiSettled && lastDeployJob) {
      renderDeployProgress(activeDeployServer, lastDeployJob);
      return;
    }
    if (lastDeployResultServer && lastDeployResult) {
      showDeployResult(lastDeployResultServer, lastDeployResult);
    }
  }

  async function finishDeployJob(job) {
    if (deployUiSettled) return;
    deployUiSettled = true;
    stopDeployStream();
    activeDeployJobId = null;

    const server = activeDeployServer || job.server;
    const box = deployBox(server);
    if (box) {
      const msgEl = box.querySelector(".deploy-inline-message");
      if (msgEl) {
        msgEl.textContent = "Обновление статуса…";
        msgEl.className = "deploy-inline-message deploy-summary";
      }
    }

    try {
      await refreshAfterDeploy(server);
    } catch (e) {
      console.error(e);
    } finally {
      setDeployButtonsDisabled(false);
      activeDeployServer = null;
    }

    const result = job.result || {
      ok: job.status === "completed",
      message: job.error || job.progress_message || "Deploy завершён",
    };
    lastDeployResult = result;
    lastDeployResultServer = server;
    showDeployResult(server, result);
    if (result.refresh_hint) {
      $("mcp-refresh-hint")?.classList.remove("hidden");
    }
  }

  function onDeployJobUpdate(job) {
    if (!job || deployUiSettled) return;
    lastDeployJob = job;
    const server = activeDeployServer || job.server;
    if (job.status === "running" || job.status === "pending") {
      renderDeployProgress(server, job);
      return;
    }
    if (job.status === "completed" || job.status === "failed") {
      finishDeployJob(job);
    }
  }

  function scheduleDeployPolling(jobId) {
    if (deployPollTimer) return;
    pollDeployJob(jobId);
    deployPollTimer = setInterval(() => pollDeployJob(jobId), 1500);
  }

  function startDeployStream(jobId) {
    stopDeployStream();
    activeDeployJobId = jobId;
    deployUiSettled = false;
    if (typeof EventSource !== "undefined") {
      deployEventSource = new EventSource(`/mcp/api/deploy/jobs/${jobId}/stream`);
      deployEventSource.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data.job) onDeployJobUpdate(data.job);
        } catch (_) {}
      };
      deployEventSource.onerror = () => {
        if (deployUiSettled) {
          stopDeployStream();
          return;
        }
        stopDeployStream();
        scheduleDeployPolling(jobId);
      };
      return;
    }
    scheduleDeployPolling(jobId);
  }

  async function pollDeployJob(jobId) {
    if (deployUiSettled) {
      stopDeployStream();
      return;
    }
    try {
      const data = await api(`/mcp/api/deploy/jobs/${jobId}`);
      if (data.job) onDeployJobUpdate(data.job);
    } catch (e) {
      console.error(e);
    }
  }

  function serverCard(srv) {
    const hbkBlock =
      srv.slug === "1c-syntax-helper"
        ? `<div class="field-row">
            <input type="text" class="text-input hbk-path${srv.needs_hbk ? " input-required" : ""}" data-server="${srv.slug}" value="${escapeHtml(srv.hbk_path || "")}" placeholder="Путь к shcntx_ru.hbk">
            <button type="button" class="btn btn-pick-hbk" data-server="${srv.slug}">Выбрать HBK…</button>
          </div>`
        : "";
    const deployDisabled = srv.slug === "1c-syntax-helper" && srv.needs_hbk;
    const deployTitle = deployDisabled ? ' title="Сначала укажите shcntx_ru.hbk"' : "";
    const containerRunning = !!(srv.container || {}).running;
    const deployBtn = containerRunning
      ? ""
      : `<button type="button" class="btn btn-primary btn-deploy" data-server="${srv.slug}"${deployDisabled ? " disabled" : ""}${deployTitle}>Deploy (up -d)</button>`;
    const corePort =
      srv.slug === "searxng"
        ? `<label>Порт Core <input type="number" class="text-input port-core" data-server="${srv.slug}" value="${srv.host_port_core || 8202}" min="1024" max="65535"></label>`
        : "";
    const container = srv.container || {};
    const containerUp =
      container.running && (container.health === "healthy" || container.health === "none");
    const mcpSynced = srv.in_mcp_json && srv.mcp_json_url === srv.mcp_url;
    const titleReady = containerUp || srv.ready;
    const statusBadge = titleReady
      ? '<span class="server-status-badge status-ready">Готово</span>'
      : container.running
        ? '<span class="server-status-badge status-in_progress">Запущен</span>'
        : '<span class="server-status-badge">Не запущен</span>';
    const mcpStaleLine = srv.port_mismatch
      ? `<p class="hint cell-warn">Контейнер на порту <code>${srv.host_port_published}</code>, в настройках <code>${srv.host_port_mcp}</code> — остановите стек и Deploy, чтобы порты совпали</p>`
      : containerUp && srv.in_mcp_json && srv.mcp_json_url && !mcpSynced
        ? `<p class="hint cell-warn">В mcp.json указан другой URL: <code>${escapeHtml(srv.mcp_json_url)}</code> — нажмите «Применить в mcp.json» ниже</p>`
        : "";
    const contLine = `Контейнер ${escapeHtml(srv.stack_name)}: ${escapeHtml(container.detail || "—")}`;

    const panelReadyClass = srv.ready ? " mcp-block--ready" : "";
    return `
      <section class="panel mcp-block server-panel${panelReadyClass}" data-slug="${srv.slug}">
        <div class="server-panel-head">
          <h2 class="server-title">${escapeHtml(srv.title)}</h2>
          ${statusBadge}
        </div>
        <p class="hint">${escapeHtml(srv.why)}</p>
        <p class="hint small">MCP tools: <code>${escapeHtml(srv.tools)}</code></p>
        <p class="runtime-line">${contLine}</p>
        <p class="runtime-line">MCP URL: <code>${escapeHtml(srv.mcp_url)}</code> · ключ mcp.json: <code>${escapeHtml(srv.mcp_key)}</code></p>
        ${mcpStaleLine}
        <div class="field-row">
          <input type="text" class="text-input compose-dir" data-server="${srv.slug}" value="${escapeHtml(srv.compose_dir || "")}" placeholder="Каталог compose">
          <button type="button" class="btn btn-pick-compose" data-server="${srv.slug}">Выбрать каталог…</button>
        </div>
        <div class="field-row port-row">
          <label>Порт MCP <input type="number" class="text-input port-mcp" data-server="${srv.slug}" value="${srv.host_port_mcp}" min="1024" max="65535"></label>
          ${corePort}
        </div>
        ${hbkBlock}
        <div class="server-deploy-box hidden" data-server="${srv.slug}">
          <p class="deploy-inline-message"></p>
          <div class="deploy-progress-head">
            <span class="deploy-progress-pct">0%</span>
            <span class="deploy-progress-step muted"></span>
          </div>
          <div class="progress-bar deploy-progress-bar" aria-hidden="true">
            <div class="progress-fill deploy-progress-fill"></div>
          </div>
          <div class="deploy-step-bars"></div>
          <details class="deploy-inline-details hidden">
            <summary>Шаги deploy</summary>
            <div class="deploy-inline-report deploy-report"></div>
          </details>
        </div>
        <div class="field-row actions-row">
          ${deployBtn}
          <button type="button" class="btn btn-stop" data-server="${srv.slug}">Остановить</button>
          <button type="button" class="btn btn-ghost btn-logs" data-server="${srv.slug}">Логи</button>
        </div>
      </section>`;
  }

  function renderServers(servers) {
    const anchor = $("mcp-block-mcp-json");
    if (!anchor || !anchor.parentNode) return;
    document.querySelectorAll(".server-panel").forEach((el) => el.remove());
    const fragment = document.createDocumentFragment();
    servers.forEach((srv) => {
      const wrap = document.createElement("div");
      wrap.innerHTML = serverCard(srv);
      const panel = wrap.firstElementChild;
      if (panel) fragment.appendChild(panel);
    });
    anchor.parentNode.insertBefore(fragment, anchor);
    bindServerEvents();
    restoreDeployUi();
  }

  function renderWarnings(data) {
    const legacy = $("mcp-legacy-banner");
    if (legacy) {
      if (data.legacy_compose) {
        legacy.textContent =
          "Обнаружен устаревший " +
          (data.legacy_compose_path || "~/DockerMCP/docker-compose.yml") +
          ". Используйте отдельные каталоги searxng/ и 1c-syntax/.";
        legacy.classList.remove("hidden");
      } else {
        legacy.classList.add("hidden");
      }
    }
    const docker = $("mcp-docker-banner");
    if (docker && data.docker) {
      if (!data.docker.running) {
        docker.textContent = data.docker.message || "Docker daemon недоступен";
        docker.classList.remove("hidden");
      } else {
        docker.classList.add("hidden");
      }
    }
    const ports = $("mcp-port-warnings");
    if (ports && data.port_registry) {
      const busy = data.port_registry.filter((p) => !p.free);
      if (busy.length) {
        ports.innerHTML = busy
          .map((p) => `<div class="warning-item">Порт ${p.port} занят (${escapeHtml(p.role)})</div>`)
          .join("");
        ports.classList.remove("hidden");
      } else {
        ports.classList.add("hidden");
      }
    }
    const rootLine = $("docker-root-line");
    if (rootLine && data.docker) {
      rootLine.textContent = `Docker root: ${data.docker.docker_root || "—"} · ${data.docker.message || ""}`;
    }
    const cfgPath = $("mcp-config-path");
    if (cfgPath && data.mcp_config) {
      cfgPath.textContent = `mcp.json: ${data.mcp_config.config_path}`;
    }
  }

  function renderResourceSliders(presets, limits) {
    const grid = $("resource-sliders");
    if (!grid || grid.querySelector(".res-slider")) return;
    const keys = [
      ["valkey_mem", "Valkey"],
      ["core_mem", "SearXNG core"],
      ["searxng_mcp_mem", "SearXNG MCP"],
      ["es_heap", "ES heap"],
      ["syntax_mcp_mem", "Syntax MCP"],
    ];
    grid.innerHTML = keys
      .map(([key, label]) => {
        const lim = limits[key] || limits.es_heap;
        const max = lim ? lim.max : 2048;
        const min = lim ? lim.min : 64;
        const val = (presets.economical && presets.economical[key]) || min;
        return `<label class="slider-row">${label}
          <input type="range" class="res-slider" data-key="${key}" min="${min}" max="${max}" value="${val}">
          <input type="number" class="text-input res-input" data-key="${key}" min="${min}" max="${max}" value="${val}" style="width:5rem">
          <span class="muted">MB</span></label>`;
      })
      .join("");
    grid.querySelectorAll(".res-slider").forEach((sl) => {
      syncSliderFill(sl);
      sl.addEventListener("input", () => {
        syncSliderFill(sl);
        const inp = grid.querySelector(`.res-input[data-key="${sl.dataset.key}"]`);
        if (inp) inp.value = sl.value;
      });
    });
    grid.querySelectorAll(".res-input").forEach((inp) => {
      inp.addEventListener("change", () => {
        const sl = grid.querySelector(`.res-slider[data-key="${inp.dataset.key}"]`);
        if (sl) {
          sl.value = inp.value;
          syncSliderFill(sl);
        }
      });
    });
  }

  function collectResources() {
    const resources = {};
    document.querySelectorAll(".res-input").forEach((inp) => {
      resources[inp.dataset.key] = parseInt(inp.value, 10) || 0;
    });
    return resources;
  }

  async function saveServerSettings(server, extra) {
    const preset = $("resource-preset")?.value || "economical";
    const body = {
      server,
      resource_preset: preset,
      resources: collectResources(),
      compose_dir: document.querySelector(`.compose-dir[data-server="${server}"]`)?.value || "",
      ...extra,
    };
    if (extra.userPortEdit) {
      body.host_port_mcp = parseInt(
        document.querySelector(`.port-mcp[data-server="${server}"]`)?.value,
        10
      );
      body.host_port_mcp_user_edit = true;
    }
    const core = document.querySelector(`.port-core[data-server="${server}"]`);
    if (core) body.host_port_core = parseInt(core.value, 10);
    const hbk = document.querySelector(`.hbk-path[data-server="${server}"]`);
    if (hbk) body.hbk_path = hbk.value;
    return api("/mcp/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  async function refresh() {
    const data = await api("/mcp/api/status");
    lastStatus = data;
    setBadge(data.section_status);
    renderServers(data.servers || []);
    renderWarnings(data);
    clearMcpBlockHighlights();
    if (data.resource_presets && data.resource_limits) {
      renderResourceSliders(data.resource_presets, data.resource_limits);
    }
    return data;
  }

  function bindServerEvents() {
    document.querySelectorAll(".hbk-path").forEach((input) => {
      input.addEventListener("change", () => saveServerSettings(input.dataset.server, {}).then(refresh));
    });
    document.querySelectorAll(".port-mcp").forEach((input) => {
      input.addEventListener("change", () =>
        saveServerSettings(input.dataset.server, { userPortEdit: true }).then(refresh)
      );
    });
    document.querySelectorAll(".btn-deploy").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const server = btn.dataset.server;
        if (server === "1c-syntax-helper") {
          const hbk = document.querySelector('.hbk-path[data-server="1c-syntax-helper"]');
          if (!hbk?.value.trim()) {
            alert("Укажите путь к shcntx_ru.hbk — файл справки обязателен перед Deploy.");
            hbk?.focus();
            return;
          }
          const syntaxSrv = (lastStatus?.servers || []).find((s) => s.slug === "1c-syntax-helper");
          if (syntaxSrv?.needs_hbk) {
            alert(
              syntaxSrv.hbk_path
                ? "Файл shcntx_ru.hbk не найден по указанному пути. Проверьте путь и повторите Deploy."
                : "Укажите путь к shcntx_ru.hbk — файл справки обязателен перед Deploy."
            );
            hbk?.focus();
            return;
          }
        }
        await saveServerSettings(server, {});
        activeDeployServer = server;
        deployUiSettled = false;
        setDeployButtonsDisabled(true);
        openDeployProgress(server);
        try {
          const res = await api("/mcp/api/deploy", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ server }),
          });
          if (res.job_id) {
            if (res.job) {
              lastDeployJob = res.job;
              renderDeployProgress(server, res.job);
            }
            startDeployStream(res.job_id);
          } else {
            deployUiSettled = true;
            activeDeployServer = null;
            setDeployButtonsDisabled(false);
            await refreshAfterDeploy(server);
            lastDeployResult = res;
            lastDeployResultServer = server;
            showDeployResult(server, res);
            if (res.refresh_hint) $("mcp-refresh-hint")?.classList.remove("hidden");
          }
        } catch (e) {
          deployUiSettled = true;
          activeDeployServer = null;
          activeDeployJobId = null;
          setDeployButtonsDisabled(false);
          stopDeployStream();
          deployBox(server)?.classList.add("hidden");
          alert(e.message);
        }
      });
    });
    document.querySelectorAll(".btn-stop").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Остановить стек " + btn.dataset.server + "?")) return;
        await api("/mcp/api/stop", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ server: btn.dataset.server }),
        });
        refresh();
      });
    });
    document.querySelectorAll(".btn-logs").forEach((btn) => {
      btn.addEventListener("click", async () => {
        activeServerForErrors = btn.dataset.server;
        const res = await api("/mcp/api/logs?server=" + encodeURIComponent(btn.dataset.server));
        const dlg = $("errors-dialog");
        $("errors-logs").textContent = res.logs || res.message || "";
        dlg?.showModal();
        loadErrorsCatalog(btn.dataset.server);
      });
    });
    document.querySelectorAll(".btn-pick-compose").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const res = await api("/mcp/api/pick-compose-dir", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ server: btn.dataset.server }),
        });
        if (!res.cancelled) refresh();
      });
    });
    document.querySelectorAll(".btn-pick-hbk").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const res = await api("/mcp/api/pick-hbk", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        if (!res.cancelled) refresh();
      });
    });
  }

  async function loadErrorsCatalog(server) {
    const res = await api("/mcp/api/errors?server=" + encodeURIComponent(server));
    const staticBox = $("errors-static");
    const matchedBox = $("errors-matched");
    if (staticBox) {
      staticBox.innerHTML = (res.static || [])
        .map(
          (e) =>
            `<div class="error-card"><strong>${escapeHtml(e.title || e.symptom)}</strong><p>${escapeHtml(e.cause || "")}</p><p class="cell-ok">${escapeHtml(e.fix || "")}</p></div>`
        )
        .join("");
    }
    if (matchedBox) {
      matchedBox.innerHTML = (res.matched || []).length
        ? (res.matched || [])
            .map((e) => `<div class="error-card matched">${escapeHtml(e.title || e.symptom)}</div>`)
            .join("")
        : '<p class="hint">Совпадений в логах не найдено</p>';
    }
    if ($("errors-logs") && res.logs_excerpt) {
      $("errors-logs").textContent = res.logs_excerpt;
    }
  }

  $("btn-preview-mcp")?.addEventListener("click", async () => {
    const res = await api("/mcp/api/preview-mcp", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const pre = $("mcp-diff");
    if (pre) {
      pre.textContent = res.diff || JSON.stringify(res, null, 2);
      pre.classList.remove("hidden");
    }
  });

  $("btn-apply-mcp")?.addEventListener("click", async () => {
    try {
      const res = await api("/mcp/api/apply-mcp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const pre = $("mcp-diff");
      if (pre) {
        pre.textContent = res.diff || res.message || "";
        pre.classList.remove("hidden");
      }
      if (!res.ok) {
        alert(res.message || "Не удалось применить mcp.json");
        return;
      }
      if (res.warnings?.length) {
        alert(res.warnings.join("\n\n"));
      }
      $("mcp-refresh-hint")?.classList.remove("hidden");
      refresh();
    } catch (e) {
      alert(e.message);
    }
  });

  $("btn-check-orphans")?.addEventListener("click", async () => {
    const res = await api("/mcp/api/orphans");
    const box = $("orphans-report");
    if (!box) return;
    const rows = res.orphans || [];
    box.innerHTML = rows.length
      ? rows.map((r) => `<div class="report-line">${escapeHtml(r.name)} — ${escapeHtml(r.status)}</div>`).join("")
      : '<p class="hint">Осиротевших контейнеров SearXNG не найдено</p>';
    box.classList.remove("hidden");
  });

  $("btn-errors")?.addEventListener("click", () => {
    $("errors-dialog")?.showModal();
    loadErrorsCatalog($("errors-server")?.value || "searxng");
  });

  $("btn-reload-errors")?.addEventListener("click", () => {
    loadErrorsCatalog($("errors-server")?.value || activeServerForErrors);
  });

  $("errors-server")?.addEventListener("change", (e) => {
    loadErrorsCatalog(e.target.value);
  });

  $("resource-preset")?.addEventListener("change", (e) => {
    const preset = e.target.value;
    if (preset === "manual" || !lastStatus?.resource_presets?.[preset]) return;
    applyResourceValues(lastStatus.resource_presets[preset]);
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (!deployUiSettled && activeDeployJobId) {
      pollDeployJob(activeDeployJobId);
      return;
    }
    refresh().catch((e) => console.error(e));
  });

  refresh().catch((e) => console.error(e));
})();
