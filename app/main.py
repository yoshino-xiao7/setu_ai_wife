from __future__ import annotations

import uuid
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.comfyui import ComfyUIClient, build_workflow, random_seed
from app.config import Settings, get_settings
from app.db import JobStore
from app.presets import find_character, list_loras, load_characters, merge_tags
from app.prompting import PromptResult, PromptTranslationError, translate_prompt


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
    "shared hair color, shared outfit, duplicated outfit, conjoined bodies"
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


class TranslateRequest(BaseModel):
    prompt_cn: str = Field(..., min_length=1, max_length=1000)
    style_tags: str = ""
    negative_prompt: str = ""


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
    prompt_source = merge_tags(
        character.trigger_words if character else "",
        character.default_positive if character else "",
        second_character.trigger_words if second_character else "",
        second_character.default_positive if second_character else "",
        payload.trigger_words,
        payload.style_tags,
        character.style_tags if character else "",
        second_character.style_tags if second_character else "",
        dual_character_guard() if is_dual else "",
        payload.prompt_cn,
    )
    if is_dual:
        prompt_source = filter_dual_character_tags(prompt_source)
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
            )
        except PromptTranslationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    positive_prompt = build_positive_prompt(payload, prompt.positive, character, second_character, is_dual)
    regional_global_positive = build_regional_global_positive(
        payload,
        prompt.positive,
        character,
        second_character,
        is_dual,
    )
    regional_left_positive, regional_right_positive = build_regional_positive_prompts(
        payload,
        prompt.positive,
        character,
        second_character,
        is_dual,
    )
    negative_prompt = build_negative_prompt(prompt.negative, is_dual)
    lora_name = payload.lora_name or (character.lora_name if character else "")
    lora_strength = payload.lora_strength or (character.lora_strength if character and character.lora_name else 0)
    second_lora_name = payload.second_lora_name or (second_character.lora_name if second_character else "")
    second_lora_strength = payload.second_lora_strength or (second_character.lora_strength if second_character and second_character.lora_name else 0)
    if is_dual:
        lora_strength = min(lora_strength, 0.45)
        second_lora_strength = min(second_lora_strength, 0.45)
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
        workflow = build_workflow(
            positive=job.get("regional_global_positive") or job["prompt_positive"],
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
            regional_left_positive=job.get("regional_left_positive") or "",
            regional_right_positive=job.get("regional_right_positive") or "",
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


def character_tags(character) -> str:
    if not character:
        return ""
    return merge_tags(character.trigger_words, character.default_positive, character.style_tags)


def dual_character_guard() -> str:
    return (
        "2girls, two distinct characters, duo, separate faces, separate outfits, "
        "left and right characters, no fusion, no mixed features"
    )


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
    return merge_tags(
        dual_character_guard(),
        scene_tags,
        f"left character: {first_tags}" if first_tags else "",
        f"right character: {second_tags}" if second_tags else "",
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
        dual_character_guard(),
    )


def build_regional_global_positive(
    payload: GenerateRequest,
    translated_positive: str,
    character,
    second_character,
    is_dual: bool,
) -> str:
    if not is_dual:
        return ""
    first_tags = filter_dual_character_tags(merge_tags(character_tags(character), payload.trigger_words))
    second_tags = filter_dual_character_tags(character_tags(second_character))
    scene_tags = build_dual_scene_tags(payload, translated_positive, first_tags, second_tags)
    return merge_tags(
        dual_character_guard(),
        "balanced two character composition, clear left-right separation",
        scene_tags,
    )


def build_regional_positive_prompts(
    payload: GenerateRequest,
    translated_positive: str,
    character,
    second_character,
    is_dual: bool,
) -> tuple[str, str]:
    if not is_dual:
        return "", ""
    first_tags = filter_dual_character_tags(merge_tags(character_tags(character), payload.trigger_words))
    second_tags = filter_dual_character_tags(character_tags(second_character))
    scene_tags = build_dual_scene_tags(payload, translated_positive, first_tags, second_tags)
    left_positive = merge_tags(
        "left side of image, left character, only one character in this region, distinct face, distinct outfit",
        scene_tags,
        first_tags,
    )
    right_positive = merge_tags(
        "right side of image, right character, only one character in this region, distinct face, distinct outfit",
        scene_tags,
        second_tags,
    )
    return left_positive, right_positive


def build_negative_prompt(translated_negative: str, is_dual: bool) -> str:
    if not is_dual:
        return translated_negative
    return merge_tags(translated_negative, DUAL_CHARACTER_NEGATIVE_TAGS)
