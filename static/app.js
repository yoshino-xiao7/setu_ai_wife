const form = document.querySelector("#generate-form");
const preview = document.querySelector("#prompt-preview");
const currentResult = document.querySelector("#current-result");
const jobMeta = document.querySelector("#job-meta");
const historyEl = document.querySelector("#history");
const translateBtn = document.querySelector("#translate-btn");
const refreshHistoryBtn = document.querySelector("#refresh-history");
const refreshPresetsBtn = document.querySelector("#refresh-presets");
const refreshHealthBtn = document.querySelector("#refresh-health");
const characterSelect = document.querySelector("#character-id");
const loraSelect = document.querySelector("#lora-name");
const healthGrid = document.querySelector("#health-grid");
const overallStatus = document.querySelector("#overall-status");
const capabilitySummary = document.querySelector("#capability-summary");
const loraList = document.querySelector("#lora-list");
const characterList = document.querySelector("#character-list");
let characters = [];
let sourceImageBase64 = "";

function field(id) {
  return document.querySelector(id);
}

function value(id) {
  return field(id).value.trim();
}

function numberValue(id) {
  const raw = value(id);
  return raw ? Number(raw) : null;
}

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json; charset=utf-8" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `请求失败：${response.status}`);
  }
  return data;
}

function parseMetadata(item) {
  try {
    return item.metadataJson ? JSON.parse(item.metadataJson) : {};
  } catch {
    return {};
  }
}

function renderHealth(data) {
  const checks = data.checks || {};
  const cards = Object.entries(checks).map(([key, item]) => {
    const label = {
      localService: "本机服务",
      comfyui: "ComfyUI",
      ollama: "Ollama",
      cloud: "云端连接",
      models: "模型目录",
      defaultCheckpoint: "默认模型",
    }[key] || key;
    return `
      <div class="health-card ${item.ok ? "ok" : "bad"}">
        <strong>${label}</strong>
        <span>${item.ok ? "正常" : "异常"}</span>
        <p>${escapeHtml(item.message)}</p>
      </div>
    `;
  });
  healthGrid.innerHTML = cards.join("");
  overallStatus.innerHTML = `
    <span class="status-dot ${data.ok ? "" : "bad"}"></span>
    <span>${data.ok ? "本机就绪" : "需要检查"}</span>
  `;
  const caps = data.capabilities || {};
  capabilitySummary.innerHTML = `
    <div><strong>${caps.checkpoints || 0}</strong><span>Checkpoint</span></div>
    <div><strong>${caps.loras || 0}</strong><span>LoRA</span></div>
    <div><strong>${caps.vaes || 0}</strong><span>VAE</span></div>
    <div><strong>${caps.characters || 0}</strong><span>角色</span></div>
  `;
}

async function loadHealth() {
  healthGrid.innerHTML = `<div class="job-state slim">正在检测本机服务...</div>`;
  try {
    renderHealth(await requestJson("/api/health"));
  } catch (error) {
    healthGrid.innerHTML = `<div class="job-state error slim">${escapeHtml(error.message)}</div>`;
    overallStatus.innerHTML = `<span class="status-dot bad"></span><span>检测失败</span>`;
  }
}

async function loadPresets() {
  try {
    characters = await requestJson("/api/characters");
    characterSelect.innerHTML =
      `<option value="">不使用预设</option>` +
      characters.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join("");
    characterList.innerHTML = characters.length
      ? characters.map((item) => {
          const tags = [item.trigger_words, item.default_positive, item.style_tags].filter(Boolean).join(", ");
          return `<article><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.lora_name || "无默认 LoRA")}</span><p>${escapeHtml(tags || item.notes || "未配置触发词")}</p></article>`;
        }).join("")
      : `<p class="muted-line">没有角色预设。</p>`;
  } catch (error) {
    characterSelect.innerHTML = `<option value="">角色预设加载失败</option>`;
    characterList.innerHTML = `<p class="error-text">${escapeHtml(error.message)}</p>`;
  }

  try {
    const loras = await requestJson("/api/loras");
    loraSelect.innerHTML =
      `<option value="">不使用 LoRA</option>` +
      loras.map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.displayName || item.name)}</option>`).join("");
    loraList.innerHTML = loras.length
      ? loras.map((item) => {
          const metadata = parseMetadata(item);
          return `<article><strong>${escapeHtml(item.displayName || item.name)}</strong><span>${escapeHtml(item.name)}</span><p>${escapeHtml(metadata.trigger_words || metadata.notes || "未配置触发词")}</p></article>`;
        }).join("")
      : `<p class="muted-line">没有扫描到 LoRA。</p>`;
  } catch (error) {
    loraSelect.innerHTML = `<option value="">LoRA 列表加载失败</option>`;
    loraList.innerHTML = `<p class="error-text">${escapeHtml(error.message)}</p>`;
  }
}

function buildPayload() {
  const payload = {
    prompt_cn: value("#prompt-cn") || value("#style-tags") || "local debug image",
    character_id: value("#character-id") || null,
    trigger_words: value("#trigger-words"),
    style_tags: value("#style-tags"),
    width: Number(value("#width")),
    height: Number(value("#height")),
    steps: numberValue("#steps"),
    cfg: numberValue("#cfg"),
    seed: numberValue("#seed"),
    checkpoint: value("#checkpoint") || null,
    lora_name: value("#lora-name"),
    lora_strength: Number(value("#lora-strength") || 0),
    job_type: value("#job-type") || "TEXT2IMG",
  };
  if (payload.job_type === "IMG2IMG") {
    payload.source_image_base64 = sourceImageBase64;
    payload.denoise = numberValue("#denoise") || 0.45;
  }
  return payload;
}

function setStageLoading(message) {
  currentResult.className = "job-state compact-stage";
  currentResult.innerHTML = `<div><div class="empty-mark">...</div><p>${escapeHtml(message)}</p></div>`;
}

function showJob(job) {
  jobMeta.textContent = `${job.width}x${job.height} · steps ${job.steps} · seed ${job.seed}`;
  if (job.status === "completed" && job.image_path) {
    currentResult.className = "result-view";
    currentResult.innerHTML = `
      <img src="/api/images/${encodeURIComponent(job.image_path)}" alt="生成结果" />
      <p class="result-caption">${escapeHtml(job.prompt_cn)}</p>
    `;
    return;
  }
  currentResult.className = job.status === "failed" ? "job-state error compact-stage" : "job-state compact-stage";
  currentResult.textContent = job.error || `任务状态：${job.status}`;
}

translateBtn.addEventListener("click", async () => {
  preview.style.display = "block";
  preview.textContent = "正在调用本机 Ollama...";
  try {
    const prompt = [value("#trigger-words"), value("#style-tags"), value("#prompt-cn")].filter(Boolean).join(", ");
    const data = await requestJson("/api/prompt/translate", {
      method: "POST",
      body: JSON.stringify({ prompt_cn: prompt || "anime portrait" }),
    });
    preview.textContent = `Positive:\n${data.positive}\n\nNegative:\n${data.negative}\n\nNotes:\n${data.style_notes}`;
  } catch (error) {
    preview.textContent = error.message;
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (value("#job-type") === "IMG2IMG" && !sourceImageBase64) {
    currentResult.className = "job-state error compact-stage";
    currentResult.textContent = "图生图需要先选择源图。";
    jobMeta.textContent = "提交失败";
    return;
  }
  setStageLoading("已提交本机测试任务，等待 ComfyUI...");
  jobMeta.textContent = "正在排队";
  try {
    const data = await requestJson("/api/generate", {
      method: "POST",
      body: JSON.stringify(buildPayload()),
    });
    pollJob(data.job_id);
  } catch (error) {
    currentResult.className = "job-state error compact-stage";
    currentResult.textContent = error.message;
    jobMeta.textContent = "提交失败";
  }
});

async function pollJob(jobId) {
  const timer = setInterval(async () => {
    try {
      const job = await requestJson(`/api/jobs/${jobId}`);
      if (job.status === "completed" || job.status === "failed") {
        clearInterval(timer);
        showJob(job);
        loadHistory();
      } else {
        setStageLoading(`任务状态：${job.status}`);
        jobMeta.textContent = job.comfy_prompt_id ? `ComfyUI: ${job.comfy_prompt_id}` : "正在运行";
      }
    } catch (error) {
      clearInterval(timer);
      currentResult.className = "job-state error compact-stage";
      currentResult.textContent = error.message;
      jobMeta.textContent = "轮询失败";
    }
  }, 2000);
}

async function loadHistory() {
  try {
    const jobs = await requestJson("/api/history?limit=12");
    historyEl.innerHTML = jobs.length
      ? jobs.map((job) => {
          const meta = job.status === "completed" ? `${job.width}x${job.height} · seed ${job.seed}` : escapeHtml(job.error || job.status);
          return `<article class="history-line"><strong>#${escapeHtml(job.id)}</strong><span>${escapeHtml(job.prompt_cn || job.prompt_positive)}</span><p>${meta}</p></article>`;
        }).join("")
      : `<p class="muted-line">暂无本机调试任务。</p>`;
  } catch (error) {
    historyEl.innerHTML = `<div class="job-state error slim">${escapeHtml(error.message)}</div>`;
  }
}

characterSelect.addEventListener("change", () => {
  const selected = characters.find((item) => item.id === characterSelect.value);
  if (!selected) return;
  field("#trigger-words").value = selected.trigger_words || "";
  field("#style-tags").value = selected.style_tags || "";
  if (selected.lora_name) {
    loraSelect.value = selected.lora_name;
  }
  field("#lora-strength").value = selected.lora_strength || 0.8;
});

document.querySelectorAll("[data-size]").forEach((button) => {
  button.addEventListener("click", () => {
    const [width, height] = button.dataset.size.split("x");
    field("#width").value = width;
    field("#height").value = height;
  });
});

document.querySelectorAll("[data-steps]").forEach((button) => {
  button.addEventListener("click", () => {
    field("#steps").value = button.dataset.steps;
  });
});

document.querySelectorAll("[data-denoise]").forEach((button) => {
  button.addEventListener("click", () => {
    field("#denoise").value = button.dataset.denoise;
  });
});

field("#job-type").addEventListener("change", () => {
  const img2img = value("#job-type") === "IMG2IMG";
  field("#img2img-fields").hidden = !img2img;
});

field("#source-image").addEventListener("change", async (event) => {
  const file = event.target.files && event.target.files[0];
  const preview = field("#source-preview");
  sourceImageBase64 = "";
  preview.hidden = true;
  preview.removeAttribute("src");
  if (!file) return;
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
  sourceImageBase64 = dataUrl.includes(",") ? dataUrl.split(",", 2)[1] : dataUrl;
  preview.src = dataUrl;
  preview.hidden = false;
});

refreshHealthBtn.addEventListener("click", loadHealth);
refreshHistoryBtn.addEventListener("click", loadHistory);
refreshPresetsBtn.addEventListener("click", async () => {
  await loadPresets();
  await loadHealth();
});

loadHealth();
loadPresets();
loadHistory();
