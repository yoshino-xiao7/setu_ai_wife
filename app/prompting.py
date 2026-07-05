from __future__ import annotations

import asyncio
import json
import re

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.prompt_knowledge import matched_knowledge_context


DEFAULT_NEGATIVE = (
    "low quality, worst quality, bad anatomy, bad hands, extra fingers, "
    "missing fingers, deformed, blurry, text, watermark, logo, cropped, "
    "looking at viewer, eye contact, facing camera, direct gaze, staring at viewer, "
    "front view, head facing forward, facing the viewer, looking straight at camera"
)
NSFW_INCOMPATIBLE_TAG_TOKENS = {
    "clothes",
    "clothing",
    "outfit",
    "uniform",
    "dress",
    "skirt",
    "shirt",
    "blouse",
    "jacket",
    "coat",
    "kimono",
    "sleeve",
    "sleeves",
    "glove",
    "gloves",
    "gauntlet",
    "gauntlets",
    "pantyhose",
    "stocking",
    "stockings",
    "thighhigh",
    "thighhighs",
    "sock",
    "socks",
    "shoe",
    "shoes",
    "boot",
    "boots",
    "obi",
    "robe",
    "cape",
    "cloak",
    "armor",
    "bodysuit",
    "leotard",
    "swimsuit",
    "censor",
    "censored",
    "censoring",
    "censorship",
    "mosaic",
    "cropped",
    "obscured",
}
NSFW_INCOMPATIBLE_EXACT_TAGS = {
    "nontraditional miko",
    "traditional miko",
    "strategically covered",
    "hands covering body",
    "hand covering body",
    "hair covering body",
    "hair over body",
    "foreground obstruction",
    "object in foreground",
    "obscured anatomy",
    "cropped body",
    "out of frame",
    "steam covering body",
    "shadow covering body",
    "convenient censoring",
    "mosaic censorship",
    "bar censor",
    "black censor bar",
}
NSFW_ANATOMY_VISIBILITY_PROTECTED_PHRASES = {
    "cross section",
    "cross-section",
    "cutaway",
    "cutaway view",
    "x ray",
    "x-ray",
    "internal anatomy",
    "visible anatomy",
    "anatomical view",
    "anatomical detail",
}

# These are intentionally kept even in nsfw_mode because they represent
# popular "NSFW remnant clothing" aesthetics (partially clothed / aside / minimal coverage).
NSFW_ALLOWED_REMNANT_PHRASES = {
    "micro bikini",
    "sling bikini",
    "pasties",
    "nipple pasties",
    "panties aside",
    "bra pulled",
    "bra down",
    "see through",
    "wet shirt",
    "wet clothes",
    "stockings only",
    "thighhighs only",
    "garter belt",
    "garter only",
    "partially undressed",
    "clothes aside",
    "shirt open",
}
NSFW_VISIBILITY_POSITIVE_TAGS = (
    "full body visible",
)
NSFW_VISIBILITY_NEGATIVE_TAGS = (
    "censored",
    "mosaic censorship",
    "bar censor",
    "convenient censoring",
    "strategically covered",
    "obscured anatomy",
    "hands covering body",
    "hair covering body",
    "foreground obstruction",
    "cropped body",
    "out of frame",
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
    if not raw or not raw.strip():
        raise PromptTranslationError("Ollama returned an empty JSON response.")
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            candidate = raw[start : end + 1]
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                parsed, _ = json.JSONDecoder().raw_decode(raw[start:])
            return parsed if isinstance(parsed, dict) else {}
        raise


def contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value or ""))


def ollama_output_text(data: dict) -> str:
    return str(data.get("response") or data.get("thinking") or "").strip()


def chat_completion_output_text(data: dict) -> str:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else {}
    if isinstance(message, dict):
        return str(message.get("content") or "").strip()
    return str(first.get("text") or "").strip()


def chat_completion_sse_output_text(raw: str) -> str:
    content_parts: list[str] = []
    error_message = ""
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            error_message = str(error.get("message") or error)
            continue
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            continue
        first = choices[0] if isinstance(choices[0], dict) else {}
        delta = first.get("delta") if isinstance(first, dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        if isinstance(delta, dict) and delta.get("content"):
            content_parts.append(str(delta.get("content")))
        elif isinstance(message, dict) and message.get("content"):
            content_parts.append(str(message.get("content")))
    text = "".join(content_parts).strip()
    if text:
        return text
    if error_message:
        raise PromptTranslationError(error_message)
    return ""


def remove_cjk_tags(value: str) -> str:
    return ", ".join(
        tag
        for raw_tag in value.split(",")
        if (tag := raw_tag.strip()) and not contains_cjk(tag)
    )


def normalize_tag_key(tag: str) -> str:
    return " ".join(tag.strip().lower().replace("_", " ").split())


def merge_unique_tags(*parts: str) -> str:
    tags: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for raw_tag in (part or "").split(","):
            tag = raw_tag.strip()
            key = normalize_tag_key(tag)
            if not tag or key in seen:
                continue
            seen.add(key)
            tags.append(tag)
    return ", ".join(tags)


def apply_nsfw_visibility_positive(prompt: str) -> str:
    return apply_nsfw_visibility_profile(prompt, "STANDARD")


def apply_nsfw_visibility_negative(prompt: str) -> str:
    return apply_nsfw_visibility_negative_profile(prompt, "STANDARD")


def normalize_visibility_level(value: str) -> str:
    level = (value or "STANDARD").strip().upper()
    return level if level in {"LIGHT", "STANDARD", "STRONG"} else "STANDARD"


def apply_nsfw_visibility_profile(prompt: str, level: str) -> str:
    level = normalize_visibility_level(level)
    prompt = remove_visibility_control_tags(prompt, negative=False)
    if level == "STRONG":
        prompt = merge_unique_tags(
            prompt,
            "(uncensored adult nude body:1.2), explicit nude anatomy visible, "
            "unobstructed anatomy, clear frontal view, front-facing pose, "
            "centered composition, uncluttered foreground",
        )
    lower = (prompt or "").lower()
    if (
        any(tag in lower for tag in ("full body", "head to toe", "wide shot"))
        and not any(tag in lower for tag in (
            "close-up", "portrait", "face focus", "upper body", "bust", "cowboy shot", "waist up"
        ))
    ):
        return merge_unique_tags(prompt, "full body visible, head-to-toe framing")
    return prompt


def apply_nsfw_visibility_negative_profile(prompt: str, level: str) -> str:
    level = normalize_visibility_level(level)
    tags = {
        "LIGHT": "censored, mosaic censorship, strategically covered",
        "STANDARD": ", ".join(NSFW_VISIBILITY_NEGATIVE_TAGS),
        "STRONG": (
            "(censored:1.3), (mosaic censorship:1.3), (convenient censoring:1.25), "
            "(strategically covered:1.25), (obscured anatomy:1.25), hands covering body, "
            "hair covering body, foreground obstruction, cropped body, out of frame, "
            "clothing coverage, fabric coverage, underwear"
        ),
    }[level]
    return merge_unique_tags(remove_visibility_control_tags(prompt, negative=True), tags)


def remove_visibility_control_tags(prompt: str, *, negative: bool) -> str:
    markers = (
        (
            "censored", "mosaic censorship", "convenient censoring", "strategically covered",
            "obscured anatomy", "hands covering body", "hair covering body",
            "foreground obstruction", "cropped body", "out of frame",
        )
        if negative
        else (
            "unobstructed anatomy", "explicit anatomy visible", "clear frontal view",
            "clear view", "full body visible", "head-to-toe framing",
            "front-facing pose", "centered composition", "uncluttered foreground",
        )
    )
    return ", ".join(
        tag.strip()
        for tag in (prompt or "").split(",")
        if tag.strip() and not any(marker in normalize_tag_key(tag) for marker in markers)
    )


def filter_nsfw_incompatible_tags(prompt: str) -> str:
    if not prompt:
        return ""
    tags: list[str] = []
    for raw_tag in prompt.split(","):
        tag = raw_tag.strip()
        key = normalize_tag_key(tag)
        tokens = set(re.findall(r"[a-z]+", key))
        plain_key = " ".join(re.findall(r"[a-z]+", key))

        # Always preserve explicit anatomy visibility requests
        if any(phrase in key for phrase in NSFW_ANATOMY_VISIBILITY_PROTECTED_PHRASES):
            tags.append(tag)
            continue

        # Preserve intentional NSFW "remnant clothing" (micro, pasties, pulled aside, see-through wet, etc.)
        if any(phrase in key for phrase in NSFW_ALLOWED_REMNANT_PHRASES):
            tags.append(tag)
            continue

        if (
            not tag
            or plain_key in NSFW_INCOMPATIBLE_EXACT_TAGS
            or tokens.intersection(NSFW_INCOMPATIBLE_TAG_TOKENS)
        ):
            continue
        tags.append(tag)
    return ", ".join(tags)


def build_translation_prompts(prompt_cn: str, settings: Settings, negative_prompt: str, nsfw_mode: bool) -> tuple[str, str]:
    system_prompt = (
        "You are a Stable Diffusion anime prompt translator. Convert the Chinese drawing request "
        "into concise English tags. Translate character names, actions, scenes, moods, camera, "
        "composition, clothes, lighting, and background details. Never copy Chinese text into "
        "positive or negative. Return JSON only with keys positive, negative, style_notes. "
        "Use comma-separated English tags. Do not prepend generic quality boosters such as "
        "masterpiece, best quality, high quality, anime illustration, detailed eyes, or clean "
        "lineart unless the user explicitly asks for them. Keep negative prompt practical. "
        "When NSFW compatibility mode is enabled, omit full garment, outfit, uniform, dress, "
        "censorship, occlusion, covering, foreground-blocking, and cropped-composition tags. "
        "However, deliberately keep intentional NSFW remnant clothing such as micro bikini, "
        "pasties, panties aside, bra pulled down, see-through wet clothing, stockings only, "
        "partially undressed, garter. Preserve identity, body, pose, expression, camera, lighting, "
        "and background tags. Preserve requested cross-section, cutaway, x-ray, internal-anatomy, "
        "and anatomical-visibility descriptors. "
        "If the scene describes looking out a window, reading, cooking, or any everyday moment, "
        "strongly prefer natural poses where the character is NOT facing the camera — use looking away, "
        "gazing out, side view, back view, looking down, profile, turned head. Add 'not looking at viewer' "
        "to negative when appropriate. "
        "Do not add extra composition-control tags unless the user requests them. "
        "If local prompt knowledge is provided, follow it exactly."
    )
    knowledge_context = matched_knowledge_context(prompt_cn, settings.prompt_knowledge_path)
    user_prompt = (
        f"Chinese request: {prompt_cn}\n"
        f"Existing negative prompt to translate/merge if useful: {negative_prompt or '(none)'}\n"
        f"NSFW compatibility mode: {'enabled' if nsfw_mode else 'disabled'}\n"
        f"{knowledge_context or 'Local prompt knowledge matched: (none)'}\n"
        "Return the final JSON now."
    )
    return system_prompt, user_prompt


def finalize_prompt_result(
    parsed: dict,
    *,
    negative_prompt: str,
    nsfw_mode: bool,
    nsfw_visibility_level: str,
    provider: str,
    model: str,
    used_ollama: bool,
) -> PromptResult:
    positive = normalize_prompt_value(parsed.get("positive", ""))
    if contains_cjk(positive):
        positive = remove_cjk_tags(positive)
    if nsfw_mode:
        positive = filter_nsfw_incompatible_tags(positive)
        positive = apply_nsfw_visibility_profile(positive, nsfw_visibility_level)
    if not positive:
        raise PromptTranslationError(f"{provider} could not produce usable English positive tags.")
    negative = normalize_prompt_value(parsed.get("negative", negative_prompt or DEFAULT_NEGATIVE)) or DEFAULT_NEGATIVE
    if contains_cjk(negative):
        negative = remove_cjk_tags(negative) or DEFAULT_NEGATIVE
    if DEFAULT_NEGATIVE not in negative:
        negative = f"{negative}, {DEFAULT_NEGATIVE}"
    if nsfw_mode:
        negative = apply_nsfw_visibility_negative_profile(negative, nsfw_visibility_level)
    return PromptResult(
        positive=positive,
        negative=negative,
        style_notes=normalize_prompt_value(parsed.get("style_notes", "")) or f"Translated by {provider} model {model}.",
        used_ollama=used_ollama,
    )


async def translate_prompt_with_ollama(
    prompt_cn: str,
    settings: Settings,
    *,
    negative_prompt: str = "",
    nsfw_mode: bool = False,
    nsfw_visibility_level: str = "STANDARD",
) -> PromptResult:
    system_prompt, user_prompt = build_translation_prompts(prompt_cn, settings, negative_prompt, nsfw_mode)
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "format": "json",
        "prompt": f"/no_think\n{system_prompt}\n\n{user_prompt}\n\nJSON:",
        "options": {
            "temperature": 0,
            "num_predict": 512,
            "num_gpu": max(0, settings.ollama_prompt_num_gpu),
        },
    }
    try:
        async with httpx.AsyncClient(timeout=settings.prompt_translation_timeout_seconds) as client:
            response = await client.post(f"{settings.ollama_url.rstrip('/')}/api/generate", json=payload)
            response.raise_for_status()
        data = response.json()
        raw = ollama_output_text(data)
        parsed = parse_json_response(raw)
        positive = normalize_prompt_value(parsed.get("positive", ""))
        if contains_cjk(positive):
            original_parsed = parsed
            original_positive = positive
            correction_prompt = (
                "/no_think\n"
                "Rewrite the following Stable Diffusion prompt JSON into English only. "
                "Translate every Chinese word, including names, actions, scenes, and descriptions. "
                "Keep concise comma-separated tags. Return JSON only with keys positive, negative, "
                "style_notes. Do not explain.\n\n"
                f"Original Chinese request: {prompt_cn}\n"
                f"JSON to correct: {raw}\n\n"
                'Example output: {"positive":"woman, silver hair, rainy night, neon lights",'
                '"negative":"low quality, blurry","style_notes":"English tags"}'
            )
            correction_payload = {
                "model": settings.ollama_model,
                "stream": False,
                "format": "json",
                "prompt": correction_prompt,
                "options": {
                    "temperature": 0,
                    "num_predict": 512,
                    "num_gpu": max(0, settings.ollama_prompt_num_gpu),
                },
            }
            try:
                async with httpx.AsyncClient(timeout=settings.prompt_translation_timeout_seconds) as client:
                    correction_response = await client.post(
                        f"{settings.ollama_url.rstrip('/')}/api/generate",
                        json=correction_payload,
                    )
                    correction_response.raise_for_status()
                correction_data = correction_response.json()
                correction_raw = ollama_output_text(correction_data)
                correction_parsed = parse_json_response(correction_raw)
                corrected_positive = normalize_prompt_value(correction_parsed.get("positive", ""))
                if corrected_positive:
                    parsed = correction_parsed
                    positive = corrected_positive
            except (httpx.HTTPError, json.JSONDecodeError, PromptTranslationError, ValueError):
                parsed = original_parsed
                positive = original_positive
        return finalize_prompt_result(
            parsed,
            negative_prompt=negative_prompt,
            nsfw_mode=nsfw_mode,
            nsfw_visibility_level=nsfw_visibility_level,
            provider="local Ollama",
            model=settings.ollama_model,
            used_ollama=True,
        )
    except PromptTranslationError:
        raise
    except Exception as exc:
        raise PromptTranslationError(f"Ollama prompt translation failed: {exc}") from exc


async def translate_prompt_with_grok2api(
    prompt_cn: str,
    settings: Settings,
    *,
    negative_prompt: str = "",
    nsfw_mode: bool = False,
    nsfw_visibility_level: str = "STANDARD",
) -> PromptResult:
    if not settings.grok2api_url:
        raise PromptTranslationError("grok2api prompt translation is not configured.")
    system_prompt, user_prompt = build_translation_prompts(prompt_cn, settings, negative_prompt, nsfw_mode)
    url = settings.grok2api_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions" if url.endswith("/v1") else f"{url}/v1/chat/completions"
    model_candidates = [settings.grok2api_model]
    model_candidates.extend(
        model.strip()
        for model in (settings.grok2api_fallback_models or "").split(",")
        if model.strip() and model.strip() not in model_candidates
    )
    headers = {"Content-Type": "application/json"}
    if settings.grok2api_api_key:
        headers["Authorization"] = f"Bearer {settings.grok2api_api_key}"
    errors: list[str] = []
    try:
        for model in model_candidates:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{user_prompt}\n\nReturn JSON only."},
                ],
                "temperature": 0,
                "max_tokens": 512,
                "response_format": {"type": "json_object"},
            }
            try:
                async with httpx.AsyncClient(timeout=settings.prompt_translation_timeout_seconds) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" in content_type or response.text.lstrip().startswith(":"):
                    raw = chat_completion_sse_output_text(response.text)
                else:
                    raw = chat_completion_output_text(response.json())
                parsed = parse_json_response(raw)
                return finalize_prompt_result(
                    parsed,
                    negative_prompt=negative_prompt,
                    nsfw_mode=nsfw_mode,
                    nsfw_visibility_level=nsfw_visibility_level,
                    provider="grok2api",
                    model=model,
                    used_ollama=False,
                )
            except Exception as exc:
                errors.append(f"{model}: {exc}")
                continue
        raise PromptTranslationError("; ".join(errors) or "all grok2api models failed")
    except PromptTranslationError:
        raise
    except Exception as exc:
        raise PromptTranslationError(f"grok2api prompt translation failed: {exc}") from exc


async def first_successful_prompt_result(tasks: list[asyncio.Task[PromptResult]]) -> PromptResult:
    errors: list[str] = []
    pending = set(tasks)
    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            winner: PromptResult | None = None
            for task in done:
                try:
                    result = task.result()
                except PromptTranslationError as exc:
                    errors.append(str(exc))
                    continue
                if winner is None:
                    winner = result
            if winner is not None:
                for pending_task in pending:
                    pending_task.cancel()
                return winner
        raise PromptTranslationError("; ".join(errors) or "Prompt translation failed.")
    finally:
        for task in pending:
            task.cancel()


async def translate_prompt(
    prompt_cn: str,
    settings: Settings,
    style_tags: str = "",
    negative_prompt: str = "",
    nsfw_mode: bool = False,
    nsfw_visibility_level: str = "STANDARD",
) -> PromptResult:
    del style_tags
    if not settings.grok2api_url:
        return await translate_prompt_with_ollama(
            prompt_cn,
            settings,
            negative_prompt=negative_prompt,
            nsfw_mode=nsfw_mode,
            nsfw_visibility_level=nsfw_visibility_level,
        )
    tasks = [
        asyncio.create_task(
            translate_prompt_with_ollama(
                prompt_cn,
                settings,
                negative_prompt=negative_prompt,
                nsfw_mode=nsfw_mode,
                nsfw_visibility_level=nsfw_visibility_level,
            )
        ),
        asyncio.create_task(
            translate_prompt_with_grok2api(
                prompt_cn,
                settings,
                negative_prompt=negative_prompt,
                nsfw_mode=nsfw_mode,
                nsfw_visibility_level=nsfw_visibility_level,
            )
        ),
    ]
    return await first_successful_prompt_result(tasks)
