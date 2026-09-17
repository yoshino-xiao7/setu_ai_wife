from __future__ import annotations

import asyncio
import json
import re
import time

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.prompt_knowledge import knowledge_positive_tags, matched_knowledge_context
from app.prompt_tags import (
    GAZE_AT_VIEWER_TAGS,
    QUALITY_NEGATIVE,
    compose_stacked_negative,
    compose_stacked_prompt,
    rewrite_positive_tags,
)


DEFAULT_NEGATIVE = QUALITY_NEGATIVE
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
    "shorts",
    "necktie",
    "maid",
    "suit",
    "pants",
    "jeans",
    "bikini",
    "underwear",
    "vest",
    "hoodie",
    "sweater",
    "apron",
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
CHARACTER_STYLE_DROP = {
    "anime style",
    "detailed eyes",
    "high quality",
    "masterpiece",
    "best quality",
    "highres",
    "cute",
    "elegant",
    "ethereal",
    "idol",
    "dancer",
    "bare shoulders",
}
CHARACTER_BODY_TOKENS = {
    "breast",
    "breasts",
    "cleavage",
    "thigh",
    "thighs",
    "midriff",
    "navel",
    "hips",
}
SMILE_REQUEST_MARKERS = ("回眸一笑", "回头笑", "回眸笑", "回眸微笑", "一笑", "微笑", "浅笑", "笑着", "笑容")
SMILE_NEGATIVE_TAGS = {
    "smiling",
    "smile",
    "light smile",
    "grin",
    "open mouth",
    "happy expression",
    "winking",
}
CLOSED_MOUTH_WHEN_SMILING = {
    "closed mouth",
    "calm expression",
}


def filter_character_identity_tags(prompt: str) -> str:
    if not prompt:
        return ""
    tags: list[str] = []
    for raw_tag in prompt.split(","):
        tag = raw_tag.strip()
        if not tag:
            continue
        key = normalize_tag_key(tag)
        tokens = set(re.findall(r"[a-z]+", key))
        if key in CHARACTER_STYLE_DROP or key in NSFW_INCOMPATIBLE_EXACT_TAGS:
            continue
        if tokens.intersection(CHARACTER_BODY_TOKENS):
            continue
        if tokens.intersection(NSFW_INCOMPATIBLE_TAG_TOKENS):
            continue
        tags.append(tag)
    return ", ".join(tags)


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
        "You are a Danbooru tag translator for anime checkpoints such as WAI and Animagine. "
        "Convert the Chinese drawing request into comma-separated English Danbooru tags, "
        "not English sentences. Never copy Chinese text into positive or negative. Return JSON only "
        "with keys positive, negative, style_notes. "
        "Order positive tags as: subject count, identity (hair, eyes, accessories), one expression, "
        "gaze, pose (body, limbs, orientation), clothing with colors, color palette, lighting and "
        "skin finish, then background and in-frame scene objects. "
        "The Chinese request is already a single frozen still. Convert only that still. "
        "Do not add a second moment, extra plot, or extra people. "
        "Keep in-frame scene objects such as bed, door, window, furniture, rain, or room interior "
        "when they are described. Do not replace a described indoor scene with a simple or clean "
        "background. Use one camera, one pose, and one expression. "
        "Do not write prose such as beautiful girl, cute girl, elegant atmosphere, or excellent composition. "
        "Keep the user's requested expression. Do not default to closed mouth or a blank face. "
        "If the user asks for a smile, 回眸一笑, or 微笑, put light smile in positive and do not put "
        "smiling, smile, or open mouth in negative. Only ban smile or open mouth when the user "
        "explicitly asks for a serious, calm, or closed-mouth face. If clothing colors are specified, "
        "put conflicting colors in negative. "
        "Do not prepend masterpiece, best quality, highres, high quality, anime illustration, or "
        "detailed eyes unless the user explicitly asks for quality or style boosters. "
        "Keep the default negative practical: anatomy, hands, extra limbs, blur, text, watermark. "
        "Do not put looking at viewer, eye contact, or facing camera in negative when the user asks "
        "for looking back, over-shoulder, looking at viewer, or eye contact. "
        "Only prefer looking away, profile, back view, or looking down when the user asks for that "
        "gaze, or describes a task-focused everyday action such as reading, cooking, or looking out "
        "a window without asking for eye contact. "
        "When NSFW compatibility mode is enabled, omit full garment, outfit, uniform, dress, "
        "censorship, occlusion, covering, foreground-blocking, and cropped-composition tags. "
        "However, deliberately keep intentional NSFW remnant clothing such as micro bikini, "
        "pasties, panties aside, bra pulled down, see-through wet clothing, stockings only, "
        "partially undressed, garter. Preserve identity, body, pose, expression, camera, lighting, "
        "and background tags. Preserve requested cross-section, cutaway, x-ray, internal-anatomy, "
        "and anatomical-visibility descriptors. "
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
    prompt_cn: str = "",
    knowledge_path=None,
) -> PromptResult:
    positive = normalize_prompt_value(parsed.get("positive", ""))
    if contains_cjk(positive):
        positive = remove_cjk_tags(positive)
    positive = rewrite_positive_tags(positive)
    if prompt_cn and knowledge_path is not None:
        positive = merge_unique_tags(knowledge_positive_tags(prompt_cn, knowledge_path), positive)
    positive = apply_lookback_positive_locks(positive, prompt_cn)
    positive = compose_stacked_prompt(positive)
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
    negative = apply_lookback_negative_locks(positive, negative, prompt_cn)
    negative = compose_stacked_negative(negative, positive)
    if nsfw_mode:
        negative = apply_nsfw_visibility_negative_profile(negative, nsfw_visibility_level)
    return PromptResult(
        positive=positive,
        negative=negative,
        style_notes=normalize_prompt_value(parsed.get("style_notes", "")) or f"Translated by {provider} model {model}.",
        used_ollama=used_ollama,
    )


def _has_lookback(positive: str) -> bool:
    keys = {normalize_tag_key(tag) for tag in (positive or "").split(",") if tag.strip()}
    return any(
        key == "looking back over shoulder" or key.startswith("looking back")
        for key in keys
    )


def _wants_smile(prompt_cn: str) -> bool:
    source = prompt_cn or ""
    return any(marker in source for marker in SMILE_REQUEST_MARKERS)


def apply_lookback_positive_locks(positive: str, prompt_cn: str = "") -> str:
    tags = [tag.strip() for tag in (positive or "").split(",") if tag.strip()]
    if _wants_smile(prompt_cn):
        tags = [tag for tag in tags if normalize_tag_key(tag) not in CLOSED_MOUTH_WHEN_SMILING]
    return ", ".join(tags)


def apply_lookback_negative_locks(positive: str, negative: str, prompt_cn: str = "") -> str:
    tags = [tag.strip() for tag in (negative or "").split(",") if tag.strip()]
    drop: set[str] = set()
    if _has_lookback(positive):
        drop.update(GAZE_AT_VIEWER_TAGS)
    if _wants_smile(prompt_cn):
        drop.update(SMILE_NEGATIVE_TAGS)
    if drop:
        tags = [tag for tag in tags if normalize_tag_key(tag) not in drop]
    return ", ".join(tags)


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
        "think": False,
        "keep_alive": settings.ollama_prompt_keep_alive,
        "format": "json",
        "prompt": f"/no_think\n{system_prompt}\n\n{user_prompt}\n\nJSON:",
        "options": {
            "temperature": 0,
            "num_predict": 512,
            "num_gpu": settings.ollama_prompt_num_gpu,
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
                "think": False,
                "keep_alive": settings.ollama_prompt_keep_alive,
                "format": "json",
                "prompt": correction_prompt,
                "options": {
                    "temperature": 0,
                    "num_predict": 512,
                    "num_gpu": settings.ollama_prompt_num_gpu,
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
            prompt_cn=prompt_cn,
            knowledge_path=settings.prompt_knowledge_path,
        )
    except PromptTranslationError:
        raise
    except Exception as exc:
        raise PromptTranslationError(f"Ollama prompt translation failed: {exc}") from exc


async def translate_prompt(
    prompt_cn: str,
    settings: Settings,
    style_tags: str = "",
    negative_prompt: str = "",
    nsfw_mode: bool = False,
    nsfw_visibility_level: str = "STANDARD",
) -> PromptResult:
    del style_tags
    started = time.perf_counter()
    outcome = "failed"
    try:
        # One deadline covers Ollama generation and the English correction pass.
        async with asyncio.timeout(settings.prompt_translation_total_timeout_seconds):
            result = await translate_prompt_with_ollama(
                prompt_cn,
                settings,
                negative_prompt=negative_prompt,
                nsfw_mode=nsfw_mode,
                nsfw_visibility_level=nsfw_visibility_level,
            )
        outcome = "ollama"
        return result
    except TimeoutError as exc:
        outcome = "timeout"
        raise PromptTranslationError(
            f"Prompt translation exceeded {settings.prompt_translation_total_timeout_seconds:g}s total timeout."
        ) from exc
    finally:
        print("[prompt-timing] " + json.dumps({
            "outcome": outcome, "seconds": round(time.perf_counter() - started, 3),
        }), flush=True)
