from __future__ import annotations

import json

import httpx
from pydantic import BaseModel

from app.config import Settings


DEFAULT_NEGATIVE = (
    "low quality, worst quality, bad anatomy, bad hands, extra fingers, "
    "missing fingers, deformed, blurry, text, watermark, logo, cropped"
)


class PromptResult(BaseModel):
    positive: str
    negative: str = DEFAULT_NEGATIVE
    style_notes: str = "fallback template"
    used_ollama: bool = False


def normalize_prompt_value(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def fallback_prompt(prompt_cn: str) -> PromptResult:
    return PromptResult(
        positive=(
            "anime style, high quality, detailed illustration, masterpiece, "
            f"{prompt_cn}"
        ),
        negative=DEFAULT_NEGATIVE,
        style_notes="Ollama unavailable or returned invalid JSON; used a conservative template.",
        used_ollama=False,
    )


async def translate_prompt(prompt_cn: str, settings: Settings) -> PromptResult:
    system_prompt = (
        "You convert Chinese drawing requests into concise English anime image tags. "
        "Return JSON only with keys positive, negative, style_notes. "
        "Do not include sexualized minors. Keep negative prompt practical."
    )
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "format": "json",
        "prompt": f"/no_think\n{system_prompt}\n\nChinese request: {prompt_cn}\n\nJSON:",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.prompt_translation_timeout_seconds) as client:
            response = await client.post(f"{settings.ollama_url.rstrip('/')}/api/generate", json=payload)
            response.raise_for_status()
        data = response.json()
        raw = data.get("response") or data.get("thinking") or ""
        parsed = json.loads(raw)
        positive = normalize_prompt_value(parsed.get("positive", ""))
        if not positive:
            return fallback_prompt(prompt_cn)
        negative = normalize_prompt_value(parsed.get("negative", DEFAULT_NEGATIVE)) or DEFAULT_NEGATIVE
        if DEFAULT_NEGATIVE not in negative:
            negative = f"{negative}, {DEFAULT_NEGATIVE}"
        return PromptResult(
            positive=positive,
            negative=negative,
            style_notes=normalize_prompt_value(parsed.get("style_notes", "")),
            used_ollama=True,
        )
    except Exception:
        return fallback_prompt(prompt_cn)
