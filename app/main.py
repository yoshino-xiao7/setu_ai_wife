from __future__ import annotations

import json
import base64
import os
import uuid
import time
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFilter
from pydantic import BaseModel, Field

from app.comfyui import (
    ComfyUIClient,
    ComfyUIExecutionError,
    build_anima_img2img_workflow,
    build_anima_workflow,
    build_brushnet_inpaint_workflow,
    build_img2img_workflow,
    build_inpaint_workflow,
    build_mask_conditioning_workflow,
    build_workflow,
    clamp_img2img_denoise,
    is_anima_checkpoint,
    resolve_classic_sampling,
    random_seed,
)
from app.config import Settings, get_settings
from app.db import JobStore
from app.presets import find_character, list_loras, load_characters, load_prompt_presets, merge_tags
from app.prompt_tags import compose_stacked_negative, compose_stacked_prompt
from app.prompting import (
    PromptResult,
    PromptTranslationError,
    apply_lookback_negative_locks,
    apply_lookback_positive_locks,
    apply_nsfw_visibility_negative_profile,
    apply_nsfw_visibility_profile,
    filter_character_identity_tags,
    filter_nsfw_incompatible_tags,
    merge_unique_tags,
    translate_prompt,
)
from app.prompt_knowledge import knowledge_positive_tags


app = FastAPI(title="Local AI Drawing Service")

DUAL_CHARACTER_BLOCKED_TAGS = {
    "1girl",
    "1boy",
    "solo",
    "solo focus",
    "single girl",
    "single boy",
    "one girl",
    "one boy",
}

DUAL_CHARACTER_NEGATIVE_TAGS = (
    "merged characters, mixed character features, identical faces, "
    "shared hair color, shared outfit, conjoined bodies, "
    "extra people, duplicate character, extra limbs, "
    "disconnected hands, tangled limbs"
)
class GenerateRequest(BaseModel):
    prompt_cn: str = Field(..., min_length=1, max_length=1000)
    prompt_positive: str = ""
    prompt_negative: str = ""
    style_notes: str = ""
    generation_mode: str = "SINGLE"
    character_id: str | None = None
    second_character_id: str | None = None
    trigger_words: str = ""
    style_tags: str = ""
    width: int = Field(832, ge=512, le=1536)
    height: int = Field(1216, ge=512, le=1536)
    steps: int | None = Field(None, ge=8, le=60)
    cfg: float | None = Field(None, ge=1, le=15)
    seed: int | None = Field(None, ge=1, le=2**32 - 1)
    checkpoint: str | None = None
    lora_name: str = ""
    lora_strength: float = Field(0, ge=0, le=2)
    second_lora_name: str = ""
    second_lora_strength: float = Field(0, ge=0, le=2)
    character_mask_json: str = Field("", max_length=120000)
    nsfw_mode: bool = False
    nsfw_visibility_level: str = "STANDARD"
    light_hires: bool = False
    job_type: str = "TEXT2IMG"
    parent_job_id: int | None = None
    inpaint_instruction: str = ""
    inpaint_mask_json: str = Field("", max_length=120000)
    source_image_base64: str = ""
    denoise: float | None = Field(None, ge=0.25, le=0.70)
    cloud_job_id: int | None = None
    user_id: int | None = None
    storage_date: str | None = None


class TranslateRequest(BaseModel):
    prompt_cn: str = Field(..., min_length=1, max_length=1000)
    style_tags: str = ""
    negative_prompt: str = ""
    nsfw_mode: bool = False
    nsfw_visibility_level: str = "STANDARD"


def get_store(settings: Settings = Depends(get_settings)) -> JobStore:
    return JobStore(settings.database_path)


@app.post("/api/prompt/translate")
async def translate_api(payload: TranslateRequest, settings: Settings = Depends(get_settings)) -> PromptResult:
    try:
        return await translate_prompt(
            payload.prompt_cn,
            settings,
            style_tags=payload.style_tags,
            negative_prompt=payload.negative_prompt,
            nsfw_mode=payload.nsfw_mode,
            nsfw_visibility_level=payload.nsfw_visibility_level,
        )
    except PromptTranslationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/loras")
def loras(settings: Settings = Depends(get_settings)) -> list[dict]:
    return list_loras(settings)


@app.get("/api/characters")
def characters(settings: Settings = Depends(get_settings)) -> list[dict]:
    return [character.model_dump() for character in load_characters(settings.characters_path)]


@app.get("/api/health")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    checkpoints_dir = settings.comfyui_models_dir / "checkpoints"
    default_checkpoint_path = checkpoints_dir / settings.default_checkpoint
    capabilities = {
        "checkpoints": len(list(checkpoints_dir.glob("*"))) if checkpoints_dir.exists() else 0,
        "loras": len(list_loras(settings)),
        "vaes": len(list((settings.comfyui_models_dir / "vae").glob("*"))) if (settings.comfyui_models_dir / "vae").exists() else 0,
        "characters": len(load_characters(settings.characters_path)),
        "promptPresets": len(load_prompt_presets(settings.prompt_presets_path)),
    }
    checks = {
        "localService": {"ok": True, "message": "FastAPI is running."},
        "comfyui": await probe_http(f"{settings.comfyui_url.rstrip('/')}/system_stats"),
        "ollama": await probe_http(f"{settings.ollama_url.rstrip('/')}/api/tags"),
        "cloud": await probe_cloud(settings),
        "models": {
            "ok": settings.comfyui_models_dir.exists(),
            "message": str(settings.comfyui_models_dir),
        },
        "defaultCheckpoint": {
            "ok": default_checkpoint_path.exists(),
            "message": settings.default_checkpoint,
        },
    }
    return {
        "ok": all(item.get("ok") for item in checks.values()),
        "workerId": settings.ai_worker_id,
        "workerName": settings.ai_worker_name,
        "cloudApiUrl": settings.cloud_api_url,
        "cloudConfigured": bool(settings.cloud_api_url and settings.ai_worker_token),
        "cleanupOutputs": settings.ai_worker_cleanup_outputs,
        "dualCharacter": {
            "strategy": settings.dual_character_strategy,
            "loraStrengthCap": settings.dual_lora_strength_cap,
            "maskConditioningStrength": settings.dual_mask_conditioning_strength,
        },
        "generationDefaults": {
            "steps": settings.default_steps,
            "pollSeconds": settings.generation_poll_seconds,
        },
        "promptTranslation": {
            "ollamaGpuLayers": settings.ollama_prompt_num_gpu,
            "ollamaKeepAlive": settings.ollama_prompt_keep_alive,
            "thinking": False,
            "totalTimeoutSeconds": settings.prompt_translation_total_timeout_seconds,
        },
        "capabilities": capabilities,
        "checks": checks,
    }


async def probe_http(url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            response = await client.get(url)
        return {"ok": response.status_code < 500, "message": f"HTTP {response.status_code}"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


async def probe_cloud(settings: Settings) -> dict:
    if not settings.cloud_api_url or not settings.ai_worker_token:
        return {"ok": False, "message": "CLOUD_API_URL or AI_WORKER_TOKEN is empty."}
    try:
        async with httpx.AsyncClient(
            timeout=6,
            headers={"X-AI-Worker-Token": settings.ai_worker_token},
        ) as client:
            response = await client.get(f"{settings.cloud_api_url.rstrip('/')}/ai-worker/health")
        return {"ok": response.status_code < 500, "message": f"HTTP {response.status_code}"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@app.post("/api/generate")
async def generate(
    payload: GenerateRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: JobStore = Depends(get_store),
) -> dict[str, str]:
    job_type = str(payload.job_type or "TEXT2IMG").strip().upper() or "TEXT2IMG"
    if job_type == "INPAINT":
        raise HTTPException(status_code=400, detail="局部修复已下线，请使用一次性生成重新出图。")
    if job_type == "IMG2IMG":
        if is_dual_generation(payload):
            raise HTTPException(status_code=400, detail="图生图暂不支持双角色。")
        if not payload.source_image_base64.strip():
            raise HTTPException(status_code=400, detail="图生图需要上传源图。")
    character = find_character(settings, payload.character_id)
    second_character = find_character(settings, payload.second_character_id)
    is_dual = is_dual_generation(payload)
    has_custom_mask = has_complete_character_mask(payload.character_mask_json)
    layout_hint = build_character_layout_hint(payload.character_mask_json) if is_dual and has_custom_mask else ""
    if payload.prompt_positive.strip():
        positive = merge_unique_tags(
            knowledge_positive_tags(payload.prompt_cn, settings.prompt_knowledge_path),
            payload.prompt_positive.strip(),
        )
        positive = apply_lookback_positive_locks(positive, payload.prompt_cn)
        positive = compose_stacked_prompt(positive)
        negative = payload.prompt_negative.strip() or PromptResult.model_fields["negative"].default
        negative = apply_lookback_negative_locks(positive, negative, payload.prompt_cn)
        prompt = PromptResult(
            positive=positive,
            negative=compose_stacked_negative(negative, positive),
            style_notes=payload.style_notes.strip() or "provided by cloud prompt editor",
        )
    else:
        try:
            prompt = await translate_prompt(
                payload.prompt_cn,
                settings,
                negative_prompt=payload.prompt_negative,
                nsfw_mode=payload.nsfw_mode,
                nsfw_visibility_level=payload.nsfw_visibility_level,
            )
        except PromptTranslationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    if str(payload.job_type or "").strip().upper() == "INPAINT" and payload.inpaint_instruction.strip():
        try:
            repair_prompt = await translate_prompt(
                payload.inpaint_instruction.strip(),
                settings,
                negative_prompt=payload.prompt_negative,
                nsfw_mode=payload.nsfw_mode,
                nsfw_visibility_level=payload.nsfw_visibility_level,
            )
            prompt = prompt.model_copy(
                update={
                    "positive": merge_tags(prompt.positive, repair_prompt.positive),
                    "style_notes": merge_tags(prompt.style_notes, repair_prompt.style_notes),
                }
            )
        except PromptTranslationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    positive_prompt = build_positive_prompt(payload, prompt.positive, character, second_character, is_dual, has_custom_mask, layout_hint)
    regional_global_positive = build_regional_global_positive(
        payload,
        prompt.positive,
        character,
        second_character,
        is_dual,
        has_custom_mask,
        layout_hint,
    )
    regional_left_positive, regional_right_positive = build_regional_positive_prompts(
        payload,
        prompt.positive,
        character,
        second_character,
        is_dual,
        has_custom_mask,
    )
    if payload.nsfw_mode:
        positive_prompt = apply_nsfw_visibility_profile(positive_prompt, payload.nsfw_visibility_level)
        if regional_global_positive:
            regional_global_positive = apply_nsfw_visibility_profile(
                regional_global_positive, payload.nsfw_visibility_level
            )
        if regional_left_positive:
            regional_left_positive = apply_nsfw_visibility_profile(
                regional_left_positive, payload.nsfw_visibility_level
            )
        if regional_right_positive:
            regional_right_positive = apply_nsfw_visibility_profile(
                regional_right_positive, payload.nsfw_visibility_level
            )
    negative_prompt = build_negative_prompt(prompt.negative, is_dual)
    if payload.nsfw_mode:
        negative_prompt = apply_nsfw_visibility_negative_profile(
            negative_prompt, payload.nsfw_visibility_level
        )
    lora_name = payload.lora_name or (character.lora_name if character else "")
    lora_strength = payload.lora_strength or (character.lora_strength if character and character.lora_name else 0)
    second_lora_name = payload.second_lora_name or (second_character.lora_name if second_character else "")
    second_lora_strength = payload.second_lora_strength or (second_character.lora_strength if second_character and second_character.lora_name else 0)
    if is_dual:
        lora_strength = min(lora_strength, settings.dual_lora_strength_cap)
        second_lora_strength = min(second_lora_strength, settings.dual_lora_strength_cap)
    if payload.nsfw_mode:
        default_strength, max_strength = nsfw_lora_range(payload.nsfw_visibility_level)
        if lora_name:
            lora_strength = min(lora_strength or default_strength, max_strength)
        if second_lora_name:
            second_lora_strength = min(
                second_lora_strength or default_strength,
                max_strength,
            )
    if is_anima_checkpoint(payload.checkpoint):
        lora_name = ""
        lora_strength = 0
        second_lora_name = ""
        second_lora_strength = 0
    job_id = uuid.uuid4().hex
    source_image_path = ""
    if job_type == "IMG2IMG":
        source_image_path = save_source_image(payload.source_image_base64, job_id, settings)
    storage_date = normalized_storage_date(payload.storage_date)
    seed = payload.seed or random_seed()
    job = {
        "id": job_id,
        "cloud_job_id": payload.cloud_job_id,
        "user_id": payload.user_id,
        "storage_date": storage_date,
        "prompt_cn": payload.prompt_cn,
        "prompt_positive": positive_prompt,
        "prompt_negative": negative_prompt,
        "style_notes": prompt.style_notes,
        "seed": seed,
        "width": payload.width,
        "height": payload.height,
        "steps": payload.steps or settings.default_steps,
        "cfg": payload.cfg or settings.default_cfg,
        "checkpoint": payload.checkpoint or settings.default_checkpoint,
        "generation_mode": "DUAL" if is_dual else "SINGLE",
        "character_id": payload.character_id or "",
        "second_character_id": payload.second_character_id or "",
        "character_mask_json": payload.character_mask_json.strip() if is_dual and has_custom_mask else "",
        "regional_global_positive": regional_global_positive,
        "regional_left_positive": regional_left_positive,
        "regional_right_positive": regional_right_positive,
        "nsfw_visibility_level": normalize_visibility_level(payload.nsfw_visibility_level),
        "job_type": job_type,
        "parent_job_id": payload.parent_job_id,
        "inpaint_instruction": payload.inpaint_instruction.strip(),
        "inpaint_mask_json": payload.inpaint_mask_json.strip(),
        "source_image_path": source_image_path,
        "denoise": clamp_img2img_denoise(payload.denoise) if job_type == "IMG2IMG" else 1.0,
        "lora_name": lora_name,
        "lora_strength": lora_strength,
        "second_lora_name": second_lora_name if is_dual else "",
        "second_lora_strength": second_lora_strength if is_dual else 0,
        "light_hires": 0 if job_type == "IMG2IMG" else (1 if payload.light_hires and not is_anima_checkpoint(payload.checkpoint) else 0),
        "status": "queued",
        "image_path": "",
    }
    store.create_job(job)
    background_tasks.add_task(run_generation, job_id, settings)
    return {"job_id": job_id, "status": "queued"}


async def run_generation(job_id: str, settings: Settings) -> None:
    store = JobStore(settings.database_path)
    job = store.get_job(job_id)
    if not job:
        return
    store.update_job(job_id, status="running")
    client = ComfyUIClient(settings)
    try:
        if str(job.get("job_type") or "").upper() == "INPAINT":
            image_path = await run_manual_inpaint_generation(job, settings, store, client)
        elif str(job.get("job_type") or "").upper() == "IMG2IMG":
            image_path = await run_img2img_generation(job, settings, store, client)
        elif is_anima_checkpoint(job.get("checkpoint")):
            workflow = build_anima_workflow(
                positive=job["prompt_positive"],
                negative=job["prompt_negative"],
                seed=job["seed"],
                width=job["width"],
                height=job["height"],
                steps=job["steps"],
                cfg=job["cfg"],
                unet_name=str(job["checkpoint"]),
                clip_name=settings.anima_clip_name,
                vae_name=settings.anima_vae_name,
                sampler=settings.anima_sampler,
                scheduler=settings.anima_scheduler,
                filename_prefix=f"local_ai_drawing/{job_id}",
            )
            image_path = await queue_and_download(
                client, store, job_id, workflow, settings.output_dir, local_image_stem(job))
        elif should_use_dual_inpaint(settings, job):
            image_path = await run_dual_inpaint_generation(job, settings, store, client)
        elif should_use_dual_mask_conditioning(settings, job):
            image_path = await run_dual_mask_conditioning_generation(job, settings, store, client)
        else:
            use_regions = should_use_dual_regions(settings, job)
            sampling = resolve_classic_sampling(
                light_hires=bool(job.get("light_hires")),
                cfg=job["cfg"],
                default_sampler=settings.default_sampler,
                default_scheduler=settings.default_scheduler,
                width=job["width"],
                height=job["height"],
            )
            workflow = build_workflow(
                positive=(job.get("regional_global_positive") or job["prompt_positive"]) if use_regions else job["prompt_positive"],
                negative=job["prompt_negative"],
                seed=job["seed"],
                width=job["width"],
                height=job["height"],
                steps=job["steps"],
                cfg=sampling["cfg"],
                checkpoint=job["checkpoint"],
                sampler=sampling["sampler"],
                scheduler=sampling["scheduler"],
                lora_name=job["lora_name"],
                lora_strength=job["lora_strength"],
                second_lora_name=job["second_lora_name"],
                second_lora_strength=job["second_lora_strength"],
                regional_left_positive=job["regional_left_positive"] if use_regions else "",
                regional_right_positive=job["regional_right_positive"] if use_regions else "",
                clip_skip=sampling["clip_skip"],
                hires_scale=sampling["hires_scale"],
                hires_steps=sampling["hires_steps"],
                hires_denoise=sampling["hires_denoise"],
                filename_prefix=f"local_ai_drawing/{job_id}",
            )
            image_path = await queue_and_download(
                client, store, job_id, workflow, settings.output_dir, local_image_stem(job))
        relative_path = image_path.resolve().relative_to(settings.output_dir.resolve()).as_posix()
        store.update_job(job_id, status="completed", image_path=relative_path)
    except Exception as exc:
        store.update_job(job_id, status="failed", error=str(exc))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, store: JobStore = Depends(get_store)) -> dict:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/api/history")
def history(limit: int = 50, store: JobStore = Depends(get_store)) -> list[dict]:
    return store.list_jobs(limit)


@app.get("/api/images/{image_path:path}")
def image(image_path: str, settings: Settings = Depends(get_settings)) -> FileResponse:
    path = resolve_output_path(settings.output_dir, image_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(path)


app.mount("/", StaticFiles(directory="static", html=True), name="static")


def is_dual_generation(payload: GenerateRequest) -> bool:
    mode = (payload.generation_mode or "").strip().upper()
    return (
        mode == "DUAL"
        or bool(payload.second_character_id)
        or bool(payload.second_lora_name)
    )


def normalized_storage_date(value: str | None) -> str:
    if value:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return datetime.now().strftime("%Y-%m-%d")


def normalize_visibility_level(value: str | None) -> str:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in {"LIGHT", "STANDARD", "STRONG"} else "STANDARD"


def nsfw_lora_range(level: str | None) -> tuple[float, float]:
    normalized = normalize_visibility_level(level)
    if normalized == "LIGHT":
        return 0.65, 0.65
    if normalized == "STRONG":
        return 0.55, 0.60
    return 0.60, 0.65


def save_inpaint_source(encoded: str, job_id: str, settings: Settings) -> str:
    return save_source_image(encoded, job_id, settings)


def save_source_image(encoded: str, job_id: str, settings: Settings) -> str:
    if not encoded.strip():
        raise HTTPException(status_code=400, detail="Source image is missing.")
    value = encoded.strip()
    if value.startswith("data:") and "," in value:
        value = value.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid source image.") from exc
    if len(image_bytes) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Source image is too large.")

    source_dir = settings.database_path.parent / "source_images"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / f"{job_id}.png"
    try:
        from io import BytesIO

        with Image.open(BytesIO(image_bytes)) as image:
            image.convert("RGB").save(source_path, format="PNG")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid source image.") from exc
    return str(source_path)


def local_image_stem(job: dict) -> str:
    user_id = job.get("user_id")
    date = normalized_storage_date(str(job.get("storage_date") or job.get("created_at") or ""))
    return f"{user_id if user_id else 'local'}/{date}/{job['id']}"


def resolve_output_path(output_dir: Path, relative_path: str) -> Path:
    normalized = str(relative_path or "").replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
        raise HTTPException(status_code=400, detail="Invalid image path.")
    candidate = (output_dir / normalized).resolve()
    root = output_dir.resolve()
    if not normalized or not candidate.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Invalid image path.")
    return candidate


def has_complete_character_mask(mask_json: str) -> bool:
    roles = character_mask_roles(mask_json)
    return "primary" in roles and "secondary" in roles


def character_mask_roles(mask_json: str) -> set[str]:
    if not mask_json.strip():
        return set()
    try:
        payload = json.loads(mask_json)
    except json.JSONDecodeError:
        return set()
    if not isinstance(payload, dict):
        return set()
    roles: set[str] = set()
    strokes = payload.get("strokes")
    if not isinstance(strokes, list):
        return set()
    for stroke in strokes:
        if not isinstance(stroke, dict):
            continue
        role = normalize_mask_role(str(stroke.get("role") or ""))
        points = stroke.get("points")
        if role and isinstance(points, list) and points:
            roles.add(role)
    return roles


def build_character_layout_hint(mask_json: str) -> str:
    role_points = character_mask_points(mask_json)
    primary = role_points.get("primary", [])
    secondary = role_points.get("secondary", [])
    if not primary or not secondary:
        return ""

    primary_box = normalized_bounds(primary)
    secondary_box = normalized_bounds(secondary)
    relation = describe_character_relation(primary_box, secondary_box)
    return merge_tags(
        f"first character roughly toward {describe_box_position(primary_box)}",
        f"second character roughly toward {describe_box_position(secondary_box)}",
        relation.replace("character A", "first character").replace("character B", "second character"),
    )


def character_mask_points(mask_json: str) -> dict[str, list[tuple[float, float]]]:
    if not mask_json.strip():
        return {}
    try:
        payload = json.loads(mask_json)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}

    result: dict[str, list[tuple[float, float]]] = {"primary": [], "secondary": []}
    strokes = payload.get("strokes")
    if not isinstance(strokes, list):
        return result
    for stroke in strokes:
        if not isinstance(stroke, dict):
            continue
        role = normalize_mask_role(str(stroke.get("role") or ""))
        points = stroke.get("points")
        if role not in result or not isinstance(points, list):
            continue
        for point in points:
            if not isinstance(point, dict):
                continue
            try:
                x = float(point.get("x"))
                y = float(point.get("y"))
            except (TypeError, ValueError):
                continue
            if x > 1:
                x = x / max(float(payload.get("width") or 1), 1)
            if y > 1:
                y = y / max(float(payload.get("height") or 1), 1)
            result[role].append((max(0.0, min(1.0, x)), max(0.0, min(1.0, y))))
    return result


def normalized_bounds(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def describe_box_position(bounds: tuple[float, float, float, float]) -> str:
    x0, y0, x1, y1 = bounds
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    horizontal = "left" if cx < 0.38 else "right" if cx > 0.62 else "center"
    vertical = "upper" if cy < 0.38 else "lower" if cy > 0.62 else "middle"
    if horizontal == "center" and vertical == "middle":
        return "near the center"
    return f"{vertical} {horizontal}".strip()


def describe_character_relation(
    primary: tuple[float, float, float, float],
    secondary: tuple[float, float, float, float],
) -> str:
    ax0, ay0, ax1, ay1 = primary
    bx0, by0, bx1, by1 = secondary
    acx, acy = (ax0 + ax1) / 2, (ay0 + ay1) / 2
    bcx, bcy = (bx0 + bx1) / 2, (by0 + by1) / 2
    dx = bcx - acx
    dy = bcy - acy
    distance = (dx * dx + dy * dy) ** 0.5
    overlap = normalized_iou(primary, secondary)

    if overlap > 0.08 or distance < 0.24:
        return "close interaction, overlapping composition"
    if abs(dx) >= abs(dy):
        if dx > 0:
            return "character A is left of character B"
        return "character A is right of character B"
    if dy > 0:
        return "character A is above character B"
    return "character A is below character B"


def normalized_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    ax0, ay0, ax1, ay1 = first
    bx0, by0, bx1, by1 = second
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def should_use_dual_inpaint(settings: Settings, job: dict) -> bool:
    return (
        str(job.get("generation_mode") or "").upper() == "DUAL"
        and settings.dual_character_strategy.strip().lower() == "inpaint"
        and bool(job.get("regional_left_positive"))
        and bool(job.get("regional_right_positive"))
    )


def should_use_dual_regions(settings: Settings, job: dict) -> bool:
    strategy = settings.dual_character_strategy.strip().lower()
    return (
        str(job.get("generation_mode") or "").upper() == "DUAL"
        and strategy == "regional-area"
        and bool(job.get("regional_left_positive"))
        and bool(job.get("regional_right_positive"))
    )


def should_use_dual_mask_conditioning(settings: Settings, job: dict) -> bool:
    return (
        str(job.get("generation_mode") or "").upper() == "DUAL"
        and settings.dual_character_strategy.strip().lower()
        in {"mask", "masked", "mask-conditioning", "conditioning", "regional-mask", "regional-area"}
        and bool(job.get("regional_left_positive"))
        and bool(job.get("regional_right_positive"))
        and has_complete_character_mask(str(job.get("character_mask_json") or ""))
    )


async def run_manual_inpaint_generation(
    job: dict,
    settings: Settings,
    store: JobStore,
    client: ComfyUIClient,
) -> Path:
    job_id = job["id"]
    source_path = Path(str(job.get("source_image_path") or ""))
    if not source_path.is_file():
        raise RuntimeError("Inpaint source image is missing.")

    with Image.open(source_path) as source:
        width, height = source.size
    mask_dir = settings.database_path.parent / "masks"
    mask_dir.mkdir(parents=True, exist_ok=True)
    mask_path = mask_dir / f"{job_id}_repair_mask.png"
    crop_source_path = mask_dir / f"{job_id}_repair_source_crop.png"
    crop_mask_path = mask_dir / f"{job_id}_repair_mask_crop.png"

    uploaded_inputs: list[str] = []
    temp_paths = [source_path, mask_path, crop_source_path, crop_mask_path]
    try:
        create_manual_inpaint_mask(mask_path, width, height, job.get("inpaint_mask_json") or "")
        crop_box = create_manual_inpaint_crop(
            source_path,
            mask_path,
            crop_source_path,
            crop_mask_path,
        )
        source_upload = await client.upload_image(crop_source_path, f"{job_id}_source_crop.png")
        mask_upload = await client.upload_image(crop_mask_path, f"{job_id}_repair_mask_crop.png")
        uploaded_inputs.extend([source_upload, mask_upload])
        denoise, grow_mask_by = inpaint_profile(job.get("nsfw_visibility_level"))
        brushnet_model = select_brushnet_model(settings)
        legacy_workflow = build_inpaint_workflow(
            positive=inpaint_positive_prompt(job["prompt_positive"]),
            negative=inpaint_negative_prompt(job["prompt_negative"]),
            seed=job["seed"],
            steps=job["steps"],
            cfg=job["cfg"],
            checkpoint=job["checkpoint"],
            sampler=settings.default_sampler,
            scheduler=settings.default_scheduler,
            base_image=source_upload,
            mask_image=mask_upload,
            denoise=denoise,
            lora_name=job["lora_name"],
            lora_strength=job["lora_strength"],
            second_lora_name=job["second_lora_name"],
            second_lora_strength=job["second_lora_strength"],
            grow_mask_by=grow_mask_by,
            filename_prefix=f"local_ai_drawing/{job_id}",
        )
        used_brushnet = False
        if should_use_brushnet_inpaint(settings, brushnet_model):
            workflow = build_brushnet_inpaint_workflow(
                positive=inpaint_positive_prompt(job["prompt_positive"]),
                negative=inpaint_negative_prompt(job["prompt_negative"]),
                seed=job["seed"],
                steps=job["steps"],
                cfg=job["cfg"],
                checkpoint=job["checkpoint"],
                sampler=settings.default_sampler,
                scheduler=settings.default_scheduler,
                base_image=source_upload,
                mask_image=mask_upload,
                denoise=denoise,
                brushnet_model=brushnet_model,
                brushnet_dtype=settings.brushnet_dtype,
                brushnet_scale=settings.brushnet_scale,
                lora_name=job["lora_name"],
                lora_strength=job["lora_strength"],
                second_lora_name=job["second_lora_name"],
                second_lora_strength=job["second_lora_strength"],
                filename_prefix=f"local_ai_drawing/{job_id}",
            )
            used_brushnet = True
        else:
            workflow = legacy_workflow
        try:
            repaired_crop_path = await queue_and_download(
                client, store, job_id, workflow, settings.output_dir, local_image_stem(job)
            )
        except ComfyUIExecutionError as exc:
            if not used_brushnet:
                raise
            print(f"[inpaint] BrushNet failed for job {job_id}; retrying legacy inpaint: {exc}")
            repaired_crop_path = await queue_and_download(
                client, store, job_id, legacy_workflow, settings.output_dir, local_image_stem(job)
            )
        composite_inpaint_crop(
            source_path=source_path,
            mask_path=mask_path,
            repaired_crop_path=repaired_crop_path,
            crop_box=crop_box,
            output_path=repaired_crop_path,
        )
        return repaired_crop_path
    finally:
        for filename in uploaded_inputs:
            client.cleanup_comfyui_input_file(filename)
        cleanup_temp_paths(temp_paths)


def inpaint_profile(level: str | None) -> tuple[float, int]:
    normalized = normalize_visibility_level(level)
    if normalized == "LIGHT":
        return 0.42, 12
    if normalized == "STRONG":
        return 0.62, 22
    return 0.52, 16


def should_use_brushnet_inpaint(settings: Settings, brushnet_model: str) -> bool:
    engine = str(settings.inpaint_engine or "auto").strip().lower()
    if engine in {"legacy", "default", "vae", "comfyui"}:
        return False
    if engine in {"brushnet", "auto"}:
        return bool(brushnet_model)
    return False


def select_brushnet_model(settings: Settings) -> str:
    configured = str(settings.brushnet_model or "").strip()
    if configured:
        return configured.replace("\\", os.sep).replace("/", os.sep)
    inpaint_dir = settings.comfyui_models_dir / "inpaint"
    if not inpaint_dir.is_dir():
        return ""
    candidates = sorted(
        str(path.relative_to(inpaint_dir))
        for path in inpaint_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".safetensors", ".ckpt", ".pt", ".pth"}
    )
    return candidates[0] if candidates else ""


def inpaint_positive_prompt(prompt: str) -> str:
    return merge_prompt_tags(
        prompt,
        "match original image style, seamless edit, consistent lineart, consistent coloring, "
        "consistent lighting, preserve surrounding details",
    )


def inpaint_negative_prompt(prompt: str) -> str:
    return merge_prompt_tags(
        prompt,
        "visible brush stroke, painted line, red mark, sketch line, line artifact, repair seam, "
        "mismatched style, mismatched coloring, blurry patch",
    )


def create_manual_inpaint_mask(
    path: Path,
    width: int,
    height: int,
    mask_json: str,
) -> None:
    try:
        payload = json.loads(mask_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Inpaint mask is invalid.") from exc
    strokes = payload.get("strokes") if isinstance(payload, dict) else None
    if not isinstance(strokes, list) or not strokes:
        raise RuntimeError("Inpaint mask contains no painted area.")

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    painted = False
    max_brush = 0
    for stroke in strokes:
        if not isinstance(stroke, dict):
            continue
        points = normalized_points(stroke.get("points") or [], width, height)
        if not points:
            continue
        brush = mask_brush_width(
            stroke.get("brush", stroke.get("brushSize", 0.05)),
            width,
            height,
        )
        draw_painted_character_region(draw, points, brush)
        max_brush = max(max_brush, brush)
        painted = True
    if not painted:
        raise RuntimeError("Inpaint mask contains no painted area.")

    region_mask = finalize_manual_inpaint_mask(mask, width, height, max_brush)
    region_mask.save(path)


def create_manual_inpaint_crop(
    source_path: Path,
    mask_path: Path,
    crop_source_path: Path,
    crop_mask_path: Path,
) -> tuple[int, int, int, int]:
    with Image.open(source_path) as source, Image.open(mask_path) as mask:
        source_rgb = source.convert("RGB")
        mask_l = mask.convert("L")
        width, height = source_rgb.size
        crop_box = inpaint_crop_box(mask_l, width, height)
        source_rgb.crop(crop_box).save(crop_source_path, format="PNG")
        mask_l.crop(crop_box).convert("RGB").save(crop_mask_path, format="PNG")
        return crop_box


def inpaint_crop_box(mask: Image.Image, width: int, height: int) -> tuple[int, int, int, int]:
    bbox = mask.point(lambda value: 255 if value > 8 else 0).getbbox()
    if bbox is None:
        raise RuntimeError("Inpaint mask contains no painted area.")

    left, top, right, bottom = bbox
    painted_width = max(1, right - left)
    painted_height = max(1, bottom - top)
    min_side = min(width, height)
    padding = max(48, int(max(painted_width, painted_height) * 0.85), int(min_side * 0.08))
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(width, right + padding)
    bottom = min(height, bottom + padding)

    min_crop = min(min_side, 320)
    if right - left < min_crop:
        extra = min_crop - (right - left)
        left = max(0, left - extra // 2)
        right = min(width, right + extra - extra // 2)
    if bottom - top < min_crop:
        extra = min_crop - (bottom - top)
        top = max(0, top - extra // 2)
        bottom = min(height, bottom + extra - extra // 2)

    left = align_down(left, 8)
    top = align_down(top, 8)
    right = align_up(right, 8, width)
    bottom = align_up(bottom, 8, height)
    if right <= left or bottom <= top:
        return 0, 0, width, height
    return left, top, right, bottom


def composite_inpaint_crop(
    *,
    source_path: Path,
    mask_path: Path,
    repaired_crop_path: Path,
    crop_box: tuple[int, int, int, int],
    output_path: Path,
) -> None:
    with Image.open(source_path) as source, Image.open(mask_path) as mask, Image.open(repaired_crop_path) as repaired:
        base = source.convert("RGB")
        mask_l = mask.convert("L")
        left, top, right, bottom = crop_box
        crop_size = (right - left, bottom - top)
        repaired_rgb = repaired.convert("RGB")
        if repaired_rgb.size != crop_size:
            repaired_rgb = repaired_rgb.resize(crop_size, Image.Resampling.LANCZOS)
        alpha = mask_l.crop(crop_box)
        alpha = feather_inpaint_mask(alpha, base.size)
        base.paste(repaired_rgb, (left, top), alpha)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        base.save(output_path, format="PNG")


def feather_inpaint_mask(mask: Image.Image, full_size: tuple[int, int]) -> Image.Image:
    min_side = min(full_size)
    expansion = max(5, int(min_side * 0.008))
    if expansion % 2 == 0:
        expansion += 1
    expanded = mask.filter(ImageFilter.MaxFilter(expansion))
    return expanded.filter(ImageFilter.GaussianBlur(radius=max(3, expansion // 2))).convert("L")


def align_down(value: int, multiple: int) -> int:
    return max(0, value - (value % multiple))


def align_up(value: int, multiple: int, limit: int) -> int:
    if value >= limit:
        return limit
    aligned = value + (-value % multiple)
    return min(limit, max(multiple, aligned))


async def run_dual_mask_conditioning_generation(
    job: dict,
    settings: Settings,
    store: JobStore,
    client: ComfyUIClient,
) -> Path:
    job_id = job["id"]
    mask_dir = settings.database_path.parent / "masks"
    mask_dir.mkdir(parents=True, exist_ok=True)
    left_mask = mask_dir / f"{job_id}_left_mask.png"
    right_mask = mask_dir / f"{job_id}_right_mask.png"
    create_character_conditioning_masks(
        left_mask,
        right_mask,
        job["width"],
        job["height"],
        job.get("character_mask_json") or "",
        settings.dual_inpaint_mask_overlap_ratio,
    )

    uploaded_inputs: list[str] = []
    temp_paths = [left_mask, right_mask]
    try:
        left_mask_upload = await client.upload_image(left_mask, f"{job_id}_left_mask.png")
        right_mask_upload = await client.upload_image(right_mask, f"{job_id}_right_mask.png")
        uploaded_inputs.extend([left_mask_upload, right_mask_upload])
        workflow = build_mask_conditioning_workflow(
            positive=job.get("regional_global_positive") or job["prompt_positive"],
            negative=job["prompt_negative"],
            regional_left_positive=job["regional_left_positive"],
            regional_right_positive=job["regional_right_positive"],
            left_mask_image=left_mask_upload,
            right_mask_image=right_mask_upload,
            seed=job["seed"],
            width=job["width"],
            height=job["height"],
            steps=job["steps"],
            cfg=job["cfg"],
            checkpoint=job["checkpoint"],
            sampler=settings.default_sampler,
            scheduler=settings.default_scheduler,
            lora_name=job["lora_name"],
            lora_strength=job["lora_strength"],
            second_lora_name=job["second_lora_name"],
            second_lora_strength=job["second_lora_strength"],
            mask_strength=settings.dual_mask_conditioning_strength,
            filename_prefix=f"local_ai_drawing/{job_id}",
        )
        return await queue_and_download(
            client, store, job_id, workflow, settings.output_dir, local_image_stem(job))
    finally:
        for filename in uploaded_inputs:
            client.cleanup_comfyui_input_file(filename)
        cleanup_temp_paths(temp_paths)


async def run_dual_inpaint_generation(
    job: dict,
    settings: Settings,
    store: JobStore,
    client: ComfyUIClient,
) -> Path:
    job_id = job["id"]
    base_prompt = job.get("regional_global_positive") or job["prompt_positive"]
    base_workflow = build_workflow(
        positive=base_prompt,
        negative=job["prompt_negative"],
        seed=job["seed"],
        width=job["width"],
        height=job["height"],
        steps=job["steps"],
        cfg=job["cfg"],
        checkpoint=job["checkpoint"],
        sampler=settings.default_sampler,
        scheduler=settings.default_scheduler,
        filename_prefix=f"local_ai_drawing/{job_id}_base",
    )
    image_stem = local_image_stem(job)
    base_path = await queue_and_download(
        client, store, job_id, base_workflow, settings.output_dir, f"{image_stem}_base")

    mask_dir = settings.database_path.parent / "masks"
    mask_dir.mkdir(parents=True, exist_ok=True)
    left_mask = mask_dir / f"{job_id}_left_mask.png"
    right_mask = mask_dir / f"{job_id}_right_mask.png"
    create_character_masks(
        left_mask,
        right_mask,
        job["width"],
        job["height"],
        job.get("character_mask_json") or "",
        settings.dual_inpaint_mask_overlap_ratio,
    )

    uploaded_inputs: list[str] = []
    temp_paths = [base_path, left_mask, right_mask]
    try:
        base_upload = await client.upload_image(base_path, f"{job_id}_base.png")
        left_mask_upload = await client.upload_image(left_mask, f"{job_id}_left_mask.png")
        uploaded_inputs.extend([base_upload, left_mask_upload])
        left_workflow = build_inpaint_workflow(
            positive=job["regional_left_positive"],
            negative=job["prompt_negative"],
            seed=job["seed"] + 101,
            steps=job["steps"],
            cfg=job["cfg"],
            checkpoint=job["checkpoint"],
            sampler=settings.default_sampler,
            scheduler=settings.default_scheduler,
            base_image=base_upload,
            mask_image=left_mask_upload,
            denoise=settings.dual_inpaint_denoise,
            lora_name=job["lora_name"],
            lora_strength=job["lora_strength"],
            filename_prefix=f"local_ai_drawing/{job_id}_left",
        )
        left_path = await queue_and_download(
            client, store, job_id, left_workflow, settings.output_dir, f"{image_stem}_left")
        temp_paths.append(left_path)

        left_upload = await client.upload_image(left_path, f"{job_id}_left.png")
        right_mask_upload = await client.upload_image(right_mask, f"{job_id}_right_mask.png")
        uploaded_inputs.extend([left_upload, right_mask_upload])
        right_workflow = build_inpaint_workflow(
            positive=job["regional_right_positive"],
            negative=job["prompt_negative"],
            seed=job["seed"] + 202,
            steps=job["steps"],
            cfg=job["cfg"],
            checkpoint=job["checkpoint"],
            sampler=settings.default_sampler,
            scheduler=settings.default_scheduler,
            base_image=left_upload,
            mask_image=right_mask_upload,
            denoise=settings.dual_inpaint_denoise,
            lora_name=job["second_lora_name"],
            lora_strength=job["second_lora_strength"],
            filename_prefix=f"local_ai_drawing/{job_id}",
        )
        return await queue_and_download(
            client, store, job_id, right_workflow, settings.output_dir, image_stem)
    finally:
        for filename in uploaded_inputs:
            client.cleanup_comfyui_input_file(filename)
        cleanup_temp_paths(temp_paths)


async def run_img2img_generation(
    job: dict,
    settings: Settings,
    store: JobStore,
    client: ComfyUIClient,
) -> Path:
    source_path = Path(str(job.get("source_image_path") or ""))
    if not source_path.exists():
        raise RuntimeError("Img2img source image is missing.")
    source_upload = await client.upload_image(source_path, f"{job['id']}_img2img_source.png")
    denoise = clamp_img2img_denoise(job.get("denoise"))
    try:
        if is_anima_checkpoint(job.get("checkpoint")):
            workflow = build_anima_img2img_workflow(
                positive=job["prompt_positive"],
                negative=job["prompt_negative"],
                seed=job["seed"],
                width=job["width"],
                height=job["height"],
                steps=job["steps"],
                cfg=job["cfg"],
                unet_name=str(job["checkpoint"]),
                clip_name=settings.anima_clip_name,
                vae_name=settings.anima_vae_name,
                source_image=source_upload,
                denoise=denoise,
                sampler=settings.anima_sampler,
                scheduler=settings.anima_scheduler,
                filename_prefix=f"local_ai_drawing/{job['id']}",
            )
        else:
            workflow = build_img2img_workflow(
                positive=job["prompt_positive"],
                negative=job["prompt_negative"],
                seed=job["seed"],
                width=job["width"],
                height=job["height"],
                steps=job["steps"],
                cfg=job["cfg"],
                checkpoint=job["checkpoint"],
                sampler=settings.default_sampler,
                scheduler=settings.default_scheduler,
                source_image=source_upload,
                denoise=denoise,
                lora_name=job["lora_name"],
                lora_strength=job["lora_strength"],
                second_lora_name="",
                second_lora_strength=0,
                filename_prefix=f"local_ai_drawing/{job['id']}",
            )
        return await queue_and_download(
            client, store, job["id"], workflow, settings.output_dir, local_image_stem(job)
        )
    finally:
        client.cleanup_comfyui_input_file(source_upload)


async def queue_and_download(
    client: ComfyUIClient,
    store: JobStore,
    job_id: str,
    workflow: dict,
    output_dir: Path,
    image_name: str,
) -> Path:
    started = time.perf_counter()
    prompt_id = await client.queue_prompt(workflow, client_id=job_id)
    store.update_job(job_id, comfy_prompt_id=prompt_id)
    queued = time.perf_counter()
    history = await client.wait_for_history(prompt_id)
    ready = time.perf_counter()
    image_path = await client.download_first_image(history, output_dir, image_name)
    finished = time.perf_counter()
    timestamps = {
        event: details["timestamp"]
        for event, details in history.get("status", {}).get("messages", [])
        if isinstance(details, dict) and isinstance(details.get("timestamp"), (int, float))
    }
    execution_ms = (
        timestamps["execution_success"] - timestamps["execution_start"]
        if "execution_success" in timestamps and "execution_start" in timestamps else None
    )
    print("[generation-timing] " + json.dumps({
        "job_id": job_id, "prompt_id": prompt_id,
        "submit_seconds": round(queued - started, 3),
        "queue_and_execute_seconds": round(ready - queued, 3),
        "comfy_execution_seconds": round(execution_ms / 1000, 3) if execution_ms is not None else None,
        "download_seconds": round(finished - ready, 3),
        "total_seconds": round(finished - started, 3),
    }), flush=True)
    return image_path


def create_split_mask(path: Path, width: int, height: int, side: str, overlap_ratio: float) -> None:
    overlap = max(32, min(width // 4, int(width * overlap_ratio)))
    midpoint = width // 2
    if side == "left":
        x0, x1 = 0, min(width, midpoint + overlap)
    else:
        x0, x1 = max(0, midpoint - overlap), width
    image = Image.new("RGB", (width, height), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((x0, 0, x1, height), fill="white")
    image.save(path)


def create_split_conditioning_mask(path: Path, width: int, height: int, side: str) -> None:
    midpoint = width // 2
    if side == "left":
        x0, x1 = 0, midpoint
    else:
        x0, x1 = midpoint, width
    image = Image.new("RGB", (width, height), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((x0, 0, x1, height), fill="white")
    image.save(path)


def create_character_conditioning_masks(
    left_path: Path,
    right_path: Path,
    width: int,
    height: int,
    mask_json: str,
    overlap_ratio: float,
) -> None:
    if not mask_json.strip():
        create_split_conditioning_mask(left_path, width, height, "left")
        create_split_conditioning_mask(right_path, width, height, "right")
        return

    left = Image.new("L", (width, height), 0)
    right = Image.new("L", (width, height), 0)
    left_draw = ImageDraw.Draw(left)
    right_draw = ImageDraw.Draw(right)
    drawn = {"primary": False, "secondary": False}
    try:
        payload = json.loads(mask_json)
        strokes = payload.get("strokes", []) if isinstance(payload, dict) else []
        for stroke in strokes:
            if not isinstance(stroke, dict):
                continue
            role = normalize_mask_role(str(stroke.get("role") or ""))
            points = stroke.get("points") or []
            if role not in drawn or not isinstance(points, list) or not points:
                continue
            brush = mask_brush_width(stroke.get("brush"), width, height)
            pixel_points = normalized_points(points, width, height)
            if not pixel_points:
                continue
            draw = left_draw if role == "primary" else right_draw
            draw_painted_character_region(draw, pixel_points, brush)
            drawn[role] = True
    except Exception as exc:
        print(f"[dual-mask-conditioning] custom mask ignored: {exc}")

    if not drawn["primary"]:
        create_split_conditioning_mask(left_path, width, height, "left")
    else:
        finalize_conditioning_mask(left, width, height).save(left_path)
    if not drawn["secondary"]:
        create_split_conditioning_mask(right_path, width, height, "right")
    else:
        finalize_conditioning_mask(right, width, height).save(right_path)


def draw_painted_character_region(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    brush: int,
) -> None:
    radius = max(brush // 2, 1)
    if len(points) == 1:
        x, y = points[0]
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
        return

    draw.line(points, fill=255, width=brush, joint="curve")
    for x, y in points:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)


def finalize_manual_inpaint_mask(mask: Image.Image, width: int, height: int, max_brush: int) -> Image.Image:
    min_side = min(width, height)
    expansion = max(9, int(min_side * 0.02), int(max_brush * 0.55))
    if expansion % 2 == 0:
        expansion += 1
    expanded = mask.filter(ImageFilter.MaxFilter(expansion))
    softened = expanded.filter(ImageFilter.GaussianBlur(radius=max(3, expansion // 3)))
    return softened.convert("RGB")


def merge_prompt_tags(*parts: str) -> str:
    tags: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for raw_tag in (part or "").split(","):
            tag = raw_tag.strip()
            key = " ".join(tag.lower().replace("_", " ").split())
            if not tag or key in seen:
                continue
            seen.add(key)
            tags.append(tag)
    return ", ".join(tags)


def finalize_conditioning_mask(mask: Image.Image, width: int, height: int) -> Image.Image:
    expansion = max(3, int(min(width, height) * 0.008))
    if expansion % 2 == 0:
        expansion += 1
    expanded = mask.filter(ImageFilter.MaxFilter(expansion))
    softened = expanded.filter(ImageFilter.GaussianBlur(radius=max(1, expansion // 2)))
    return softened.convert("RGB")


def create_character_masks(
    left_path: Path,
    right_path: Path,
    width: int,
    height: int,
    mask_json: str,
    overlap_ratio: float,
) -> None:
    if not mask_json.strip():
        create_split_mask(left_path, width, height, "left", overlap_ratio)
        create_split_mask(right_path, width, height, "right", overlap_ratio)
        return

    left = Image.new("L", (width, height), 0)
    right = Image.new("L", (width, height), 0)
    left_draw = ImageDraw.Draw(left)
    right_draw = ImageDraw.Draw(right)
    drawn = {"primary": False, "secondary": False}
    try:
        payload = json.loads(mask_json)
        strokes = payload.get("strokes", []) if isinstance(payload, dict) else []
        for stroke in strokes:
            if not isinstance(stroke, dict):
                continue
            role = normalize_mask_role(str(stroke.get("role") or ""))
            points = stroke.get("points") or []
            if role not in drawn or not isinstance(points, list) or not points:
                continue
            brush = mask_brush_width(stroke.get("brush"), width, height)
            pixel_points = normalized_points(points, width, height)
            if not pixel_points:
                continue
            draw = left_draw if role == "primary" else right_draw
            draw_expanded_character_region(draw, pixel_points, brush, width, height)
            drawn[role] = True
    except Exception as exc:
        print(f"[dual-inpaint] custom mask ignored: {exc}")

    if not drawn["primary"]:
        create_split_mask(left_path, width, height, "left", overlap_ratio)
    else:
        finalize_character_mask(left, width, height).save(left_path)
    if not drawn["secondary"]:
        create_split_mask(right_path, width, height, "right", overlap_ratio)
    else:
        finalize_character_mask(right, width, height).save(right_path)


def draw_expanded_character_region(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    brush: int,
    width: int,
    height: int,
) -> None:
    radius = max(brush // 2, 1)
    if len(points) == 1:
        x, y = points[0]
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    else:
        draw.line(points, fill=255, width=brush, joint="curve")
        for x, y in (points[0], points[-1]):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)

    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]
    region_padding = max(brush * 2, int(min(width, height) * 0.08))
    x0 = max(0, min(x_values) - region_padding)
    y0 = max(0, min(y_values) - region_padding)
    x1 = min(width - 1, max(x_values) + region_padding)
    y1 = min(height - 1, max(y_values) + region_padding)
    if x1 - x0 < brush * 2:
        center = (x0 + x1) // 2
        x0 = max(0, center - brush)
        x1 = min(width - 1, center + brush)
    if y1 - y0 < brush * 2:
        center = (y0 + y1) // 2
        y0 = max(0, center - brush)
        y1 = min(height - 1, center + brush)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=max(brush, 12), fill=255)


def finalize_character_mask(mask: Image.Image, width: int, height: int) -> Image.Image:
    expansion = max(9, int(min(width, height) * 0.035))
    if expansion % 2 == 0:
        expansion += 1
    expanded = mask.filter(ImageFilter.MaxFilter(expansion))
    return expanded.convert("RGB")


def normalize_mask_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized in {"primary", "left", "a", "character_a", "character-a"}:
        return "primary"
    if normalized in {"secondary", "right", "b", "character_b", "character-b"}:
        return "secondary"
    return ""


def mask_brush_width(value, width: int, height: int) -> int:
    try:
        brush = float(value)
    except (TypeError, ValueError):
        brush = 0.05
    if brush <= 1:
        pixels = brush * min(width, height)
    else:
        pixels = brush
    return max(16, min(int(round(pixels)), max(width, height)))


def normalized_points(points: list, width: int, height: int) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        try:
            x = float(point.get("x"))
            y = float(point.get("y"))
        except (TypeError, ValueError):
            continue
        if x > 1 or y > 1:
            px = int(round(x))
            py = int(round(y))
        else:
            px = int(round(x * width))
            py = int(round(y * height))
        px = max(0, min(width - 1, px))
        py = max(0, min(height - 1, py))
        result.append((px, py))
    return result


def cleanup_temp_paths(paths: list[Path]) -> None:
    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            print(f"[dual-inpaint] cleanup skipped for {path.name}: {exc}")


def character_tags(character, *, nsfw_mode: bool = False) -> str:
    if not character:
        return ""
    tags = filter_character_identity_tags(
        merge_tags(character.trigger_words, character.default_positive, character.style_tags)
    )
    return filter_nsfw_incompatible_tags(tags) if nsfw_mode else tags


def character_outfit_tags(character) -> str:
    if not character:
        return ""
    stored = str(getattr(character, "default_outfit", "") or "")
    if stored.strip():
        return stored
    raw = merge_tags(character.default_positive, character.style_tags)
    identity = filter_character_identity_tags(raw)
    return subtract_prompt_tags(raw, identity)


def dual_character_guard(custom_mask: bool = False) -> str:
    return "2girls, duo, distinct faces, one continuous scene, consistent lighting, consistent art style"


def normalize_tag_key(tag: str) -> str:
    return " ".join(tag.strip().lower().replace("_", " ").split())


def filter_dual_character_tags(prompt: str) -> str:
    if not prompt:
        return ""
    tags: list[str] = []
    for raw_tag in prompt.split(","):
        tag = raw_tag.strip()
        if not tag or normalize_tag_key(tag) in DUAL_CHARACTER_BLOCKED_TAGS:
            continue
        tags.append(tag)
    return ", ".join(tags)


def subtract_prompt_tags(prompt: str, *remove_prompts: str) -> str:
    remove_keys: set[str] = set()
    for remove_prompt in remove_prompts:
        for raw_tag in remove_prompt.split(","):
            tag = raw_tag.strip()
            if tag:
                remove_keys.add(normalize_tag_key(tag))

    tags: list[str] = []
    for raw_tag in prompt.split(","):
        tag = raw_tag.strip()
        if not tag:
            continue
        key = normalize_tag_key(tag)
        if key in remove_keys or key in DUAL_CHARACTER_BLOCKED_TAGS:
            continue
        tags.append(tag)
    return ", ".join(tags)


def build_positive_prompt(
    payload: GenerateRequest,
    translated_positive: str,
    character,
    second_character,
    is_dual: bool,
    custom_mask: bool = False,
    layout_hint: str = "",
) -> str:
    if not is_dual:
        scene = subtract_prompt_tags(translated_positive, character_outfit_tags(character))
        return compose_stacked_prompt(merge_tags(
            character_tags(character, nsfw_mode=payload.nsfw_mode),
            payload.trigger_words,
            payload.style_tags,
            scene,
        ))

    first_tags = filter_dual_character_tags(merge_tags(
        character_tags(character, nsfw_mode=payload.nsfw_mode),
        payload.trigger_words,
    ))
    second_tags = filter_dual_character_tags(character_tags(second_character, nsfw_mode=payload.nsfw_mode))
    scene_source = subtract_prompt_tags(
        translated_positive,
        character_outfit_tags(character),
        character_outfit_tags(second_character),
    )
    scene_tags = build_dual_scene_tags(payload, scene_source, first_tags, second_tags)
    return compose_stacked_prompt(merge_tags(
        scene_tags,
        dual_character_guard(custom_mask),
        layout_hint if custom_mask else "",
        f"first character: {first_tags}" if first_tags else "",
        f"second character: {second_tags}" if second_tags else "",
    ))


def build_dual_scene_tags(
    payload: GenerateRequest,
    translated_positive: str,
    first_tags: str,
    second_tags: str,
) -> str:
    scene = merge_tags(payload.style_tags, translated_positive)
    # Older consoles inject this exact guard even when no region was painted.
    # Remove the old boilerplate only when its signature is present; preserve
    # ordinary user-authored placement instructions such as "woman on the left".
    keys = {normalize_tag_key(tag) for tag in scene.split(",")}
    if {"two distinct characters", "no fusion", "no mixed features"} <= keys:
        scene = subtract_prompt_tags(scene,
            "2girls, two distinct characters, left and right characters, character A, character B, "
            "separate faces, separate outfits, no fusion, no mixed features, natural close interaction")
    return subtract_prompt_tags(
        scene,
        first_tags,
        second_tags,
        dual_character_guard(True),
        dual_character_guard(False),
    )


def build_regional_global_positive(
    payload: GenerateRequest,
    translated_positive: str,
    character,
    second_character,
    is_dual: bool,
    custom_mask: bool = False,
    layout_hint: str = "",
) -> str:
    if not is_dual:
        return ""
    first_tags = filter_dual_character_tags(merge_tags(
        character_tags(character, nsfw_mode=payload.nsfw_mode),
        payload.trigger_words,
    ))
    second_tags = filter_dual_character_tags(character_tags(second_character, nsfw_mode=payload.nsfw_mode))
    scene_source = subtract_prompt_tags(
        translated_positive,
        character_outfit_tags(character),
        character_outfit_tags(second_character),
    )
    scene_tags = build_dual_scene_tags(payload, scene_source, first_tags, second_tags)
    composition_tags = (
        "coherent interaction"
        if custom_mask
        else "one character on each side"
    )
    return merge_tags(
        dual_character_guard(custom_mask),
        composition_tags,
        # The mask already carries placement. Textual A/B bounding-box descriptions
        # can turn the scene into a labelled character sheet and lengthen conditioning.
        layout_hint if not custom_mask else "",
        scene_tags,
    )


def build_regional_positive_prompts(
    payload: GenerateRequest,
    translated_positive: str,
    character,
    second_character,
    is_dual: bool,
    custom_mask: bool = False,
) -> tuple[str, str]:
    if not is_dual:
        return "", ""
    first_tags = filter_dual_character_tags(merge_tags(
        character_tags(character, nsfw_mode=payload.nsfw_mode),
        payload.trigger_words,
    ))
    second_tags = filter_dual_character_tags(character_tags(second_character, nsfw_mode=payload.nsfw_mode))
    first_region = (
        "one person"
        if custom_mask
        else "left person"
    )
    second_region = (
        "one person"
        if custom_mask
        else "right person"
    )
    left_positive = merge_tags(
        first_region,
        first_tags,
    )
    right_positive = merge_tags(
        second_region,
        second_tags,
    )
    return left_positive, right_positive


def build_negative_prompt(translated_negative: str, is_dual: bool) -> str:
    if not is_dual:
        return translated_negative
    return merge_tags(translated_negative, DUAL_CHARACTER_NEGATIVE_TAGS)
