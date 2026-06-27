# MODELS

## Directory layout

For ComfyUI Portable, use these model directories:

- `ComfyUI\models\checkpoints`
- `ComfyUI\models\loras`
- `ComfyUI\models\vae`

The service sends model filenames to ComfyUI. Filenames must match exactly.

## Recommended naming

Use readable names and avoid spaces where possible:

- `anime_sdxl_base.safetensors`
- `character_name_v1.safetensors`
- `sdxl_vae.safetensors`

## Licensing

Before downloading or using a model, confirm:

- Whether commercial use is allowed.
- Whether redistribution is allowed.
- Whether the model has content restrictions.
- Whether character LoRA files are fan-made and limited to personal use.

## First checkpoint

Edit `.env`:

```env
DEFAULT_CHECKPOINT=your-checkpoint-filename.safetensors
```

Restart the service after changing `.env`.

## Character LoRA presets

Put LoRA files here:

```text
tools\ComfyUI_windows_portable\ComfyUI\models\loras
```

Then edit `config\characters.json`:

```json
{
  "id": "my_character",
  "name": "角色显示名",
  "lora_name": "my_character.safetensors",
  "lora_strength": 0.8,
  "trigger_words": "official trigger words from the LoRA page",
  "default_positive": "1girl, solo",
  "style_tags": "anime style, detailed eyes, high quality",
  "notes": "optional"
}
```

The local UI loads these presets from `/api/characters`. When a preset is selected, the backend injects its trigger words and style tags into the positive prompt, and applies its LoRA unless the UI manually chooses another LoRA.
