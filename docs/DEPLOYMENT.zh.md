# 部署说明

## 本地端口

- ComfyUI：`http://127.0.0.1:8188`
- 本地 AI 服务：`http://127.0.0.1:7861`
- Ollama：`http://127.0.0.1:11434`

## 启动顺序

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\start_cloud_all.ps1
```

手动顺序：

1. ComfyUI
2. 本地 FastAPI 服务
3. Cloud worker

## 配置

复制 `.env.example` 为 `.env`，设置本地模型路径、默认 checkpoint、`CLOUD_API_URL` 和 `AI_WORKER_TOKEN`。

机器相关路径必须放在 `.env` 或本地 shell profile 中，不要提交到文档或脚本。

## 冒烟测试

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
.\.venv\Scripts\python.exe -m compileall app
```

允许云端任务前，打开 `http://127.0.0.1:7861` 并确认健康面板正常。
