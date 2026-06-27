from __future__ import annotations

import uuid
from pathlib import Path

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


class GenerateRequest(BaseModel):
    prompt_cn: str = Field(..., min_length=1, max_length=1000)
    prompt_positive: str = ""
    prompt_negative: str = ""
    style_notes: str = ""
    character_id: str | None = None
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


@app.post("/api/generate")
async def generate(
    payload: GenerateRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: JobStore = Depends(get_store),
) -> dict[str, str]:
    character = find_character(settings, payload.character_id)
    prompt_source = merge_tags(
        character.trigger_words if character else "",
        character.default_positive if character else "",
        payload.trigger_words,
        payload.style_tags,
        character.style_tags if character else "",
        payload.prompt_cn,
    )
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
    positive_prompt = merge_tags(
        character.trigger_words if character else "",
        character.default_positive if character else "",
        payload.trigger_words,
        payload.style_tags,
        character.style_tags if character else "",
        prompt.positive,
    )
    lora_name = payload.lora_name or (character.lora_name if character else "")
    lora_strength = payload.lora_strength or (character.lora_strength if character and character.lora_name else 0)
    job_id = uuid.uuid4().hex
    seed = payload.seed or random_seed()
    job = {
        "id": job_id,
        "prompt_cn": payload.prompt_cn,
        "prompt_positive": positive_prompt,
        "prompt_negative": prompt.negative,
        "style_notes": prompt.style_notes,
        "seed": seed,
        "width": payload.width,
        "height": payload.height,
        "steps": payload.steps or settings.default_steps,
        "cfg": payload.cfg or settings.default_cfg,
        "checkpoint": payload.checkpoint or settings.default_checkpoint,
        "lora_name": lora_name,
        "lora_strength": lora_strength,
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
