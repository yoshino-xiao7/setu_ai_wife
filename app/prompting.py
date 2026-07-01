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


async def translate_prompt(
    prompt_cn: str,
    settings: Settings,
    style_tags: str = "",
    negative_prompt: str = "",
    nsfw_mode: bool = False,
    nsfw_visibility_level: str = "STANDARD",
) -> PromptResult:
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
        "Do not add extra composition-control tags unless the user requests them. "
        "If local prompt knowledge is provided, follow it exactly."
    )
    knowledge_context = matched_knowledge_context(prompt_cn, settings.prompt_knowledge_path)
    style_tag_instruction = (
        f"Preset/style tags to sanitize: {style_tags or '(none)'}. Keep identity, face, hair, "
        "body, pose, camera, lighting, and background tags. Remove full garments/outfits, but "
        "preserve NSFW remnants such as micro bikini, pasties, pulled-aside clothing, see-through wet, "
        "stockings only, garter. Remove censorship, covering, foreground-obstruction, and cropped tags."
        if nsfw_mode
        else f"Extra style tags to keep in English if useful: {style_tags or '(none)'}"
    )
    user_prompt = (
        f"Chinese request: {prompt_cn}\n"
        f"{style_tag_instruction}\n"
        f"Existing negative prompt to translate/merge if useful: {negative_prompt or '(none)'}\n"
        f"NSFW compatibility mode: {'enabled' if nsfw_mode else 'disabled'}\n"
        f"{knowledge_context or 'Local prompt knowledge matched: (none)'}\n"
        "Return the final JSON now."
    )
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
        if contains_cjk(positive):
            positive = remove_cjk_tags(positive)
        if nsfw_mode:
            positive = filter_nsfw_incompatible_tags(positive)
            positive = apply_nsfw_visibility_profile(positive, nsfw_visibility_level)
        if not positive:
            raise PromptTranslationError("Ollama could not produce usable English positive tags.")
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
            style_notes=normalize_prompt_value(parsed.get("style_notes", "")) or f"Translated by local Ollama model {settings.ollama_model}.",
            used_ollama=True,
        )
    except PromptTranslationError:
        raise
    except Exception as exc:
        raise PromptTranslationError(f"Ollama prompt translation failed: {exc}") from exc
