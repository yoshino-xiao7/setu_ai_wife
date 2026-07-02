# 实现日志

## 当前状态

本地 worker 当前包含：

- 本地 FastAPI 生图服务。
- ComfyUI 集成。
- 基于 Ollama 的提示词翻译。
- SQLite 任务历史。
- Cloud worker 轮询模式。
- checkpoint、LoRA、VAE、角色和提示词预设能力上报。
- 提示词翻译任务领取。
- 本地图片路径对账和删除指令处理。

## 待处理的本机步骤

- `.env` 保持机器本地化，不提交。
- 模型文件和 portable runtime 不进 git。
- 修改本地路径或运行时后，执行 `scripts/check_env.ps1`。
