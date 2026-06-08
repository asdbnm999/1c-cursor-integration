const API = "/rules/api";

let schema = null;
const fieldState = {};
let advancedRulesState = {};
let advancedRulesDraft = {};
let advancedAck = false;
let mcpAck = false;
let mcpState = { searxng: false, syntax_helper: false, kb_profiles: {} };
let analyzeOk = false;
let projectType = null;
let generateOk = false;

const $ = (sel) => document.querySelector(sel);

const exportPath = $("#exportPath");
const projectTypeEl = $("#projectType");
const gitFields = $("#gitFields");
const gitBranch = $("#gitBranch");
const analysisOut = $("#analysisOut");
const statusEl = $("#status");
const previewOut = $("#previewOut");
const eventLogOut = $("#eventLogOut");
const outputLinks = $("#outputLinks");
const writeToCursorRules = $("#writeToCursorRules");
const customOutputWrap = $("#customOutputWrap");
const outputPath = $("#outputPath");
const mcpToggles = $("#mcpToggles");

function setStatus(text, type = "") {
  if (!statusEl) return;
  statusEl.textContent = text;
  statusEl.className = "status-line" + (type ? ` ${type}` : "");
}

function setBadge(id, ok, labelOk = "Готово", labelNo = "Не выполнено") {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = ok ? labelOk : labelNo;
  el.classList.toggle("success", ok);
}

function setStepReady(sectionId, ready) {
  const sec = document.getElementById(sectionId);
  if (sec) sec.classList.toggle("step-ready", ready);
}

function unlockStep(stepId, unlocked) {
  const sec = document.getElementById(stepId);
  if (!sec) return;
  sec.classList.toggle("workflow-step--locked", !unlocked);
}

function updateWorkflow() {
  const path = exportPath?.value?.trim();
  const projectOk = Boolean(path && projectType);

  setBadge("badge-project", projectOk);
  setStepReady("section-project", projectOk);
  unlockStep("section-analyze", projectOk);

  setBadge("badge-analyze", analyzeOk);
  setStepReady("section-analyze", analyzeOk);
  unlockStep("section-main", analyzeOk);

  const mainOk = analyzeOk && isMainComplete();
  setBadge("badge-main", mainOk && advancedAck);
  setStepReady("section-main", mainOk && advancedAck);
  unlockStep("section-mcp-rules", mainOk && advancedAck);

  setBadge("badge-mcp", mcpAck);
  setStepReady("section-mcp-rules", mcpAck);
  unlockStep("section-generate", mcpAck);

  setBadge("badge-generate", generateOk);
  setStepReady("section-generate", generateOk);
}

function isMainComplete() {
  if (!schema) return false;
  const notSet = schema.constants.not_set;
  const required = ["solution_type", "vcs", "dev_prefix"];
  for (const key of required) {
    const st = fieldState[key];
    if (!st || st.choice === notSet) return false;
  }
  const vcs = fieldState.vcs?.choice;
  if (vcs !== schema.constants.vcs_none) {
    const br = fieldState.default_branch?.choice;
    if (!br || br === notSet) return false;
  }
  return true;
}

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  return res;
}

function initialChoice(spec) {
  if (spec.default && spec.options.includes(spec.default)) return spec.default;
  if (spec.allow_not_set) return schema.constants.not_set;
  return spec.options[0];
}

function applyCheckboxToggle(option, checked, selected, notSet, manual) {
  if (checked) {
    if (option === notSet) return new Set([notSet]);
    if (option === manual) return new Set([manual]);
    const out = new Set([...selected].filter((o) => o !== notSet && o !== manual));
    out.add(option);
    return out;
  }
  const out = new Set(selected);
  out.delete(option);
  return out;
}

function syncCheckboxUi(spec, group, manual, selected) {
  const notSet = schema.constants.not_set;
  const manualLabel = schema.constants.manual_input;
  group.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.checked = selected.has(cb.value);
  });
  const showManual = selected.has(manualLabel);
  manual.hidden = !showManual;
  fieldState[spec.key].checked = [...selected];
  fieldState[spec.key].custom = manual.value;
}

function createCheckboxFieldBlock(spec, container) {
  const block = document.createElement("div");
  block.className = "field-block";
  block.dataset.key = spec.key;
  const label = document.createElement("div");
  label.className = "label";
  label.textContent = spec.label.replace(/:$/, "");
  const group = document.createElement("div");
  group.className = "checkbox-group";
  const manual = document.createElement("textarea");
  manual.className = "textarea-manual";
  manual.hidden = true;
  const selected = new Set(spec.default_checked || []);
  spec.options.forEach((opt) => {
    const row = document.createElement("label");
    row.className = "checkbox-row";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = opt;
    cb.addEventListener("change", () => {
      const next = applyCheckboxToggle(
        opt,
        cb.checked,
        selected,
        schema.constants.not_set,
        schema.constants.manual_input
      );
      selected.clear();
      next.forEach((v) => selected.add(v));
      syncCheckboxUi(spec, group, manual, selected);
      updateWorkflow();
    });
    const span = document.createElement("span");
    span.textContent = opt;
    row.append(cb, span);
    group.appendChild(row);
  });
  manual.addEventListener("input", () => {
    fieldState[spec.key].custom = manual.value;
    updateWorkflow();
  });
  block.append(label, group, manual);
  container.appendChild(block);
  fieldState[spec.key] = { checked: [...selected], custom: "" };
  syncCheckboxUi(spec, group, manual, selected);
}

function updateFieldUI(key) {
  const block = document.querySelector(`.field-block[data-key="${key}"]`);
  if (!block) return;
  const select = block.querySelector(".select");
  const manual = block.querySelector(".manual-input, .textarea-manual");
  const warning = block.querySelector(".warning-box");
  const choice = select.value;
  const isManual = choice === schema.constants.manual_input;
  if (manual) {
    manual.hidden = !isManual;
    if (!isManual) fieldState[key].custom = "";
  }
  if (warning && block._warnings?.[choice]) {
    warning.textContent = `⚠ ${block._warnings[choice]}`;
    warning.classList.remove("warning-box--hidden");
  } else if (warning) {
    warning.classList.add("warning-box--hidden");
  }
  fieldState[key].choice = choice;
  updateWorkflow();
}

function createFieldBlock(spec, container) {
  if (spec.field_type === "checkboxes") {
    createCheckboxFieldBlock(spec, container);
    return;
  }
  const block = document.createElement("div");
  block.className = "field-block";
  block.dataset.key = spec.key;
  if (spec.visible_when_wrap_enabled) block.dataset.wrapMarker = "1";
  if (spec.hide_when_vcs_is) block.dataset.hideWhenVcs = spec.hide_when_vcs_is;

  const label = document.createElement("label");
  label.className = "label";
  label.textContent = spec.label.replace(/:$/, "");
  const select = document.createElement("select");
  select.className = "select";
  spec.options.forEach((opt) => {
    const o = document.createElement("option");
    o.value = opt;
    o.textContent = opt;
    select.appendChild(o);
  });
  const manual = document.createElement(spec.manual_multiline ? "textarea" : "input");
  manual.className = spec.manual_multiline ? "textarea-manual manual-input" : "input manual-input";
  if (!spec.manual_multiline) manual.type = "text";
  manual.hidden = true;
  const warning = document.createElement("div");
  warning.className = "warning-box warning-box--hidden";
  block.append(label, select, manual, warning);
  container.appendChild(block);
  const choice = initialChoice(spec);
  select.value = choice;
  fieldState[spec.key] = { choice, custom: "" };
  if (spec.warning_for) block._warnings = spec.warning_for;
  select.addEventListener("change", () => {
    updateFieldUI(spec.key);
    if (spec.key === "ai_patch_wrap") updateWrapVisibility();
    if (spec.key === "vcs") updateVcsVisibility();
  });
  manual.addEventListener("input", () => {
    fieldState[spec.key].custom = manual.value;
    updateWorkflow();
  });
  updateFieldUI(spec.key);
}

function updateVcsVisibility() {
  const vcs = fieldState.vcs?.choice;
  const hide = vcs === schema?.constants?.vcs_none;
  document.querySelectorAll("[data-hide-when-vcs]").forEach((el) => {
    el.classList.toggle("field-block--hidden", hide);
  });
  updateWorkflow();
}

function updateWrapVisibility() {
  const wrap = fieldState.ai_patch_wrap?.choice;
  const disabled = wrap === schema.constants.wrap_disabled;
  document.querySelectorAll('[data-wrap-marker="1"]').forEach((el) => {
    el.classList.toggle("field-block--hidden", disabled);
  });
  updateWorkflow();
}

function updateAdvancedSummary() {
  const el = $("#advancedSummary");
  if (!el || !schema) return;
  if (!advancedAck) {
    el.textContent = "Не сохранено — откройте modal и нажмите «Сохранить» или «Рекомендуемые»";
    return;
  }
  const skip = schema.constants.advanced_skip;
  const total = (schema.advanced_fields || []).length;
  const set = Object.values(advancedRulesState).filter((v) => v && v !== skip).length;
  el.textContent = set === 0
    ? "Сохранено: все пункты пропущены (общие формулировки)"
    : `Сохранено: ${set} из ${total} уточнений`;
}

function buildAdvancedDraft(fromState) {
  advancedRulesDraft = {};
  const initial = schema.advanced_initial_defaults || {};
  (schema.advanced_fields || []).forEach((spec) => {
    const saved = fromState?.[spec.key];
    if (saved !== undefined && saved !== "") {
      advancedRulesDraft[spec.key] = saved;
    } else {
      advancedRulesDraft[spec.key] = initial[spec.key] ?? schema.constants.advanced_skip;
    }
  });
}

function renderAdvancedModal() {
  const body = $("#advancedModalBody");
  if (!body || !schema?.advanced_fields) return;
  body.innerHTML = "";
  const bySection = new Map();
  schema.advanced_fields.forEach((spec) => {
    const sec = spec.section || "Прочее";
    if (!bySection.has(sec)) bySection.set(sec, []);
    bySection.get(sec).push(spec);
  });
  bySection.forEach((fields, section) => {
    const secEl = document.createElement("div");
    secEl.className = "modal__section";
    const title = document.createElement("h3");
    title.className = "modal__section-title";
    title.textContent = section;
    secEl.appendChild(title);
    fields.forEach((spec) => {
      const wrap = document.createElement("div");
      wrap.className = "modal__field";
      const lbl = document.createElement("label");
      lbl.textContent = spec.label;
      lbl.htmlFor = `adv-${spec.key}`;
      const sel = document.createElement("select");
      sel.className = "select";
      sel.id = `adv-${spec.key}`;
      spec.options.forEach((opt) => {
        const o = document.createElement("option");
        o.value = opt;
        o.textContent = opt;
        sel.appendChild(o);
      });
      sel.value = advancedRulesDraft[spec.key] || schema.constants.advanced_skip;
      sel.addEventListener("change", () => {
        advancedRulesDraft[spec.key] = sel.value;
      });
      wrap.append(lbl, sel);
      secEl.appendChild(wrap);
    });
    body.appendChild(secEl);
  });
}

function openAdvancedModal() {
  if (!schema) return;
  buildAdvancedDraft(advancedAck ? advancedRulesState : {});
  renderAdvancedModal();
  const modal = $("#advancedModal");
  modal.hidden = false;
  modal.setAttribute("aria-hidden", "false");
}

function closeAdvancedModal() {
  const modal = $("#advancedModal");
  if (!modal) return;
  modal.hidden = true;
  modal.setAttribute("aria-hidden", "true");
}

function setAdvancedDraftAll(skip) {
  const skipLabel = schema.constants.advanced_skip;
  const rec = schema.advanced_recommended_defaults || {};
  (schema.advanced_fields || []).forEach((spec) => {
    advancedRulesDraft[spec.key] = skip ? skipLabel : (rec[spec.key] || spec.recommended);
  });
  renderAdvancedModal();
}

function collectFields() {
  const payload = {};
  Object.keys(fieldState).forEach((key) => {
    const block = document.querySelector(`.field-block[data-key="${key}"]`);
    if (block?.classList.contains("field-block--hidden")) return;
    if (fieldState[key].checked !== undefined) {
      payload[key] = { checked: [...fieldState[key].checked], custom: fieldState[key].custom || "" };
      return;
    }
    payload[key] = { choice: fieldState[key].choice, custom: fieldState[key].custom || "" };
  });
  payload.advanced = { ...advancedRulesState };
  payload.mcp = {
    searxng: mcpState.searxng,
    syntax_helper: mcpState.syntax_helper,
    kb_profiles: { ...mcpState.kb_profiles },
    acknowledged: mcpAck,
  };
  return payload;
}

function applyHints(hints) {
  Object.entries(hints || {}).forEach(([key, value]) => {
    if (key.endsWith("_custom")) return;
    const block = document.querySelector(`.field-block[data-key="${key}"]`);
    if (!block) return;
    const select = block.querySelector(".select");
    if (!select || select.value !== schema.constants.not_set) return;
    if ([...select.options].some((o) => o.value === value)) {
      select.value = value;
      fieldState[key].choice = value;
      updateFieldUI(key);
    }
  });
  if (hints.dev_prefix_custom && fieldState.dev_prefix) {
    const block = document.querySelector('.field-block[data-key="dev_prefix"]');
    const select = block?.querySelector(".select");
    const manual = block?.querySelector(".manual-input");
    if (select) {
      select.value = schema.constants.manual_input;
      fieldState.dev_prefix.choice = schema.constants.manual_input;
      fieldState.dev_prefix.custom = hints.dev_prefix_custom;
      if (manual) {
        manual.value = hints.dev_prefix_custom;
        manual.hidden = false;
      }
    }
  }
}

async function loadMcpDefaults() {
  const res = await api("/mcp-defaults");
  const data = await res.json();
  mcpState.searxng = data.searxng;
  mcpState.syntax_helper = data.syntax_helper;
  mcpState.kb_profiles = {};
  (data.available?.kb_profiles || []).forEach((key) => {
    mcpState.kb_profiles[key] = (data.kb_profiles || []).includes(key);
  });
  renderMcpToggles(data);
}

function renderMcpToggles(data) {
  if (!mcpToggles) return;
  mcpToggles.innerHTML = "";
  const items = [
    {
      key: "searxng",
      title: "searxng",
      desc: "Весь веб-поиск через локальный SearXNG MCP",
      available: data.available?.searxng,
    },
    {
      key: "syntax_helper",
      title: "1c-syntax-helper",
      desc: "Обязательное ревью кода 1С через справку платформы",
      available: data.available?.syntax_helper,
    },
  ];
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "mcp-toggle-row" + (item.available ? "" : " unavailable");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.id = `mcp-${item.key}`;
    cb.checked = mcpState[item.key];
    cb.disabled = !item.available;
    cb.addEventListener("change", () => {
      mcpState[item.key] = cb.checked;
      mcpAck = false;
      updateWorkflow();
    });
    const label = document.createElement("label");
    label.htmlFor = cb.id;
    label.innerHTML = `<span class="mcp-toggle-title">${item.title}</span>
      <span class="mcp-toggle-desc">${item.desc}${item.available ? "" : " (не в mcp.json)"}</span>`;
    row.append(cb, label);
    mcpToggles.appendChild(row);
  });
  (data.available?.kb_profiles || []).forEach((key) => {
    const row = document.createElement("div");
    row.className = "mcp-toggle-row";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.id = `mcp-kb-${key}`;
    cb.checked = Boolean(mcpState.kb_profiles[key]);
    cb.addEventListener("change", () => {
      mcpState.kb_profiles[key] = cb.checked;
      mcpAck = false;
      updateWorkflow();
    });
    const label = document.createElement("label");
    label.htmlFor = cb.id;
    label.innerHTML = `<span class="mcp-toggle-title">${key}</span>
      <span class="mcp-toggle-desc">База знаний проекта (KB MCP)</span>`;
    row.append(cb, label);
    mcpToggles.appendChild(row);
  });
}

async function detectProject() {
  const path = exportPath?.value?.trim();
  if (!path) {
    projectType = null;
    projectTypeEl.value = "";
    updateWorkflow();
    return;
  }
  try {
    const res = await api("/detect-project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ export_path: path }),
    });
    const data = await res.json();
    projectType = data.project_type;
    projectTypeEl.value = data.project_type_label || "";
    if (!data.ok && data.errors?.length) {
      setStatus(data.errors.join(" "), "err");
    }
    updateWorkflow();
  } catch {
    /* ignore */
  }
}

async function pickExportDir() {
  setStatus("Откройте окно выбора папки…");
  const res = await api("/pick-directory", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const data = await res.json();
  if (data.ok && data.path) {
    exportPath.value = data.path;
    analyzeOk = false;
    await detectProject();
    setStatus(`Выбрана папка: ${data.path}`, "ok");
  } else if (data.error) {
    setStatus(data.error, "err");
  }
}

async function analyze() {
  const path = exportPath.value.trim();
  if (!path) {
    setStatus("Укажите путь к проекту.", "err");
    return;
  }
  $("#btnAnalyze").disabled = true;
  setStatus("Анализ…");
  try {
    const res = await api("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ export_path: path, fields: collectFields() }),
    });
    const data = await res.json();
    analysisOut.textContent = data.report || data.error || "";
    projectType = data.project_type;
    projectTypeEl.value = data.project_type_label || "";
    analyzeOk = Boolean(data.ok);
    if (data.git?.is_git) {
      gitFields?.classList.remove("hidden");
      if (gitBranch && data.git.branch) gitBranch.value = data.git.branch;
      if ($("#gitRemote")) $("#gitRemote").value = data.git.remote || "";
      if (fieldState.vcs?.choice === schema.constants.not_set) {
        fieldState.vcs.choice = "Git";
        const sel = document.querySelector('.field-block[data-key="vcs"] .select');
        if (sel) sel.value = "Git";
      }
      if (fieldState.default_branch && data.git.branch) {
        const brSel = document.querySelector('.field-block[data-key="default_branch"] .select');
        if (brSel && brSel.value === schema.constants.not_set) {
          if ([...brSel.options].some((o) => o.value === data.git.branch)) {
            brSel.value = data.git.branch;
            fieldState.default_branch.choice = data.git.branch;
          } else {
            brSel.value = schema.constants.manual_input;
            fieldState.default_branch.choice = schema.constants.manual_input;
            const manual = document.querySelector('.field-block[data-key="default_branch"] .manual-input');
            if (manual) {
              manual.value = data.git.branch;
              manual.hidden = false;
            }
            fieldState.default_branch.custom = data.git.branch;
          }
        }
      }
    } else {
      gitFields?.classList.add("hidden");
    }
    if (data.hints) applyHints(data.hints);
    await loadMcpDefaults();
    mcpAck = false;
    if (data.ok) {
      setStatus("Анализ завершён. Заполните параметры.", "ok");
    } else {
      setStatus((data.errors || []).join(" ") || "Ошибка анализа", "err");
    }
    updateWorkflow();
  } catch (e) {
    setStatus(`Ошибка: ${e.message}`, "err");
  } finally {
    $("#btnAnalyze").disabled = false;
  }
}

async function generate(confirmUnsafe = false, confirmAllSkip = false) {
  const path = exportPath.value.trim();
  if (!path) {
    setStatus("Укажите путь к проекту.", "err");
    return;
  }
  const wrapChoice = fieldState.ai_patch_wrap?.choice;
  if (wrapChoice === schema.constants.wrap_disabled && !confirmUnsafe) {
    if (!confirm("Режим без обрамления небезопасен. Всё равно сгенерировать?")) return;
    confirmUnsafe = true;
  }
  $("#btnGenerate").disabled = true;
  setStatus("Генерация…");
  try {
    const res = await api("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        export_path: path,
        output_path: outputPath?.value?.trim() || "",
        fields: collectFields(),
        confirm_unsafe_wrap: confirmUnsafe,
        confirm_all_skip: confirmAllSkip,
        advanced_ack: advancedAck,
        write_to_cursor_rules: writeToCursorRules?.checked ?? true,
      }),
    });
    const data = await res.json();
    if (data.needs_confirm) {
      if (confirm(`${data.error}\n\nПродолжить?`)) return generate(true, confirmAllSkip);
      setStatus("Отменено.", "err");
      return;
    }
    if (data.needs_skip_confirm) {
      if (confirm(`${data.error}\n\nПродолжить?`)) return generate(confirmUnsafe, true);
      setStatus("Отменено.", "err");
      return;
    }
    if (!data.ok) {
      setStatus(data.error || "Ошибка", "err");
      return;
    }
    previewOut.textContent = data.markdown || "";
    eventLogOut.textContent = data.event_log_markdown || "";
    generateOk = true;
    outputLinks.classList.remove("hidden");
    outputLinks.innerHTML = `
      <div>Основной: <code>${data.output_path}</code></div>
      <div>Журнал: <code>${data.event_log_path}</code></div>`;
    setStatus(`Сохранено: ${data.output_path}`, "ok");
    updateWorkflow();
  } catch (e) {
    setStatus(`Ошибка: ${e.message}`, "err");
  } finally {
    $("#btnGenerate").disabled = false;
  }
}

function switchTab(name) {
  const isEvent = name === "eventlog";
  document.querySelectorAll(".tabs__btn").forEach((b) => {
    b.classList.toggle("tabs__btn--active", b.dataset.tab === name);
  });
  previewOut.classList.toggle("hidden", isEvent);
  eventLogOut.classList.toggle("hidden", !isEvent);
}

async function loadSchema() {
  const res = await api("/schema");
  schema = await res.json();
  $("#generalFields").innerHTML = "";
  $("#aiCommentFields").innerHTML = "";
  $("#aiExplainFields").innerHTML = "";
  schema.general_fields.forEach((s) => createFieldBlock(s, $("#generalFields")));
  (schema.ai_comment_fields || []).forEach((s) => createFieldBlock(s, $("#aiCommentFields")));
  (schema.ai_explain_fields || []).forEach((s) => createFieldBlock(s, $("#aiExplainFields")));
  updateWrapVisibility();
  updateVcsVisibility();
}

function boot() {
  loadSchema()
    .then(async () => {
      if (window.RULES_BOOT?.initialProjectPath) {
        exportPath.value = window.RULES_BOOT.initialProjectPath;
        await detectProject();
      }
      writeToCursorRules?.addEventListener("change", () => {
        customOutputWrap?.classList.toggle("hidden", writeToCursorRules.checked);
      });
      customOutputWrap?.classList.toggle("hidden", writeToCursorRules?.checked ?? true);

      $("#btnPickExport")?.addEventListener("click", pickExportDir);
      $("#btnAnalyze")?.addEventListener("click", analyze);
      $("#btnGenerate")?.addEventListener("click", () => generate(false, false));
      $("#btnPickOutput")?.addEventListener("click", async () => {
        const res = await api("/pick-save-file", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ default_name: "1С-правила-разработки.md" }),
        });
        const data = await res.json();
        if (data.ok && data.path) outputPath.value = data.path;
      });
      $("#btnAdvancedRules")?.addEventListener("click", openAdvancedModal);
      $("#advancedModal")?.querySelectorAll("[data-close-modal]").forEach((el) => {
        el.addEventListener("click", closeAdvancedModal);
      });
      $("#advancedClear")?.addEventListener("click", () => setAdvancedDraftAll(true));
      $("#advancedRecommend")?.addEventListener("click", () => setAdvancedDraftAll(false));
      $("#advancedApply")?.addEventListener("click", () => {
        advancedRulesState = { ...advancedRulesDraft };
        advancedAck = true;
        updateAdvancedSummary();
        closeAdvancedModal();
        updateWorkflow();
      });
      $("#btnMcpAccept")?.addEventListener("click", () => {
        mcpAck = true;
        setStatus("Настройки MCP приняты.", "ok");
        updateWorkflow();
      });
      document.querySelectorAll(".tabs__btn").forEach((btn) => {
        btn.addEventListener("click", () => switchTab(btn.dataset.tab));
      });
      exportPath?.addEventListener("change", () => {
        analyzeOk = false;
        detectProject();
      });

      const last = window.RULES_BOOT?.lastOutput;
      if (last?.main_path) {
        generateOk = true;
        setStatus(`Последняя генерация: ${last.main_path}`, "ok");
      }
      updateWorkflow();
      setStatus("Укажите путь к проекту и выполните анализ.");
    })
    .catch((e) => setStatus(`Не удалось загрузить форму: ${e.message}`, "err"));
}

boot();
