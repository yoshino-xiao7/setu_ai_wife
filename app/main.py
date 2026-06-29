from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFilter
from pydantic import BaseModel, Field

from app.comfyui import ComfyUIClient, build_inpaint_workflow, build_mask_conditioning_workflow, build_workflow, random_seed
from app.config import Settings, get_settings
from app.db import JobStore
from app.presets import find_character, list_loras, load_characters, merge_tags
from app.prompting import PromptResult, PromptTranslationError, filter_nsfw_incompatible_tags, translate_prompt


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
    "merged characters, fused characters, hybrid character, mixed character features, "
    "same face, identical faces, wrong character on left, wrong character on right, "
    "shared hair color, shared outfit, duplicated outfit, conjoined bodies, "
    "more than two people, extra people, three girls, crowd, duplicate character, "
    "extra arms, extra hands, extra legs, extra feet, too many limbs, "
    "broken interaction, disconnected hands, tangled limbs"
)
NSFW_DEFAULT_LORA_STRENGTH = 0.6
NSFW_MAX_LORA_STRENGTH = 0.65


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


class TranslateRequest(BaseModel):
    prompt_cn: str = Field(..., min_length=1, max_length=1000)
    style_tags: str = ""
    negative_prompt: str = ""
    nsfw_mode: bool = False


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
    character = find_character(settings, payload.character_id)
    second_character = find_character(settings, payload.second_character_id)
    is_dual = is_dual_generation(payload)
    has_custom_mask = has_complete_character_mask(payload.character_mask_json)
    layout_hint = build_character_layout_hint(payload.character_mask_json) if is_dual and has_custom_mask else ""
    prompt_source = merge_tags(
        character.trigger_words if character else "",
        character.default_positive if character else "",
        second_character.trigger_words if second_character else "",
        second_character.default_positive if second_character else "",
        payload.trigger_words,
        payload.style_tags,
        character.style_tags if character else "",
        second_character.style_tags if second_character else "",
        dual_character_guard(has_custom_mask) if is_dual else "",
        layout_hint,
        payload.prompt_cn,
    )
    if is_dual:
        prompt_source = filter_dual_character_tags(prompt_source)
    if payload.nsfw_mode:
        prompt_source = filter_nsfw_incompatible_tags(prompt_source)
    if payload.prompt_positive.strip():
        prompt = PromptResult(
            positive=payload.prompt_positive.strip(),
            negative=payload.prompt_negative.strip() or PromptResult.model_fields["negative"].default,
            style_notes=payload.style_notes.strip() or "provided by cloud prompt editor",
        )
    else:
        try:
            prompt = await translate_prompt(
                prompt_source,
                settings,
                style_tags=payload.style_tags,
                negative_prompt=payload.prompt_negative,
                nsfw_mode=payload.nsfw_mode,
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
        positive_prompt = filter_nsfw_incompatible_tags(positive_prompt)
        regional_global_positive = filter_nsfw_incompatible_tags(regional_global_positive)
        regional_left_positive = filter_nsfw_incompatible_tags(regional_left_positive)
        regional_right_positive = filter_nsfw_incompatible_tags(regional_right_positive)
    negative_prompt = build_negative_prompt(prompt.negative, is_dual)
    lora_name = payload.lora_name or (character.lora_name if character else "")
    lora_strength = payload.lora_strength or (character.lora_strength if character and character.lora_name else 0)
    second_lora_name = payload.second_lora_name or (second_character.lora_name if second_character else "")
    second_lora_strength = payload.second_lora_strength or (second_character.lora_strength if second_character and second_character.lora_name else 0)
    if is_dual:
        lora_strength = min(lora_strength, settings.dual_lora_strength_cap)
        second_lora_strength = min(second_lora_strength, settings.dual_lora_strength_cap)
    if payload.nsfw_mode:
        if lora_name:
            lora_strength = min(lora_strength or NSFW_DEFAULT_LORA_STRENGTH, NSFW_MAX_LORA_STRENGTH)
        if second_lora_name:
            second_lora_strength = min(
                second_lora_strength or NSFW_DEFAULT_LORA_STRENGTH,
                NSFW_MAX_LORA_STRENGTH,
            )
    job_id = uuid.uuid4().hex
    seed = payload.seed or random_seed()
    job = {
        "id": job_id,
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
        "lora_name": lora_name,
        "lora_strength": lora_strength,
        "second_lora_name": second_lora_name if is_dual else "",
        "second_lora_strength": second_lora_strength if is_dual else 0,
        "status": "queued",
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
        if should_use_dual_inpaint(settings, job):
            image_path = await run_dual_inpaint_generation(job, settings, store, client)
        elif should_use_dual_mask_conditioning(settings, job):
            image_path = await run_dual_mask_conditioning_generation(job, settings, store, client)
        else:
            workflow = build_workflow(
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
                lora_name=job["lora_name"],
                lora_strength=job["lora_strength"],
                second_lora_name=job["second_lora_name"],
                second_lora_strength=job["second_lora_strength"],
                filename_prefix=f"local_ai_drawing/{job_id}",
            )
            prompt_id = await client.queue_prompt(workflow, client_id=job_id)
            store.update_job(job_id, comfy_prompt_id=prompt_id)
            history = await client.wait_for_history(prompt_id)
            image_path = await client.download_first_image(history, settings.output_dir, job_id)
        store.update_job(job_id, status="completed", image_path=image_path.name)
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


@app.get("/api/images/{filename}")
def image(filename: str, settings: Settings = Depends(get_settings)) -> FileResponse:
    safe_name = Path(filename).name
    path = settings.output_dir / safe_name
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
        "use the drawn A/B regions as a rough composition guide only",
        f"character A position: {describe_box_position(primary_box)}",
        f"character B position: {describe_box_position(secondary_box)}",
        relation,
        "exactly two separate characters, preserve two distinct faces and two distinct bodies",
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
        return "close interaction, overlapping composition, keep two separate heads and bodies"
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


def should_use_dual_mask_conditioning(settings: Settings, job: dict) -> bool:
    strategy = settings.dual_character_strategy.strip().lower()
    return (
        str(job.get("generation_mode") or "").upper() == "DUAL"
        and strategy in {"mask", "masked", "mask-conditioning", "conditioning", "regional-mask"}
        and bool(str(job.get("character_mask_json") or "").strip())
        and bool(job.get("regional_left_positive"))
        and bool(job.get("regional_right_positive"))
    )


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
        return await queue_and_download(client, store, job_id, workflow, settings.output_dir, job_id)
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
    base_path = await queue_and_download(client, store, job_id, base_workflow, settings.output_dir, f"{job_id}_base")

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
        left_path = await queue_and_download(client, store, job_id, left_workflow, settings.output_dir, f"{job_id}_left")
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
        return await queue_and_download(client, store, job_id, right_workflow, settings.output_dir, job_id)
    finally:
        for filename in uploaded_inputs:
            client.cleanup_comfyui_input_file(filename)
        cleanup_temp_paths(temp_paths)


async def queue_and_download(
    client: ComfyUIClient,
    store: JobStore,
    job_id: str,
    workflow: dict,
    output_dir: Path,
    image_name: str,
) -> Path:
    prompt_id = await client.queue_prompt(workflow, client_id=job_id)
    store.update_job(job_id, comfy_prompt_id=prompt_id)
    history = await client.wait_for_history(prompt_id)
    return await client.download_first_image(history, output_dir, image_name)


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


def character_tags(character) -> str:
    if not character:
        return ""
    return merge_tags(character.trigger_words, character.default_positive, character.style_tags)


def dual_character_guard(custom_mask: bool = False) -> str:
    base = (
        "2girls, exactly two characters total, two distinct characters, duo, "
        "separate faces, separate outfits, no extra people, no fusion, no mixed features"
    )
    if custom_mask:
        return merge_tags(base, "natural close interaction, clear individual character identities")
    return merge_tags(base, "left and right characters")


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
        return merge_tags(
            character_tags(character),
            payload.trigger_words,
            payload.style_tags,
            translated_positive,
        )

    first_tags = filter_dual_character_tags(merge_tags(character_tags(character), payload.trigger_words))
    second_tags = filter_dual_character_tags(character_tags(second_character))
    scene_tags = build_dual_scene_tags(payload, translated_positive, first_tags, second_tags)
    first_label = "character A" if custom_mask else "character A on the left side"
    second_label = "character B" if custom_mask else "character B on the right side"
    return merge_tags(
        dual_character_guard(custom_mask),
        layout_hint,
        scene_tags,
        f"{first_label}: {first_tags}" if first_tags else "",
        f"{second_label}: {second_tags}" if second_tags else "",
    )


def build_dual_scene_tags(
    payload: GenerateRequest,
    translated_positive: str,
    first_tags: str,
    second_tags: str,
) -> str:
    return subtract_prompt_tags(
        merge_tags(payload.style_tags, translated_positive),
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
    first_tags = filter_dual_character_tags(merge_tags(character_tags(character), payload.trigger_words))
    second_tags = filter_dual_character_tags(character_tags(second_character))
    scene_tags = build_dual_scene_tags(payload, translated_positive, first_tags, second_tags)
    composition_tags = (
        "natural close interaction between exactly two characters, preserve the requested contact and relative positions, no extra people"
        if custom_mask
        else "balanced two character composition, clear left-right separation, exactly one character on each side, no extra people"
    )
    return merge_tags(
        dual_character_guard(custom_mask),
        composition_tags,
        layout_hint,
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
    first_tags = filter_dual_character_tags(merge_tags(character_tags(character), payload.trigger_words))
    second_tags = filter_dual_character_tags(character_tags(second_character))
    first_region = (
        "character A only, one person only in this region, no character B, no second person, one complete body, distinct face, distinct outfit"
        if custom_mask
        else "left side of image, character A only, one person only in this region, no character B, no second person, one complete body, distinct face, distinct outfit"
    )
    second_region = (
        "character B only, one person only in this region, no character A, no second person, one complete body, distinct face, distinct outfit"
        if custom_mask
        else "right side of image, character B only, one person only in this region, no character A, no second person, one complete body, distinct face, distinct outfit"
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
