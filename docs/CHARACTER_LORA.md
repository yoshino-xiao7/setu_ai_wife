# 角色 LoRA 和角色预设

本项目支持“LoRA 元信息 + 角色预设”的素材选择流程。云端前端不会直接读取本机目录，而是读取本机 Worker 上报到云端的能力缓存。

## 添加 LoRA

把 LoRA 文件放到：

```text
tools\ComfyUI_windows_portable\ComfyUI\models\loras
```

然后编辑：

```text
config\characters.json
```

新增角色预设：

```json
{
  "id": "my_character",
  "name": "角色显示名",
  "category": "原神",
  "category_type": "游戏角色",
  "lora_name": "my_character.safetensors",
  "lora_strength": 0.8,
  "trigger_words": "trigger words from the LoRA page",
  "default_positive": "1girl, solo",
  "style_tags": "anime style, detailed eyes, high quality",
  "preview_image": "https://your-oss.example/ai-presets/my-character.webp",
  "recommended_checkpoint": "waiIllustriousSDXL_v170.safetensors",
  "notes": "来源、授权、触发词和使用建议"
}
```

如果只是单独给 LoRA 补展示信息，编辑：

```text
config\lora_metadata.json
```

```json
{
  "name": "my_character.safetensors",
  "display_name": "角色显示名",
  "category": "原神",
  "category_type": "游戏角色",
  "trigger_words": "trigger words from the LoRA page",
  "recommended_strength": 0.8,
  "recommended_checkpoint": "waiIllustriousSDXL_v170.safetensors",
  "preview_image": "https://your-oss.example/ai-presets/my-character.webp",
  "notes": "适合竖屏人像，推荐强度 0.7-0.9。"
}
```

`category` 是云端选择器的大目录，可以填游戏名、作品名或风格名，例如 `原神`、`鸣潮`、`萝莉风格`、`校园制服`。`preview_image` 建议填写 OSS 或公网图片 URL；本机磁盘路径不能保证云端用户能访问。

重启本机服务：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_service.ps1
```

Open:

```text
http://127.0.0.1:7861
```

## 预设如何生效

- `trigger_words` 会注入正向提示词。
- `default_positive` 会作为角色默认正向词。
- `style_tags` 会作为风格补充词。
- `lora_name` 和 `lora_strength` 会发送给 ComfyUI 的 `LoraLoader`。
- 用户在云端前端手动选择 LoRA 时，手动选择优先。

## 推荐强度

建议从 `0.65` 到 `0.9` 开始。

角色特征不明显就适当提高；画面变僵硬、过拟合或崩坏就降低。

## 当前状态

当前 checkpoint：

```text
waiIllustriousSDXL_v170.safetensors
```

LoRA 目录是否有文件取决于你本机实际放入的模型。新增 LoRA 后，重启 Worker 或等待下一次能力上报，云端选择器会刷新出新素材。
