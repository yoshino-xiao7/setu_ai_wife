# AGENTS.md

## Project Overview

Setu AI Wife is the Windows-only local AI drawing worker for XueLiang Cloud. It runs local ComfyUI image generation, exposes a local FastAPI service, and can poll the cloud backend for AI drawing jobs.

This repository is not expected to exist on every macOS development machine. Frontend and backend tasks should treat it as optional unless the user is working on local AI drawing, ComfyUI, worker polling, model metadata, or prompt generation.

## Stack

- Python 3.12
- FastAPI
- SQLite for local job history
- ComfyUI Portable on Windows
- PowerShell startup scripts
- Optional Ollama prompt translation

## Key Paths

- `app/main.py`: FastAPI application and local API routes.
- `app/cloud_worker.py`: Cloud worker polling, job claiming, generation, and upload loop.
- `app/comfyui.py`: ComfyUI client integration.
- `app/prompting.py`: Prompt assembly and translation-facing logic.
- `app/prompt_knowledge.py`: Prompt knowledge loading.
- `app/config.py`: Environment and runtime settings.
- `config/characters.json`: Character presets.
- `config/lora_metadata.json`: LoRA metadata.
- `config/checkpoint_metadata.json`: Checkpoint metadata.
- `config/prompt_knowledge.json`: Prompt knowledge data.
- `workflows/`: ComfyUI workflow JSON.
- `scripts/`: Windows PowerShell startup and environment check scripts.
- `docs/`: Installation, deployment, model, operations, and worker notes.

## Common Commands

Check Windows local dependencies:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
```

Start local ComfyUI plus FastAPI service:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1
```

Start ComfyUI, FastAPI service, and cloud worker:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_cloud_all.ps1
```

## Development Rules

- Before code changes, follow `docs/maintainability.md`.
- Keep this project Windows-local unless the user explicitly asks for cross-platform support.
- Do not commit `.env`, local databases, logs, outputs, ComfyUI portable tools, model files, or other heavy runtime assets.
- Keep machine-specific paths in `.env` or local shell configuration. Do not hard-code user home directories in committed files.
- Preserve the default local binding behavior. ComfyUI and FastAPI should remain local-only unless the user explicitly asks to expose them.
- For cloud worker contract changes, inspect the backend AI generation worker endpoints in `../setu_api_full` and the frontend AI drawing flow in `../setu_cloud`.
- For model, LoRA, character, or prompt changes, inspect the relevant `config/` JSON and prompt code before editing.
- If docs render as garbled text in PowerShell, read them as UTF-8.

### Prompt Presets Organization (`config/prompt_presets.json`)

**This rule must be followed every time you edit or add to the presets file** (to prevent it from becoming scattered again):

- **Never append new presets at the end.** Always insert into the correct group.
- **SFW grouping order (by `category_type`):**
  构图 → 场景 → 日常 → 制服 → 泳装 → 运动 → 内衣
- **NSFW grouping order (by `category_type`):**
  基础 → 可见度 → 构图 → 场景 → 单人女性 → 姿势 → 玩具 → 多人 → 百合 → 扶她 → BDSM → 怪物/幻想 → 公共 → 服饰 → 服装 → 体液 → 特殊癖好 → POV → 女性主导 → 兽耳/幻想 → 口交
- Within each `category_type` group:
  - General presets first (WAI/default).
  - Model-specific variants after (Anima / Animagine only).
- All **小众生活瞬间** (niche everyday moments) must go into `场景` or `构图`.
- When adding new presets (whether manually or when I help you generate them):
  1. Decide the correct `category` ("SFW" or "NSFW") and `category_type`.
  2. Find the right group in the array.
  3. Insert the new object in the appropriate position within that group (general before variants).
- The file includes `_meta.organization_rules` as self-documentation – always respect it.
- After edits, the overall array must stay in the logical grouped order above.
- If it ever gets out of order, use the previous reordering logic (group by the orders above, then sort general before variants within groups). A quick way: run a Python snippet that rebuilds the array following the sfw_order / nsfw_order lists (I can provide the exact code when needed).

### Prompt Writing Grammar

Write presets as Danbooru tags, not English sentences. WAI and Anima / Animagine learn from tags.

Field roles:

- `trigger_words`: what this preset is (pose, scene, clothing type).
- `default_positive`: locks that are not already in trigger words (one expression, gaze, joint-level pose, clothing colors, palette).
- `style_tags`: rendering only (`masterpiece, best quality, highres` plus lighting/skin).
- `default_negative`: quality/anatomy plus this preset's anti-locks (opposite expression, conflicting colors, failed pose). Do not globally ban `looking at viewer`.

Positive tag order: subject → identity → one expression → gaze → pose → clothing/colors → palette → lighting/skin → simple background.

When stacking presets, each entry is one layer, not a full scene:

- 场景: place and light only. Never write dress, sundress, bikini, coat, or nude.
- 动作: what is happening. Do not invent a second outfit.
- 衣服: the garment only. Never write beach, flower field, bedroom, or a default smile.

A stack like 花海 + 可爱比基尼 is a frilled bikini in a flower field, not a sundress. Clothing tags win over leftover scene clothes.

Forbidden prose: `beautiful girl`, `cute girl`, `excellent composition`, `refined atmosphere`, `modest clothing`.

Character presets in `config/characters.json` are identity-only:

- Keep name, franchise, hair, eyes, ears/tails/horns, and signature head accessories.
- Do not put outfits, sleeves, uniforms, body-size tags, or `anime style / detailed eyes / high quality` on a character.
- Outfit and lighting belong to the user prompt or a style preset, so a bikini request is not fighting a default miko outfit.

When you ask me to add new presets in the future, I will:
- Pick the correct `category_type`.
- Insert the entry into the right group (not append at the end).
- Keep general before model variants.
- Write short Danbooru tags and lock expression/color in the negative.

Runtime service is unaffected (it only loads the `prompt_presets` array and ignores `_meta`). This is purely for maintainability during development.

## Verification Guidance

- For config or startup changes, run `scripts\check_env.ps1`.
- For worker changes, inspect logs under `logs/` locally but do not commit them.
- For cloud contract changes, verify the matching backend compile/tests when practical and confirm frontend API types remain compatible.
