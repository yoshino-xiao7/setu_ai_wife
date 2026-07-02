# 模型

## 目录结构

默认模型根目录：

```text
tools/ComfyUI_windows_portable/ComfyUI/models
```

预期子目录：

- `checkpoints`
- `loras`
- `vae`

## 元数据

可选展示元数据位于：

- `config/checkpoint_metadata.json`
- `config/lora_metadata.json`
- `config/characters.json`
- `config/prompt_presets.json`
- `config/prompt_knowledge.json`

## 命名

请使用稳定文件名，因为云端任务会记录选中的 checkpoint 和 LoRA 名称。建议使用可读模型名，避免在有活跃任务后重命名文件。

## 许可

只安装和提供部署方有权使用的模型。如需记录授权说明，请放在生成运行时目录之外。

## 默认 Checkpoint

在 `.env` 中设置 `DEFAULT_CHECKPOINT`，值必须是 `COMFYUI_MODELS_DIR/checkpoints` 下真实存在的 checkpoint 文件名。
