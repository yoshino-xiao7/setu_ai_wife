# 本机 AI 绘图服务

这是雪涼云 AI 绘画的本机服务项目。它主要负责在本机运行 ComfyUI 出图，并作为云端 AI 绘图业务的 Worker 主动领取任务。

默认情况下，本项目只监听 `127.0.0.1`，不会把本机 ComfyUI 或 FastAPI 暴露到公网。云端用户生图时，也不是云服务器访问你的本机，而是本机 Worker 主动轮询云端任务。

## 项目作用

本项目包含三层能力：

- 本机 ComfyUI：真正负责 AI 出图。
- 本机 FastAPI：提供本地网页、API、SQLite 历史、ComfyUI 调用封装。
- Cloud Worker：主动连接云端后端，领取云端用户提交的生图任务，调用本机 FastAPI 出图，并把结果回传云端。

云端后端负责用户鉴权、扣积分、任务队列、OSS 存储、审核、广场、管理员管理。本机只做生成，不保存云端业务数据。

## 常用地址

- 本机 AI 服务：`http://127.0.0.1:7861`
- 本机 ComfyUI：`http://127.0.0.1:8188`
- 云端后端示例：`https://api.yukiryou.icu`
- 云端前端示例：`https://cloud.yukiryou.icu`

## 目录说明

```text
setu_ai_wife/
  app/                 FastAPI 后端、ComfyUI 客户端、Worker 代码
  config/              角色预设配置
  data/                SQLite 数据库
  docs/                安装、部署、模型、Worker 文档
  logs/                启动脚本和 Worker 日志
  outputs/             本机临时输出图
  scripts/             Windows 启动脚本
  static/              本机网页 UI
  tools/               ComfyUI Portable 等本机工具
  workflows/           ComfyUI workflow JSON
  .env                 本机实际配置
  .env.example         配置模板
```

## 第一次安装

全新 Windows 机器从零安装请看：

- [docs/INSTALL.md](docs/INSTALL.md)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [docs/MODELS.md](docs/MODELS.md)
- [docs/OPERATIONS.md](docs/OPERATIONS.md)

简要流程：

1. 安装 Git、Python 3.12、7-Zip、Visual C++ Redistributable、Ollama。
2. 安装或解压 ComfyUI Portable。
3. 把 checkpoint、LoRA、VAE 放入 ComfyUI 的 `models` 目录。
4. 复制 `.env.example` 为 `.env`。
5. 按实际模型名和云端配置填写 `.env`。

## .env 配置

`.env.example` 是模板，实际运行读取 `.env`。

本机基础配置：

```dotenv
HOST=127.0.0.1
PORT=7861
COMFYUI_URL=http://127.0.0.1:8188
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b
OUTPUT_DIR=outputs
DATABASE_PATH=data/jobs.sqlite3
CHARACTERS_PATH=config/characters.json
PROMPT_KNOWLEDGE_PATH=config/prompt_knowledge.json
COMFYUI_MODELS_DIR=tools/ComfyUI_windows_portable/ComfyUI/models
DEFAULT_CHECKPOINT=waiIllustriousSDXL_v170.safetensors
DEFAULT_STEPS=35
DEFAULT_CFG=4.5
DEFAULT_SAMPLER=euler
DEFAULT_SCHEDULER=normal
PROMPT_TRANSLATION_TIMEOUT_SECONDS=45
COMFYUI_TIMEOUT_SECONDS=15
```

云端 Worker 配置：

```dotenv
LOCAL_AI_URL=http://127.0.0.1:7861
CLOUD_API_URL=https://api.yukiryou.icu
AI_WORKER_TOKEN=这里填写云端后端同一个 AI_WORKER_TOKEN
AI_WORKER_ID=local-comfyui-worker
AI_WORKER_NAME=Local ComfyUI Worker
AI_WORKER_VERSION=0.1.0
AI_WORKER_POLL_SECONDS=5
AI_WORKER_CAPABILITY_REPORT_SECONDS=60
AI_WORKER_CLEANUP_OUTPUTS=true
```

重点说明：

- `CLOUD_API_URL` 必须填写云端后端地址，不是前端地址。
- `AI_WORKER_TOKEN` 必须和云端后端 `.env` 里的 `AI_WORKER_TOKEN` 完全一致。
- OSS 配置不放在本项目里，OSS 配置继续放在云端后端。
- `COMFYUI_MODELS_DIR` 必须指向真实的 ComfyUI `models` 目录，否则云端页面看不到 LoRA 和模型。

## 一键启动云端生图

平时要让云端用户可以生图，直接运行：

```powershell
cd C:\Users\rdpuser\Documents\setu_cd\setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\start_cloud_all.ps1
```

这个脚本会依次启动：

1. ComfyUI
2. 本机 FastAPI 服务
3. Cloud Worker

启动成功后：

- 本机页面能打开 `http://127.0.0.1:7861`
- ComfyUI 能打开 `http://127.0.0.1:8188`
- 云端 `/dashboard/ai-draw` 刷新模型后能看到本机 checkpoint 和 LoRA
- 云端用户提交任务后，本机会自动领取并出图

## 只启动本机服务

如果只想本机自己测试，不接云端：

```powershell
cd C:\Users\rdpuser\Documents\setu_cd\setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1
```

或者分开启动：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_comfyui.ps1
powershell -ExecutionPolicy Bypass -File scripts\start_service.ps1
```

然后打开：

```text
http://127.0.0.1:7861
```

## 只启动 Cloud Worker

如果 ComfyUI 和本机 FastAPI 已经启动，只需要启动 Worker：

```powershell
cd C:\Users\rdpuser\Documents\setu_cd\setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\start_cloud_worker.ps1
```

## 模型和 LoRA 放置位置

默认 ComfyUI 模型目录：

```text
tools/ComfyUI_windows_portable/ComfyUI/models
```

常用子目录：

```text
models/checkpoints/   checkpoint 大模型
models/loras/         LoRA 文件
models/vae/           VAE 文件
```

新增 LoRA 后：

1. 把 `.safetensors` 文件放入 `models/loras/`。
2. 重启 `scripts/start_cloud_all.ps1`，或者等待 Worker 下次能力上报。
3. 打开云端 `/dashboard/ai-draw`，点击刷新模型。
4. LoRA 下拉框里应该能看到新文件。

LoRA 和角色预设说明：

- [docs/CHARACTER_LORA.md](docs/CHARACTER_LORA.md)
- 角色预设文件：`config/characters.json`

## 生成图保存和清理

本机临时图片会进入：

```text
outputs/
```

云端模式下，图片流程是：

1. 本机 ComfyUI 生成临时图片。
2. 本机 Worker 读取图片 bytes。
3. Worker 调用云端 complete 接口。
4. 云端后端写入 OSS。
5. 如果 `AI_WORKER_CLEANUP_OUTPUTS=true`，上传成功后本机会删除对应临时图。

也就是说，云端用户最终看图走 OSS，不依赖本机图片文件。

## 云端 OSS 说明

本项目不配置 OSS。

OSS 配置在云端后端项目 `setu_api_full` 的生产环境变量里。AI 生图使用云端后端已有的 `StorageService` 写入 OSS。

云端后端需要具备这些 OSS 权限：

- `oss:PutObject`
- `oss:GetObject`
- `oss:DeleteObject`

AI 生图默认路径：

```text
ai/private/{userId}/{jobId}.png
ai/public/general/{jobId}.png
ai/public/r18/{jobId}.png
```

## 日志位置

启动脚本日志：

```text
logs/
```

常见排查顺序：

1. ComfyUI 是否启动成功。
2. FastAPI 是否启动成功。
3. Worker 是否能连接云端。
4. Worker Token 是否一致。
5. 云端后端日志是否有 OSS 或任务回写错误。

## 常见问题

### CLOUD_API_URL is empty

说明 `.env` 里的 `CLOUD_API_URL` 没填。

填写云端后端地址，例如：

```dotenv
CLOUD_API_URL=https://api.yukiryou.icu
```

### 云端页面看不到 LoRA

检查：

- `COMFYUI_MODELS_DIR` 是否指向真实 ComfyUI `models` 目录。
- LoRA 是否放在 `models/loras/`。
- Worker 是否启动。
- 云端 `/ai/capabilities` 是否能返回 LoRA。
- 前端 `/dashboard/ai-draw` 是否点了刷新模型。

### 任务一直排队

检查：

- 本机 `start_cloud_all.ps1` 是否还在运行。
- `AI_WORKER_TOKEN` 是否和云端后端一致。
- `CLOUD_API_URL` 是否是后端地址。
- 云端后端 `/ai-worker/jobs/claim` 是否有鉴权错误。
- ComfyUI 是否能正常访问 `http://127.0.0.1:8188`。

### complete 返回 500

通常看云端后端日志。

常见原因：

- OSS RAM 权限不足。
- bucket 或 endpoint 配置错误。
- 上传图片超过 `AI_MAX_COMPLETE_IMAGE_BYTES`。
- 云端数据库迁移未执行。

### 删除 AI 生图后 OSS 文件没删

检查云端 OSS RAM 权限是否包含：

```text
oss:DeleteObject
```

数据库删除和 OSS 删除是分开的。后端会尽量删除 OSS 文件，如果权限不足，会写日志但不会阻止记录被隐藏。

## 本地检查命令

检查 Python 代码是否能编译：

```powershell
cd C:\Users\rdpuser\Documents\setu_cd\setu_ai_wife
.\.venv\Scripts\python.exe -m compileall app
```

检查基础环境：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
```

## 相关文档

- [安装说明](docs/INSTALL.md)
- [本机部署说明](docs/DEPLOYMENT.md)
- [模型放置说明](docs/MODELS.md)
- [运维和故障排查](docs/OPERATIONS.md)
- [角色 LoRA 预设](docs/CHARACTER_LORA.md)
- [本地提示词知识库](docs/PROMPT_KNOWLEDGE.md)
- [云端 Worker 模式](docs/CLOUD_WORKER.md)
- [实现日志](docs/IMPLEMENTATION_LOG.md)

## 许可证

本项目使用 [MIT License](LICENSE)。
