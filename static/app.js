const form = document.querySelector("#generate-form");
const preview = document.querySelector("#prompt-preview");
const currentResult = document.querySelector("#current-result");
const jobMeta = document.querySelector("#job-meta");
const historyEl = document.querySelector("#history");
const translateBtn = document.querySelector("#translate-btn");
const refreshHistoryBtn = document.querySelector("#refresh-history");
const refreshPresetsBtn = document.querySelector("#refresh-presets");
const reuseCurrentBtn = document.querySelector("#reuse-current");
const characterSelect = document.querySelector("#character-id");
const loraSelect = document.querySelector("#lora-name");
let characters = [];
let currentJob = null;

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

function buildPayload() {
  return {
    prompt_cn: value("#prompt-cn"),
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
  };
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

function setStageLoading(message) {
  currentResult.className = "job-state";
  currentResult.innerHTML = `<div><div class="empty-mark">...</div><p>${escapeHtml(message)}</p></div>`;
}

function showJob(job) {
  currentJob = job;
  jobMeta.textContent = `${job.width}x${job.height} · steps ${job.steps} · seed ${job.seed}`;
  if (job.status === "completed") {
    currentResult.className = "result-view";
    currentResult.innerHTML = `
      <img src="/api/images/${encodeURIComponent(job.image_path)}" alt="生成结果" />
      <p class="result-caption">${escapeHtml(job.prompt_cn)}</p>
    `;
    return;
  }
  currentResult.className = job.status === "failed" ? "job-state error" : "job-state";
  currentResult.textContent = job.error || `任务状态：${job.status}`;
}

translateBtn.addEventListener("click", async () => {
  preview.style.display = "block";
  preview.textContent = "正在转换 prompt...";
  try {
    const prompt = [value("#trigger-words"), value("#style-tags"), value("#prompt-cn")].filter(Boolean).join(", ");
    const data = await requestJson("/api/prompt/translate", {
      method: "POST",
      body: JSON.stringify({ prompt_cn: prompt }),
    });
    preview.textContent = `Positive:\n${data.positive}\n\nNegative:\n${data.negative}\n\nNotes:\n${data.style_notes}`;
  } catch (error) {
    preview.textContent = error.message;
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStageLoading("已提交，等待 ComfyUI 生成...");
  jobMeta.textContent = "正在排队";
  try {
    const data = await requestJson("/api/generate", {
      method: "POST",
      body: JSON.stringify(buildPayload()),
    });
    pollJob(data.job_id);
  } catch (error) {
    currentResult.className = "job-state error";
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
      currentResult.className = "job-state error";
      currentResult.textContent = error.message;
      jobMeta.textContent = "轮询失败";
    }
  }, 2000);
}

async function loadHistory() {
  try {
    const jobs = await requestJson("/api/history?limit=36");
    historyEl.innerHTML = jobs
      .map((job) => {
        const image = job.image_path
          ? `<img class="history-thumb" src="/api/images/${encodeURIComponent(job.image_path)}" alt="历史图片" />`
          : `<div class="history-missing">${escapeHtml(job.status)}</div>`;
        const title = escapeHtml(job.prompt_cn || job.prompt_positive);
        const meta = job.status === "completed" ? `${job.width}x${job.height} · seed ${job.seed}` : escapeHtml(job.error || job.status);
        return `
          <article class="history-card" data-job-id="${job.id}">
            ${image}
            <div>
              <h3>${title}</h3>
              <p>${meta}</p>
            </div>
          </article>
        `;
      })
      .join("");
  } catch (error) {
    historyEl.innerHTML = `<div class="job-state error">${escapeHtml(error.message)}</div>`;
  }
}

historyEl.addEventListener("click", async (event) => {
  const card = event.target.closest(".history-card");
  if (!card) return;
  const job = await requestJson(`/api/jobs/${card.dataset.jobId}`);
  showJob(job);
});

reuseCurrentBtn.addEventListener("click", () => {
  if (!currentJob) return;
  field("#prompt-cn").value = currentJob.prompt_cn || "";
  field("#width").value = currentJob.width || 768;
  field("#height").value = currentJob.height || 768;
  field("#steps").value = currentJob.steps || 12;
  field("#cfg").value = currentJob.cfg || 6;
  field("#seed").value = currentJob.seed || "";
  field("#checkpoint").value = currentJob.checkpoint || "";
  field("#lora-name").value = currentJob.lora_name || "";
  field("#lora-strength").value = currentJob.lora_strength || 0;
});

document.querySelectorAll("[data-size]").forEach((button) => {
  button.addEventListener("click", () => {
    const [width, height] = button.dataset.size.split("x");
    field("#width").value = width;
    field("#height").value = height;
  });
});

refreshHistoryBtn.addEventListener("click", loadHistory);
refreshPresetsBtn.addEventListener("click", loadPresets);

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

async function loadPresets() {
  try {
    characters = await requestJson("/api/characters");
    characterSelect.innerHTML =
      `<option value="">不使用预设</option>` +
      characters.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join("");
  } catch (error) {
    characterSelect.innerHTML = `<option value="">角色预设加载失败</option>`;
  }

  try {
    const loras = await requestJson("/api/loras");
    loraSelect.innerHTML =
      `<option value="">不使用 / 角色默认</option>` +
      loras.map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)}</option>`).join("");
  } catch (error) {
    loraSelect.innerHTML = `<option value="">LoRA 列表加载失败</option>`;
  }
}

loadPresets();
loadHistory();
