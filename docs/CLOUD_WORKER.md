# Cloud Worker Mode

## 角色分工

`setu_ai_wife` 在 cloud worker 模式下不再作为公网业务入口，只做本机 AI 绘图 worker：

1. 扫描本机 ComfyUI 模型目录和角色预设。
2. 向云端后端上报 checkpoint、LoRA、VAE、角色预设。
3. 轮询云端任务。
4. 调用本机 `http://127.0.0.1:7861/api/generate` 出图。
5. 读取本机临时图片并回传云端。
6. 云端写入 OSS，worker 可按配置清理本机临时图。

云服务器不需要访问本机 IP，本机也不需要做内网穿透。

## 环境变量

复制 `.env.example` 到 `.env` 后补充：

```dotenv
LOCAL_AI_URL=http://127.0.0.1:7861
CLOUD_API_URL=https://your-api.example.com
AI_WORKER_TOKEN=replace-with-cloud-token
AI_WORKER_ID=local-comfyui-worker
AI_WORKER_NAME=Local ComfyUI Worker
AI_WORKER_VERSION=0.1.0
AI_WORKER_POLL_SECONDS=5
AI_WORKER_CAPABILITY_REPORT_SECONDS=60
AI_WORKER_CLEANUP_OUTPUTS=true
```

`AI_WORKER_TOKEN` 必须与云端后端的 `AI_WORKER_TOKEN` 一致。

## LoRA 和模型发现

worker 会扫描：

- `COMFYUI_MODELS_DIR/checkpoints`
- `COMFYUI_MODELS_DIR/loras`
- `COMFYUI_MODELS_DIR/vae`
- `CHARACTERS_PATH` 指向的角色预设 JSON

默认 `COMFYUI_MODELS_DIR` 为：

```text
tools/ComfyUI_windows_portable/ComfyUI/models
```

新增 LoRA 后，重启 worker 或等待下一次能力上报。前端 `/dashboard/ai-draw` 读取的是云端 `/ai/capabilities`，所以只要 worker 上报成功，云端页面就能看到本机 LoRA。

## 启动顺序

一键启动云端生图所需的全部本机组件：

```powershell
cd C:\Users\rdpuser\Documents\setu_cd\setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts/start_cloud_all.ps1
```

这个脚本会依次启动 ComfyUI、本机 FastAPI 服务和 cloud worker，并把日志写到 `logs/`。

也可以按下面步骤手动启动。

1. 启动 ComfyUI，确认 `http://127.0.0.1:8188` 可访问。
2. 启动本机 FastAPI 服务：

```powershell
cd C:\Users\rdpuser\Documents\setu_cd\setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts/start_service.ps1
```

3. 启动 cloud worker：

```powershell
cd C:\Users\rdpuser\Documents\setu_cd\setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts/start_cloud_worker.ps1
```

## 图片流转

v1 采用 `CLOUD_COMPLETE_BASE64`：

1. 本机 ComfyUI 生成临时图片到 `OUTPUT_DIR`。
2. worker 读取图片 bytes。
3. worker 调用云端 `POST /ai-worker/jobs/{id}/complete`。
4. 云端通过 `StorageService.putObject` 写入 OSS 私有路径 `ai/private/{userId}/{jobId}.png`。
5. 用户通过云端签名 URL 查看自己的图片。
6. 审核通过后，云端复制到 `ai/public/general/{jobId}.png` 或 `ai/public/r18/{jobId}.png`。

如果 `AI_WORKER_CLEANUP_OUTPUTS=true`，worker 在云端 complete 成功后会删除本机 `outputs` 下对应临时图片；本地服务复制图片后也会清理 ComfyUI `output/local_ai_drawing` 下的原始输出。

## 故障排查

- `/ai/capabilities` 没有 LoRA：确认 `COMFYUI_MODELS_DIR` 指向真实 ComfyUI `models` 目录，且 worker 已启动并能访问云端。
- 任务一直 `QUEUED`：确认 worker token 一致，并查看 worker 控制台是否有 claim 错误。
- 任务 `FAILED` 且已扣积分：worker 调用 `/ai-worker/jobs/{id}/fail` 后云端会自动退款；如果没有退款，检查该任务是否已经绑定到正确 worker。
- 云端看不到图片：确认 OSS pending bucket 配置正确，`StorageService.putObject` 可用，且图片大小不超过 `AI_MAX_COMPLETE_IMAGE_BYTES`。
- 本机生成失败：先在 `http://127.0.0.1:7861` 本地页面直接生成一张，确认 ComfyUI 和模型工作正常。

## 本地检查

```powershell
cd C:\Users\rdpuser\Documents\setu_cd\setu_ai_wife
.\.venv\Scripts\python.exe -m compileall app
```
