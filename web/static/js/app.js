(function () {
  "use strict";

  const paletteSelect = document.getElementById("palette-select");
  const root = document.documentElement;
  const dockerBadge = document.getElementById("docker-badge");
  const dockerBanner = document.getElementById("docker-banner");

  function applyPalette(name) {
    root.setAttribute("data-palette", name);
    if (paletteSelect) paletteSelect.value = name;
  }

  async function loadPalette() {
    try {
      const res = await fetch("/api/settings/ui");
      if (!res.ok) return;
      const data = await res.json();
      if (data.palette) applyPalette(data.palette);
    } catch (_) { /* ignore */ }
  }

  async function savePalette(name) {
    applyPalette(name);
    try {
      await fetch("/api/settings/ui", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ palette: name }),
      });
    } catch (_) { /* ignore */ }
  }

  function setDockerBadge(running, message) {
    if (!dockerBadge) return;
    dockerBadge.textContent = running ? "Docker OK" : "Docker недоступен";
    dockerBadge.classList.toggle("ok", running);
    dockerBadge.classList.toggle("err", !running);
    dockerBadge.title = message || "";
  }

  function setDockerBanner(warnings) {
    if (!dockerBanner) return;
    const dockerWarnings = (warnings || []).filter(function (w) {
      return w.indexOf("Docker") >= 0 || w.indexOf("docker") >= 0;
    });
    if (!dockerWarnings.length) {
      dockerBanner.classList.add("hidden");
      dockerBanner.textContent = "";
      return;
    }
    dockerBanner.textContent = dockerWarnings.join(" ");
    dockerBanner.classList.remove("hidden");
  }

  async function refreshGlobalDockerStatus() {
    try {
      const res = await fetch("/api/system");
      if (!res.ok) return;
      const data = await res.json();
      const docker = data.docker || {};
      setDockerBadge(!!docker.running, docker.message || "");
      setDockerBanner(data.warnings || []);
    } catch (_) {
      setDockerBadge(false, "Не удалось получить статус Docker");
    }
  }

  if (paletteSelect) {
    paletteSelect.addEventListener("change", function () {
      savePalette(paletteSelect.value);
    });
  }

  window.setDockerStatusFromSystem = function (data) {
    const docker = (data && data.docker) || {};
    setDockerBadge(!!docker.running, docker.message || "");
    setDockerBanner((data && data.warnings) || []);
  };

  function initModalDismiss() {
    document.addEventListener("click", function (e) {
      const dialog = e.target;
      if (
        dialog instanceof HTMLDialogElement &&
        dialog.open &&
        e.target === dialog &&
        !dialog.hasAttribute("data-no-dismiss")
      ) {
        dialog.close();
        return;
      }

      const backdrop = e.target.closest("[data-close-modal]");
      if (!backdrop) return;
      const modal = backdrop.closest(".modal");
      if (modal && modal.hidden === false) {
        modal.hidden = true;
        modal.setAttribute("aria-hidden", "true");
      }
    });
  }

  initModalDismiss();

  loadPalette();
  if (!document.getElementById("health-panel")) {
    refreshGlobalDockerStatus();
    setInterval(refreshGlobalDockerStatus, 60000);
  }
})();
