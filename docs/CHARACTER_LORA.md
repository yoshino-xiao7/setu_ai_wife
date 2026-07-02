# Character LoRA and Character Presets

## Adding a LoRA

Place LoRA files under `COMFYUI_MODELS_DIR/loras`. Add optional display metadata in `config/lora_metadata.json` so the cloud UI can show friendly names and trigger words.

## Character Presets

Character presets live in `config/characters.json`. A preset can point to a LoRA, default strength, prompt fragments, and display metadata. The worker reports these presets to the cloud backend through `/ai-worker/capabilities`.

## Recommended Strength

For single-character generation, start around `0.7` to `0.9` and tune per model. For dual-character generation, the worker caps strength with `DUAL_LORA_STRENGTH_CAP` to reduce character bleed.

## Refreshing the Cloud UI

Restart the cloud worker or wait for the next capability report after changing LoRA files or metadata. The frontend reads `/ai/capabilities`; it does not scan local files directly.
