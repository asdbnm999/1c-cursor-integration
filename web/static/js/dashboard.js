(function () {
  "use strict";

  const healthTable = document.getElementById("health-table");
  const healthBody = document.getElementById("health-table-body");
  const warningsBox = document.getElementById("system-warnings");
  const mcpSummary = document.getElementById("mcp-status-summary");
  const mcpConfigPath = document.getElementById("mcp-config-path");
  const mcpTable = document.getElementById("mcp-table");
  const mcpBody = document.getElementById("mcp-table-body");
  const btnCheckMcp = document.getElementById("btn-check-mcp");
  const btnRefreshSystem = document.getElementById("btn-refresh-system");
  const btnExportSettings = document.getElementById("btn-export-settings");
  const importSettingsFile = document.getElementById("import-settings-file");
  const settingsIoMessage = document.getElementById("settings-io-message");
  const summaryPill = document.getElementById("sections-summary-pill");
  const wizardSteps = document.getElementById("wizard-steps");

  const STATUS_LABELS = {
    not_started: "Не начато",
    in_progress: "В процессе",
    ready: "Готово",
  };

  function healthLabel(code) {
    const map = {
      ok: "OK",
      unreachable: "Недоступен",
      unknown: "Не проверен",
      error: "Ошибка",
    };
    return map[code] || code;
  }

  function rowStatusClass(ok) {
    return ok ? "cell-ok" : "cell-warn";
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function renderWarnings(warnings) {
    if (!warningsBox) return;
    if (!warnings || !warnings.length) {
      warningsBox.classList.add("hidden");
      warningsBox.innerHTML = "";
      return;
    }
    warningsBox.innerHTML = warnings
      .map(function (w) {
        return '<div class="warning-item">' + escapeHtml(w) + "</div>";
      })
      .join("");
    warningsBox.classList.remove("hidden");
  }

  function updateCardBadge(cardEl, status) {
    if (!cardEl) return;
    const badge = cardEl.querySelector("[data-status-badge]");
    if (badge) {
      badge.className = "card-badge status-" + status;
      badge.textContent = STATUS_LABELS[status] || status;
    }
    cardEl.classList.remove(
      "card-status-not_started",
      "card-status-in_progress",
      "card-status-ready"
    );
    cardEl.classList.add("card-status-" + status);
  }

  function renderSectionsSnapshot(data) {
    if (!data) return;
    const cards = data.cards || [];
    cards.forEach(function (card) {
      const el = document.getElementById("card-" + card.id);
      updateCardBadge(el, card.status);
    });

    if (summaryPill && data.summary) {
      summaryPill.textContent =
        data.summary.ready_count + " / " + data.summary.total + " готово";
    }

    if (wizardSteps && data.wizard_steps) {
      data.wizard_steps.forEach(function (step) {
        const li = wizardSteps.querySelector('[data-section="' + step.id + '"]');
        if (!li) return;
        li.className = "wizard-step wizard-step--" + step.status;
        const marker = li.querySelector(".wizard-step-marker");
        if (marker) marker.textContent = step.done ? "✓" : String(step.index);
        const badge = li.querySelector(".wizard-step-badge");
        if (badge) {
          badge.className = "wizard-step-badge status-" + step.status;
          badge.textContent = step.status_label;
        }
      });
    }
  }

  function formatRamEstimate(ram) {
    if (!ram || !ram.total_mb) return null;
    const summary =
      "~" +
      ram.total_mb +
      " MiB (пресет «" +
      (ram.preset || "economical") +
      "»)";
    const stacks = (ram.breakdown || []).map(function (b) {
      return { label: b.stack, mb: b.estimate_mb };
    });
    const ok = !ram.docker_limit_mb || ram.total_mb <= ram.docker_limit_mb;
    return { summary: summary, stacks: stacks, ok: ok };
  }

  function appendHealthRow(tbody, label, value, ok) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      "<td>" +
      escapeHtml(label) +
      '</td><td class="mono">' +
      escapeHtml(String(value)) +
      '</td><td class="' +
      rowStatusClass(ok) +
      '">' +
      (ok ? "✓" : "⚠") +
      "</td>";
    tbody.appendChild(tr);
  }

  function appendRamEstimateRows(tbody, ramRow) {
    const stacks = ramRow.stacks || [];
    const rowSpan = 1 + stacks.length;
    const statusCell =
      '<td class="' +
      rowStatusClass(ramRow.ok) +
      '"' +
      (stacks.length ? ' rowspan="' + rowSpan + '"' : "") +
      ">" +
      (ramRow.ok ? "✓" : "⚠") +
      "</td>";

    const mainTr = document.createElement("tr");
    mainTr.innerHTML =
      "<td" +
      (stacks.length ? ' rowspan="' + rowSpan + '"' : "") +
      ">RAM MCP-стеков</td>" +
      '<td class="mono ram-estimate-summary">' +
      escapeHtml(ramRow.summary) +
      "</td>" +
      statusCell;
    tbody.appendChild(mainTr);

    stacks.forEach(function (s) {
      const tr = document.createElement("tr");
      tr.className = "data-table-subrow";
      tr.innerHTML =
        '<td class="ram-stack-row">' +
        '<span class="mono ram-stack-name">' +
        escapeHtml(s.label) +
        '</span><span class="mono ram-stack-size">' +
        s.mb +
        " MiB</span></td>";
      tbody.appendChild(tr);
    });
  }

  function renderSystem(data) {
    const py = data.python || {};
    const docker = data.docker || {};
    const mem = data.memory || {};
    const ramRow = formatRamEstimate(data.ram_estimate);

    if (healthBody && healthTable) {
      healthBody.innerHTML = "";
      [
        ["Python", py.version + " (" + py.implementation + ")", py.ok],
        ["Docker", docker.message || "—", docker.running],
        ["Docker RAM", docker.memory_human || "—", docker.running],
        ["Хост RAM", mem.total_human || "—", true],
      ].forEach(function (r) {
        appendHealthRow(healthBody, r[0], r[1], r[2]);
      });
      if (ramRow) {
        appendRamEstimateRows(healthBody, ramRow);
      }
      appendHealthRow(
        healthBody,
        "Legacy compose",
        docker.legacy_compose_detected ? docker.legacy_compose_path : "не обнаружен",
        !docker.legacy_compose_detected
      );
      healthTable.classList.remove("hidden");
    }

    renderWarnings(data.warnings || []);
    if (typeof window.setDockerStatusFromSystem === "function") {
      window.setDockerStatusFromSystem(data);
    }
  }

  function renderMcp(data, checked) {
    if (mcpConfigPath) mcpConfigPath.textContent = data.config_path || "—";

    const servers = data.servers || {};
    const names = Object.keys(servers);
    if (mcpSummary) {
      if (!names.length) {
        mcpSummary.textContent = "В mcp.json нет серверов 1C:Cursor (или файл не создан).";
      } else if (checked) {
        mcpSummary.textContent =
          "Проверено серверов: " + names.length + " · " + (data.summary || "");
      } else {
        mcpSummary.textContent =
          "Настроено серверов: " + names.length + ". Нажмите «Проверить MCP».";
      }
    }

    if (mcpBody && mcpTable) {
      mcpBody.innerHTML = "";
      names.forEach(function (name) {
        const s = servers[name];
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          escapeHtml(name) +
          '</td><td class="mono">' +
          escapeHtml(s.url || "") +
          '</td><td class="' +
          rowStatusClass(s.health === "ok") +
          '">' +
          healthLabel(s.health || "unknown") +
          (s.latency_ms != null ? " (" + s.latency_ms + " ms)" : "") +
          '</td><td class="mono small">' +
          escapeHtml(s.detail || "") +
          "</td>";
        mcpBody.appendChild(tr);
      });
      mcpTable.classList.toggle("hidden", !names.length);
    }
  }

  function showSettingsMessage(text, isError) {
    if (!settingsIoMessage) return;
    settingsIoMessage.textContent = text;
    settingsIoMessage.classList.toggle("cell-warn", !!isError);
    settingsIoMessage.classList.remove("hidden");
  }

  async function loadSystem() {
    const res = await fetch("/api/system");
    if (!res.ok) throw new Error("system API");
    return res.json();
  }

  async function loadMcpStatus(withHealth) {
    const res = withHealth
      ? await fetch("/api/mcp/check", { method: "POST" })
      : await fetch("/api/mcp/status");
    if (!res.ok) throw new Error("mcp API");
    return res.json();
  }

  async function loadSections(refresh) {
    const q = refresh ? "1" : "0";
    const res = await fetch("/api/sections/status?refresh=" + q);
    if (!res.ok) throw new Error("sections API");
    return res.json();
  }

  function scheduleSectionsRefresh() {
    const run = async function () {
      try {
        renderSectionsSnapshot(await loadSections(true));
      } catch (_) {
        /* keep last snapshot */
      }
    };
    if (typeof window.requestIdleCallback === "function") {
      window.requestIdleCallback(function () {
        run();
      }, { timeout: 4000 });
    } else {
      setTimeout(run, 2000);
    }
  }

  async function init() {
    const tasks = [
      loadSections(false).then(function (data) {
        renderSectionsSnapshot(data);
      }),
      loadSystem().then(function (data) {
        renderSystem(data);
      }),
      loadMcpStatus(false).then(function (data) {
        renderMcp(data, false);
      }),
    ];
    await Promise.allSettled(tasks);
    scheduleSectionsRefresh();
  }

  if (btnCheckMcp) {
    btnCheckMcp.addEventListener("click", async function () {
      btnCheckMcp.disabled = true;
      btnCheckMcp.textContent = "Проверка…";
      try {
        renderMcp(await loadMcpStatus(true), true);
      } catch (_) {
        if (mcpSummary) mcpSummary.textContent = "Ошибка проверки MCP.";
      } finally {
        btnCheckMcp.disabled = false;
        btnCheckMcp.textContent = "Проверить MCP";
      }
    });
  }

  if (btnRefreshSystem) {
    btnRefreshSystem.addEventListener("click", async function () {
      btnRefreshSystem.disabled = true;
      try {
        renderSystem(await loadSystem());
        renderSectionsSnapshot(await loadSections(true));
      } catch (_) {
        if (healthSummary) healthSummary.textContent = "Ошибка обновления.";
      } finally {
        btnRefreshSystem.disabled = false;
      }
    });
  }

  if (btnExportSettings) {
    btnExportSettings.addEventListener("click", async function () {
      try {
        const res = await fetch("/api/settings/export");
        if (!res.ok) throw new Error("export failed");
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "1c-cursor-settings.json";
        a.click();
        URL.revokeObjectURL(url);
        showSettingsMessage("Настройки экспортированы.", false);
      } catch (_) {
        showSettingsMessage("Ошибка экспорта настроек.", true);
      }
    });
  }

  if (importSettingsFile) {
    importSettingsFile.addEventListener("change", async function () {
      const file = importSettingsFile.files && importSettingsFile.files[0];
      importSettingsFile.value = "";
      if (!file) return;
      try {
        const text = await file.text();
        const payload = JSON.parse(text);
        const res = await fetch("/api/settings/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error("import failed");
        const data = await res.json();
        if (data.snapshot) renderSectionsSnapshot(data.snapshot);
        showSettingsMessage("Настройки импортированы.", false);
        renderSystem(await loadSystem());
      } catch (_) {
        showSettingsMessage("Ошибка импорта: проверьте формат JSON.", true);
      }
    });
  }

  init();
})();
