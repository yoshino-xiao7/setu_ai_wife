from __future__ import annotations

import json
import re

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.prompt_knowledge import matched_knowledge_context


DEFAULT_NEGATIVE = (
    "low quality, worst quality, bad anatomy, bad hands, extra fingers, "
    "missing fingers, deformed, blurry, text, watermark, logo, cropped"
)


class PromptResult(BaseModel):
    positive: str
    negative: str = DEFAULT_NEGATIVE
    style_notes: str = "translated by local Ollama"
    used_ollama: bool = False


class PromptTranslationError(RuntimeError):
    pass


def normalize_prompt_value(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def parse_json_response(raw: str) -> dict:
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(raw[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        raise


def contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value or ""))


async def translate_prompt(
    prompt_cn: str,
    settings: Settings,
    style_tags: str = "",
    negative_prompt: str = "",
) -> PromptResult:
    system_prompt = (
        "You are a Stable Diffusion anime prompt translator. Convert the Chinese drawing request "
        "into concise English tags. Translate character names, actions, scenes, moods, camera, "
        "composition, clothes, lighting, and background details. Never copy Chinese text into "
        "positive or negative. Return JSON only with keys positive, negative, style_notes. "
        "Use comma-separated English tags. Keep negative prompt practical. If local prompt "
        "knowledge is provided, follow it exactly."
    )
    knowledge_context = matched_knowledge_context(prompt_cn, settings.prompt_knowledge_path)
    user_prompt = (
        f"Chinese request: {prompt_cn}\n"
        f"Extra style tags to keep in English if useful: {style_tags or '(none)'}\n"
        f"Existing negative prompt to translate/merge if useful: {negative_prompt or '(none)'}\n"
        f"{knowledge_context or 'Local prompt knowledge matched: (none)'}\n"
        "Return the final JSON now."
    )
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "format": "json",
        "prompt": f"/no_think\n{system_prompt}\n\n{user_prompt}\n\nJSON:",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.prompt_translation_timeout_seconds) as client:
            response = await client.post(f"{settings.ollama_url.rstrip('/')}/api/generate", json=payload)
            response.raise_for_status()
        data = response.json()
        raw = data.get("response") or data.get("thinking") or ""
        parsed = parse_json_response(raw)
        positive = normalize_prompt_value(parsed.get("positive", ""))
        if not positive:
            raise PromptTranslationError("Ollama returned an empty positive prompt.")
        if contains_cjk(positive):
            raise PromptTranslationError("Ollama returned Chinese text in positive prompt; please retry.")
        negative = normalize_prompt_value(parsed.get("negative", negative_prompt or DEFAULT_NEGATIVE)) or DEFAULT_NEGATIVE
        if contains_cjk(negative):
            negative = DEFAULT_NEGATIVE
        if DEFAULT_NEGATIVE not in negative:
            negative = f"{negative}, {DEFAULT_NEGATIVE}"
        return PromptResult(
            positive=positive,
            negative=negative,
            style_notes=normalize_prompt_value(parsed.get("style_notes", "")) or f"Translated by local Ollama model {settings.ollama_model}.",
            used_ollama=True,
        )
    except PromptTranslationError:
        raise
    except Exception as exc:
        raise PromptTranslationError(f"Ollama prompt translation failed: {exc}") from exc
