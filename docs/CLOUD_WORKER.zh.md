# Cloud Worker 模式

`setu_ai_wife` 是 Windows 本地 AI 绘图运行时。cloud worker 模式下，它不提供公开业务 API，而是轮询云端后端，执行本地 ComfyUI/Ollama 工作，并把结果回传云端。

## 职责

1. 扫描本地 ComfyUI 模型和本地元数据文件。
2. 向云端后端上报 checkpoint、LoRA、VAE、角色、提示词预设和 worker 状态。
3. 领取生图任务、提示词翻译任务和本地图片删除指令。
4. 调用 `LOCAL_AI_URL` 指向的本地 FastAPI 服务进行生图。
5. 读取生成图片字节并完成云端任务。
6. 保留本地归档图，除非云端管理员下发本地图片删除指令。

云服务器不需要直接访问 worker 机器。

## 环境变量

复制 `.env.example` 为 `.env`，至少填写：

```dotenv
LOCAL_AI_URL=http://127.0.0.1:7861
CLOUD_API_URL=https://your-api.example.com
AI_WORKER_TOKEN=replace-with-cloud-token
AI_WORKER_ID=local-comfyui-worker
AI_WORKER_NAME=Local ComfyUI Worker
AI_WORKER_VERSION=0.1.0
AI_WORKER_POLL_SECONDS=5
AI_WORKER_CAPABILITY_REPORT_SECONDS=60
AI_WORKER_CLEANUP_OUTPUTS=false
```

`AI_WORKER_TOKEN` 必须与云端后端的 `AI_WORKER_TOKEN` 一致。

## 模型和元数据发现

worker 会扫描：

- `COMFYUI_MODELS_DIR/checkpoints`
- `COMFYUI_MODELS_DIR/loras`
- `COMFYUI_MODELS_DIR/vae`
- `CHARACTERS_PATH`
- `LORA_METADATA_PATH`
- `CHECKPOINT_METADATA_PATH`
- `PROMPT_PRESETS_PATH`
- `PROMPT_KNOWLEDGE_PATH`

新增模型或元数据后，重启 worker 或等待下一次能力上报。

## 启动

启动全部本地组件：

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\start_cloud_all.ps1
```

手动启动顺序：

1. 启动 ComfyUI，并确认 `http://127.0.0.1:8188` 可访问。
2. 启动本地 FastAPI 服务：

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\start_service.ps1
```

3. 启动 cloud worker：

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\start_cloud_worker.ps1
```

## 图片流转

1. 云端后端创建排队任务。
2. worker 领取任务并标记为运行中。
3. 本地 ComfyUI 把生成图片写到 `OUTPUT_DIR`。
4. worker 标记任务上传中，并把图片字节提交到 `/ai-worker/jobs/{id}/complete`。
5. 云端后端写入私有 OSS，记录 hash、大小和私有保留截止时间。
6. worker 把本地归档路径回报给云端。
7. 用户提交审核且管理员通过后，后端发布公开副本。

启动时也会尽可能把旧的本地已完成图片与云端历史进行对账。

## 提示词翻译流程

worker 还会领取 `/ai-worker/prompt-translations/claim`，通过本地提示词流水线翻译提示词，并完成或失败对应翻译任务。

## 本地删除流程

管理员可以从云端控制台申请删除本地归档图。worker 从 `/ai-worker/local-image-deletions/claim` 领取指令，删除本地归档路径，并上报成功或失败。

## 故障排查

- `/ai/capabilities` 没有 LoRA：检查 `COMFYUI_MODELS_DIR`、元数据 JSON、worker 启动和云端连接。
- 任务一直是 `QUEUED`：检查 `AI_WORKER_TOKEN`、`CLOUD_API_URL` 和 worker 控制台 claim 错误。
- 任务 `FAILED`：查看 `workerStage`、`workerDetail` 和本地日志。
- 云端预览不可用：检查 OSS 配置和 `AI_MAX_COMPLETE_IMAGE_BYTES`。
- 本地生成失败：先在 `http://127.0.0.1:7861` 直接测试生图。

## 验证

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
.\.venv\Scripts\python.exe -m compileall app
```
