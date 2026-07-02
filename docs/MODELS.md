# Models

## Directory Layout

The default model root is:

```text
tools/ComfyUI_windows_portable/ComfyUI/models
```

Expected subdirectories:

- `checkpoints`
- `loras`
- `vae`

## Metadata

Optional display metadata lives in:

- `config/checkpoint_metadata.json`
- `config/lora_metadata.json`
- `config/characters.json`
- `config/prompt_presets.json`
- `config/prompt_knowledge.json`

## Naming

Use stable file names because cloud jobs store selected checkpoint and LoRA names. Prefer readable model names and avoid renaming files after users have active jobs.

## Licensing

Only install and serve models that the deployment is allowed to use. Keep license notes outside generated runtime directories if needed.

## Default Checkpoint

Set `DEFAULT_CHECKPOINT` in `.env` to a checkpoint that exists under `COMFYUI_MODELS_DIR/checkpoints`.
