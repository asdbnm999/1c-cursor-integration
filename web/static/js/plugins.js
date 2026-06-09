/**
 * §1 VS-плагины — UI установки VSIX
 */

(function () {
  const statusLabels = {
    not_started: "Не начато",
    in_progress: "В процессе",
    ready: "Готово",
  };

  const progressLabels = {
    waiting: "Ожидание",
    installing: "Установка…",
    ok: "Готово",
    skipped: "Пропущено",
    failed: "Ошибка",
    conflict: "Конфликт версий",
  };

  let lastStatus = null;
  let installInFlight = false;

  function $(id) {
    return document.getElementById(id);
  }

  async function fetchStatus() {
    const res = await fetch("/plugins/api/status");
    if (!res.ok) throw new Error("Не удалось загрузить статус");
    return res.json();
  }

  function setBadge(status) {
    const badge = $("section-badge");
    if (!badge) return;
    badge.textContent = statusLabels[status] || status;
    badge.className = "card-badge status-" + status;
  }

  function renderCursorInfo(cursor) {
    const input = $("cursor-dir-input");
    const hint = $("cursor-cli-hint");
    if (input) {
      input.value =
        cursor.extensions_dir_configured ||
        cursor.extensions_dir ||
        "";
      input.placeholder = cursor.extensions_dir_exists
        ? cursor.extensions_dir
        : "Укажите каталог расширений…";
    }
    if (hint) {
      const dir = cursor.extensions_dir || cursor.extensions_dir_configured;
      const source =
        cursor.extensions_dir_source === "configured"
          ? "указан вручную"
          : cursor.extensions_dir_source === "detected"
            ? "найден автоматически"
            : "";
      let catalog;
      if (cursor.extensions_dir_exists && dir) {
        catalog = `Каталог расширений: ${dir}${source ? ` (${source})` : ""}`;
      } else {
        catalog = "Каталог расширений не найден — укажите путь к ~/.cursor/extensions";
      }
      const cli = cursor.cli_available
        ? `Установка через CLI: ${cursor.cli_path}`
        : "CLI cursor не в PATH — VSIX распаковывается в каталог вручную";
      hint.textContent = `${catalog}. ${cli}.`;
    }
  }

  function rowHtml(item, checkedDefault) {
    const checked = checkedDefault ? "checked" : "";
    const stateClass =
      item.install_state === "update_available" ? "cell-warn" : "";
    return `
      <tr data-path="${escapeAttr(item.path)}" data-extension-id="${escapeAttr(item.extension_id)}" data-filename="${escapeAttr(item.filename)}">
        <td><input type="checkbox" class="vsix-select" data-path="${escapeAttr(item.path)}" ${checked}></td>
        <td class="mono">${escapeHtml(item.filename)}</td>
        <td>${escapeHtml(item.extension_id)}</td>
        <td>v${escapeHtml(item.version)}</td>
        <td class="${stateClass}">${escapeHtml(item.status_label)}</td>
      </tr>`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s);
  }

  function renderTables(data) {
    const bundledBody = $("bundled-table")?.querySelector("tbody");
    const additionalBody = $("additional-table")?.querySelector("tbody");
    if (bundledBody) {
      bundledBody.innerHTML = (data.bundled || [])
        .map((item) => rowHtml(item, true))
        .join("");
    }
    if (additionalBody) {
      const rows = data.additional || [];
      additionalBody.innerHTML = rows.map((item) => rowHtml(item, false)).join("");
      const empty = $("additional-empty");
      if (empty) empty.classList.toggle("hidden", rows.length > 0);
    }
  }

  function renderBanners(data) {
    const banner = $("plugins-update-banner");
    if (banner) {
      if (data.update_banner && data.update_banner_text) {
        banner.textContent = data.update_banner_text;
        banner.classList.remove("hidden");
      } else {
        banner.classList.add("hidden");
      }
    }
    const errors = $("plugins-errors");
    if (errors) {
      const list = data.errors || [];
      if (list.length) {
        errors.innerHTML = list
          .map((e) => `<div class="warning-item">${escapeHtml(e)}</div>`)
          .join("");
        errors.classList.remove("hidden");
      } else {
        errors.classList.add("hidden");
        errors.innerHTML = "";
      }
    }
  }

  function selectedPaths() {
    return Array.from(document.querySelectorAll(".vsix-select:checked")).map(
      (el) => el.dataset.path
    );
  }

  function rowMeta(path) {
    const row = document.querySelector(`tr[data-path="${CSS.escape(path)}"]`);
    return {
      filename: row?.dataset.filename || path.split("/").pop() || path,
      extensionId: row?.dataset.extensionId || "",
    };
  }

  function renderInstallProgress(paths) {
    const box = $("install-progress");
    if (!box) return;
    box.innerHTML = paths
      .map((path) => {
        const meta = rowMeta(path);
        const title = meta.extensionId || meta.filename;
        return `
          <div class="install-progress-item is-waiting" data-path="${escapeAttr(path)}">
            <div class="install-progress-head">
              <span class="install-progress-name">${escapeHtml(title)}</span>
              <span class="install-progress-status">${progressLabels.waiting}</span>
            </div>
            <div class="progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
              <div class="progress-fill"></div>
            </div>
          </div>`;
      })
      .join("");
    box.classList.remove("hidden");
  }

  function setInstallProgress(path, state, message) {
    const item = $("install-progress")?.querySelector(
      `.install-progress-item[data-path="${CSS.escape(path)}"]`
    );
    if (!item) return;

    item.className = "install-progress-item is-" + state;
    const statusEl = item.querySelector(".install-progress-status");
    const fill = item.querySelector(".progress-fill");
    const bar = item.querySelector(".progress-bar");

    const label =
      message ||
      progressLabels[state] ||
      state;
    if (statusEl) statusEl.textContent = label;

    fill?.classList.remove("is-active");
    let pct = 0;
    if (state === "installing") {
      pct = 15;
      fill?.classList.add("is-active");
    } else if (state === "ok" || state === "skipped") {
      pct = 100;
    } else if (state === "failed" || state === "conflict") {
      pct = 100;
      if (fill) fill.style.background = "var(--err)";
    }

    if (fill) fill.style.width = pct + "%";
    if (bar) bar.setAttribute("aria-valuenow", String(pct));
  }

  function setInstallUiBusy(busy) {
    installInFlight = busy;
    const installBtn = $("btn-install");
    const refreshBtn = $("btn-refresh");
    if (installBtn) {
      installBtn.disabled = busy;
      installBtn.textContent = busy ? "Установка…" : "Установить выбранные";
    }
    if (refreshBtn) refreshBtn.disabled = busy;
  }

  function renderReport(results) {
    const box = $("install-report");
    if (!box) return;
    if (!results || !results.length) {
      box.classList.add("hidden");
      return;
    }
    const lines = results.map((r) => {
      const icon =
        r.status === "ok"
          ? "OK"
          : r.status === "skipped"
            ? "SKIP"
            : "FAIL";
      return `<div class="report-line report-${r.status}"><strong>${icon}</strong> ${escapeHtml(r.path.split("/").pop())}: ${escapeHtml(r.message)}</div>`;
    });
    box.innerHTML = "<h3>Результат установки</h3>" + lines.join("");
    box.classList.remove("hidden");
  }

  async function postInstall(paths, { force = false, skipPaths = [] } = {}) {
    const response = await fetch("/plugins/api/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths, force, skip_paths: skipPaths }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Ошибка установки");
    }
    return data;
  }

  async function installOne(path, { force = false } = {}) {
    setInstallProgress(path, "installing");
    const data = await postInstall([path], { force, skipPaths: [] });
    const result = (data.results || [])[0];
    if (!result) {
      setInstallProgress(path, "failed", "Нет ответа сервера");
      return { status: "failed", message: "Нет ответа сервера", path };
    }

    if (result.status === "conflict") {
      setInstallProgress(path, "conflict", result.message);
      const action = await showConflictDialog(result);
      if (action === "reinstall") {
        setInstallProgress(path, "installing", "Переустановка…");
        const forced = await postInstall([path], { force: true, skipPaths: [] });
        const forcedResult = (forced.results || [])[0] || result;
        setInstallProgress(
          path,
          forcedResult.status === "ok" ? "ok" : forcedResult.status,
          forcedResult.message
        );
        return forcedResult;
      }
      setInstallProgress(path, "skipped", "Пропущено пользователем");
      return {
        path,
        status: "skipped",
        message: "Пропущено пользователем",
      };
    }

    const uiState =
      result.status === "ok"
        ? "ok"
        : result.status === "skipped"
          ? "skipped"
          : "failed";
    setInstallProgress(path, uiState, result.message);
    return result;
  }

  async function installWithConflicts(paths) {
    renderInstallProgress(paths);
    $("install-report")?.classList.add("hidden");
    setInstallUiBusy(true);

    const allResults = [];
    try {
      for (const path of paths) {
        const result = await installOne(path, { force: false });
        allResults.push(result);
      }
      renderReport(allResults);
      await refresh();
    } catch (err) {
      alert(err.message || "Ошибка установки");
    } finally {
      setInstallUiBusy(false);
    }
    return allResults;
  }

  function showConflictDialog(conflict) {
    return new Promise((resolve) => {
      const dialog = $("conflict-dialog");
      const text = $("conflict-text");
      if (!dialog || !text) {
        resolve("skip");
        return;
      }
      text.textContent = conflict.message;
      dialog.showModal();
      dialog.onclose = () => {
        resolve(dialog.returnValue === "reinstall" ? "reinstall" : "skip");
      };
    });
  }

  async function refresh() {
    try {
      const data = await fetchStatus();
      lastStatus = data;
      setBadge(data.section_status);
      renderCursorInfo(data.cursor || {});
      renderTables(data);
      renderBanners(data);
    } catch (err) {
      console.error(err);
    }
  }

  async function saveCursorDir() {
    const path = $("cursor-dir-input")?.value?.trim();
    if (!path) {
      alert("Укажите путь к каталогу расширений");
      return;
    }
    const res = await fetch("/plugins/api/cursor-dir", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || "Не удалось сохранить");
      return;
    }
    await refresh();
  }

  async function pickCursorDir() {
    const res = await fetch("/plugins/api/pick-cursor-dir", { method: "POST" });
    const data = await res.json();
    if (data.cancelled) return;
    if (data.ok && $("cursor-dir-input")) {
      $("cursor-dir-input").value = data.path;
      await refresh();
    }
  }

  async function addVsix() {
    const res = await fetch("/plugins/api/pick-vsix", { method: "POST" });
    const data = await res.json();
    if (data.cancelled) return;
    if (!data.ok) {
      alert(data.error || "Не удалось добавить VSIX");
      return;
    }
    await refresh();
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("btn-refresh")?.addEventListener("click", () => {
      if (!installInFlight) refresh();
    });
    $("btn-install")?.addEventListener("click", async () => {
      const paths = selectedPaths();
      if (!paths.length) {
        alert("Выберите хотя бы один VSIX");
        return;
      }
      await installWithConflicts(paths);
    });
    $("btn-save-cursor-dir")?.addEventListener("click", saveCursorDir);
    $("btn-pick-cursor-dir")?.addEventListener("click", pickCursorDir);
    $("btn-add-vsix")?.addEventListener("click", addVsix);
    $("bundled-select-all")?.addEventListener("change", (e) => {
      const checked = e.target.checked;
      document
        .querySelectorAll("#bundled-table .vsix-select")
        .forEach((cb) => {
          cb.checked = checked;
        });
    });
    refresh();
  });
})();
