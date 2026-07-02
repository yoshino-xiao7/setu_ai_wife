# 角色 LoRA 和角色预设

## 添加 LoRA

把 LoRA 文件放到 `COMFYUI_MODELS_DIR/loras` 下。可以在 `config/lora_metadata.json` 中补充展示元数据，让云端 UI 显示友好的名称和触发词。

## 角色预设

角色预设位于 `config/characters.json`。预设可以指定 LoRA、默认权重、提示词片段和展示元数据。worker 会通过 `/ai-worker/capabilities` 把这些预设上报给云端后端。

## 推荐权重

单角色生图可以从 `0.7` 到 `0.9` 开始按模型调整。双角色生图会使用 `DUAL_LORA_STRENGTH_CAP` 限制权重，减少角色互相污染。

## 刷新云端 UI

修改 LoRA 文件或元数据后，重启 cloud worker，或者等待下一次能力上报。前端读取 `/ai/capabilities`，不会直接扫描本地文件。
