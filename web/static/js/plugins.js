/**
 * §1 VS-плагины — UI установки VSIX
 */

(function () {
  const statusLabels = {
    not_started: "Не начато",
    in_progress: "В процессе",
    ready: "Готово",
  };

  let lastStatus = null;
  let pendingConflicts = [];

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
      <tr data-path="${escapeAttr(item.path)}">
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

  async function installWithConflicts(paths, force) {
    const skipPaths = [];
    pendingConflicts = [];

    let response = await fetch("/plugins/api/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths, force, skip_paths: skipPaths }),
    });
    let data = await response.json();
    if (!response.ok) {
      alert(data.error || "Ошибка установки");
      return;
    }

    const conflicts = (data.results || []).filter((r) => r.status === "conflict");
    for (const conflict of conflicts) {
      const action = await showConflictDialog(conflict);
      if (action === "reinstall") {
        const forced = await fetch("/plugins/api/install", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            paths: [conflict.path],
            force: true,
            skip_paths: [],
          }),
        });
        const forcedData = await forced.json();
        data.results = (data.results || []).filter(
          (r) => r.path !== conflict.path
        );
        data.results.push(...(forcedData.results || []));
      } else {
        skipPaths.push(conflict.path);
      }
    }

    renderReport(data.results);
    await refresh();
    return data;
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
    $("btn-refresh")?.addEventListener("click", refresh);
    $("btn-install")?.addEventListener("click", async () => {
      const paths = selectedPaths();
      if (!paths.length) {
        alert("Выберите хотя бы один VSIX");
        return;
      }
      await installWithConflicts(paths, false);
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
