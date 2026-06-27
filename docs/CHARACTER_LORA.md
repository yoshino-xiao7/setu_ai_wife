# CHARACTER LORA

This project supports the article-style character LoRA flow.

## Add a LoRA

Put the LoRA file in:

```text
tools\ComfyUI_windows_portable\ComfyUI\models\loras
```

Then edit:

```text
config\characters.json
```

Add a preset:

```json
{
  "id": "my_character",
  "name": "角色显示名",
  "lora_name": "my_character.safetensors",
  "lora_strength": 0.8,
  "trigger_words": "trigger words from the LoRA page",
  "default_positive": "1girl, solo",
  "style_tags": "anime style, detailed eyes, high quality",
  "notes": "source, license, and usage tips"
}
```

Restart the local service:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_service.ps1
```

Open:

```text
http://127.0.0.1:7861
```

## How presets work

- `trigger_words` are injected into the positive prompt.
- `default_positive` is injected before the translated user prompt.
- `style_tags` are injected before the translated user prompt.
- `lora_name` and `lora_strength` are sent to ComfyUI's `LoraLoader`.
- If the UI manually selects a different LoRA, the manual selection wins.

## Recommended strength

Start with `0.65` to `0.9`.

If the character identity is weak, raise it. If the image becomes stiff or distorted, lower it.

## Current status

The checkpoint is configured:

```text
waiIllustriousSDXL_v170.safetensors
```

The LoRA directory is currently empty unless you add files.

