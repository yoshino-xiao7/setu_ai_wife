from __future__ import annotations

import re

QUALITY_NEGATIVE = (
    "low quality, worst quality, bad anatomy, bad hands, extra fingers, "
    "missing fingers, deformed, blurry, text, watermark, logo, cropped"
)

QUALITY_POSITIVE = "masterpiece, best quality, highres"

GAZE_AT_VIEWER_TAGS = {
    "looking at viewer",
    "eye contact",
    "facing camera",
    "direct gaze",
    "staring at viewer",
    "front view",
    "head facing forward",
    "facing the viewer",
    "looking straight at camera",
    "facing viewer",
    "staring at camera",
}

LOOKING_BACK_TAGS = {
    "looking back",
    "looking back over shoulder",
    "over shoulder",
    "over the shoulder",
}

LOOKING_AWAY_TAGS = {
    "looking away",
    "looking down",
    "looking to the side",
    "from behind",
    "back view",
    "profile",
    "side profile",
    "turned head",
    "gaze to the side",
    "not looking at camera",
}

FLUFF_CLAUSES = {
    "excellent composition and lighting",
    "excellent composition",
    "refined atmosphere",
    "fresh modern feel",
    "intellectual warm atmosphere",
    "intimate and engaging composition with eye contact to viewer",
    "graceful composition with focus on back and hair",
    "strong artistic composition focusing on facial silhouette and eyes",
    "beautiful sense of motion and life in the composition",
    "beautiful full body composition with soft bokeh background",
    "creates intimate yet detached artistic feel",
    "creates tension and movement in the frame",
    "empowering yet modest composition",
    "natural and stylish composition",
    "fresh and lively composition",
    "strong emotional composition with beautiful light",
}

SUBJECT_PREFIXES = (
    "an intimate nude upper body portrait of a beautiful adult woman",
    "a gentle watercolor illustration of a young woman",
    "a beautiful adult woman",
    "beautiful adult woman",
    "a beautiful young woman",
    "a beautiful woman",
    "a beautiful anime girl",
    "beautiful anime girl",
    "a beautiful girl",
    "beautiful girl",
    "a cute anime character",
    "cute anime character",
    "a cute anime girl",
    "cute anime girl",
    "an anime girl",
    "anime girl",
    "a cute girl",
    "cute girl",
    "a young woman",
    "young woman",
    "adult woman",
    "the girl",
    "girl",
)

PHRASE_REPLACEMENTS = (
    ("looking back over her shoulder", "looking back over shoulder"),

    ("head and gaze turned away from the camera", "looking away"),
    ("looking to the side or down or into the distance", "looking away"),
    ("looking slightly to the side or at viewer", "looking to the side"),
    ("not looking toward camera", "looking away"),
    ("not facing viewer", "looking away"),
    ("head turned away from camera", "looking away"),
    ("sitting elegantly on a chair or bench", "sitting, chair"),
    ("sitting naturally on stairs or stone steps", "sitting on stairs"),
    ("sitting naturally on the floor with legs tucked or to the side", "sitting on floor, legs to the side"),
    ("sitting naturally on the floor", "sitting on floor"),
    ("lying on her stomach on the bed", "lying on stomach, on bed"),
    ("lying on her stomach", "lying on stomach"),
    ("lying on her back", "lying on back"),
    ("lying on her side", "lying on side"),
    ("sleeping on her back on bed", "sleeping, lying on back, on bed"),
    ("sleeping on her side on bed", "sleeping, lying on side, on bed"),
    ("sleeping face down on bed", "sleeping, lying on stomach, on bed"),
    ("sleeping on her back", "sleeping, lying on back"),
    ("sleeping on her side", "sleeping, lying on side"),
    ("sleeping face down", "sleeping, lying on stomach"),
    ("looking down at her phone", "looking at phone, looking down"),
    ("looking down at his phone", "looking at phone, looking down"),
    ("one leg slightly bent", "one knee bent"),
    ("legs together modestly", "legs together"),
    ("legs positioned modestly", "legs together"),
    ("knees bent and legs slightly apart (not clamped)", "knees bent, legs apart"),
    ("knees bent and legs slightly apart", "knees bent, legs apart"),
    ("legs spread in v shape", "spread legs"),
    ("legs slightly parted (not pressed together)", "legs apart"),
    ("the top leg lifted and bent", "one knee up"),
    ("top leg lifted over", "one knee up"),
    ("one leg raised and bent", "one knee up"),
    ("one leg raised", "one knee up"),
    ("ass slightly raised", "ass up"),
    ("panties pulled down to mid-thigh with fabric bunched around her thighs", "panties around thighs"),
    ("the image shows her with her panties pulled down to mid-thigh with fabric bunched around her thighs", "panties around thighs"),
    ("the panties have been pulled down by an unseen hand from behind", "panties pulled down, from behind"),
    ("panties being pulled down to mid-thigh by unseen hand", "panties around thighs"),
    ("she is stirring slightly as if about to wake", "half-closed eyes"),
    ("soft smile", "light smile, closed mouth"),
    ("gentle or playful expression", "calm expression, closed mouth"),
    ("bright or soft expression", "light smile, closed mouth"),
    ("gentle focused expression", "calm expression, closed mouth"),
    ("soft distant expression", "calm expression, looking away, closed mouth"),
    ("peaceful expression", "calm expression, closed mouth"),
    ("soft expression", "calm expression, closed mouth"),
    ("gentle expression", "calm expression, closed mouth"),
    ("relaxed natural expression", "calm expression, closed mouth"),
    ("completely nude", "nude"),
    ("fully nude", "nude"),
    ("full nudity", "nude"),
    ("body completely nude", "nude"),
    ("while completely nude", "nude"),
    ("while nude", "nude"),

    ("hair and clothes moving slightly", "wind lift"),
    ("hair flowing", "flowing hair"),
    ("long flowing hair", "long hair, flowing hair"),
    ("oversized cozy knit sweater", "oversized sweater"),
    ("oversized cozy sweater", "oversized sweater"),
    ("an oversized t-shirt", "oversized t-shirt"),

)

FLUFF_WORD_RE = re.compile(
    r"\b(?:beautiful|cute|pretty|gorgeous|stunning|modest|excellent|refined|"
    r"naturally|casually|quietly|slightly|gently|just)\b",
    re.IGNORECASE,
)
ARTICLE_RE = re.compile(r"\b(?:a|an|the|her|his|their|she|he|him)\b", re.IGNORECASE)
PREP_SPLIT_RE = re.compile(
    r"\b(?:in|on|with|while|into|under|through|across|during|against|among|beside|inside|by)\b",
    re.IGNORECASE,
)
LEADING_PREP_RE = re.compile(r"^(?:with|and|or|as)\s+", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")
GENERIC_DROP = {
    "clothing",
    "clothes",
    "outfit",
    "image shows",
    "optional",
    "natural pose",
    "soft natural pose",
    "natural relaxed posture",
    "natural relaxed sleeping pose",
    "state is halfway undressed",
    "only panties are affected",
    "clean clothing",
    "viewed from behind",
    "coverage",
    "adorable",
}
STYLE_KEEP_RE = re.compile(
    r"lighting|skin|shadow|eyes|hair|fabric|watercolor|oil|cinematic|golden|"
    r"neon|ink|anime|pvc|wet|glossy|luminosity|ambient|volumetric|film|90s|"
    r"cel|newest|absurdres|dynamic|profile|perspective|angle|highres|"
    r"masterpiece|best quality|detailed|painterly|moody|rim",
    re.IGNORECASE,
)
STOP_TAGS = {
    "",
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "to",
    "for",
    "as",
    "it",
    "its",
    "be",
    "being",
    "only",
    "very",
    "more",
    "than",
    "way",
    "feel",
    "mood",
    "moment",
    "view",
    "focus",
    "sense",
}

EXPRESSION_POSITIVE_HINTS = ("closed mouth", "calm expression", "light smile", "slight blush")
EXPRESSION_NEGATIVE_LOCKS = ("winking", "open mouth", "grin")
ANATOMY_NEGATIVE = ("bad hands", "extra limbs", "deformed")


def split_clauses(value: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for char in value or "":
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            part = "".join(buf).strip(" ,")
            if part:
                parts.append(part)
            buf = []
            continue
        buf.append(char)
    part = "".join(buf).strip(" ,")
    if part:
        parts.append(part)
    return parts


def join_tags(tags: list[str]) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for tag in tags:
        cleaned = SPACE_RE.sub(" ", (tag or "").strip(" ,."))
        key = cleaned.lower()
        if not cleaned or key in seen or key in STOP_TAGS:
            continue
        seen.add(key)
        ordered.append(cleaned)
    return ", ".join(ordered)


def tag_keys(value: str) -> set[str]:
    return {item.lower() for item in split_clauses(value)}


def subtract_tags(value: str, *others: str) -> str:
    remove = set()
    for other in others:
        remove.update(tag_keys(other))
    return join_tags([tag for tag in split_clauses(value) if tag.lower() not in remove])


def _strip_subject_prefix(text: str) -> str:
    lowered = text.lower()
    for prefix in SUBJECT_PREFIXES:
        token = prefix + " "
        if lowered.startswith(token):
            return text[len(token):].strip()
    return text


def _apply_phrase_replacements(text: str) -> str:
    lowered = text.lower()
    for source, target in PHRASE_REPLACEMENTS:
        if source == target.lower():
            continue
        index = lowered.find(source)
        if index < 0:
            continue
        text = text[:index] + target + text[index + len(source):]
        lowered = text.lower()
    return text


def _drop_parenthetical_choices(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        first = re.split(r"\s*(?:,|/| or )\s*", inner, maxsplit=1)[0].strip()
        return first

    return re.sub(r"\(([^)]*)\)", replace, text)


def _take_first_alternative(text: str) -> str:
    if " or " not in text.lower() or len(text.split()) > 6:
        return text
    parts = re.split(r"\s+or\s+", text, maxsplit=1, flags=re.IGNORECASE)
    left = parts[0].strip()
    if 0 < len(left.split()) <= 4:
        return left
    return text


def _clean_short_clause(text: str) -> str:
    text = FLUFF_WORD_RE.sub(" ", text)
    text = ARTICLE_RE.sub(" ", text)
    text = text.replace("'s", "")
    text = SPACE_RE.sub(" ", text).strip(" -")
    return text


def clause_to_tags(clause: str) -> list[str]:
    text = SPACE_RE.sub(" ", (clause or "").strip(" ,."))
    if not text:
        return []
    lowered = text.lower().strip(" .")
    if lowered in FLUFF_CLAUSES:
        return []
    if "composition" in lowered and "dutch" not in lowered:
        return []
    if lowered.endswith(" atmosphere") or lowered.endswith(" feel") or lowered.endswith(" moment"):
        return []
    text = re.sub(r"\bcomposition\b", " ", text, flags=re.IGNORECASE)
    text = SPACE_RE.sub(" ", text).strip()
    if not text:
        return []

    text = _drop_parenthetical_choices(text)
    text = _apply_phrase_replacements(text)
    if "," in text:
        tags: list[str] = []
        for part in split_clauses(text):
            tags.extend(clause_to_tags(part))
        return tags

    text = _strip_subject_prefix(text)
    text = _take_first_alternative(text)
    text = _apply_phrase_replacements(text)
    if "," in text:
        tags = []
        for part in split_clauses(text):
            tags.extend(clause_to_tags(part))
        return tags

    words = text.split()
    if len(words) <= 6:
        cleaned = _finalize_tag(text)
        return [cleaned] if cleaned else []

    tags = []
    for part in PREP_SPLIT_RE.split(text):
        cleaned = _finalize_tag(part)
        if cleaned and len(cleaned.split()) <= 6:
            tags.append(cleaned)
    return tags


def _finalize_tag(text: str) -> str:
    text = _take_first_alternative(text)
    text = LEADING_PREP_RE.sub("", text).strip()
    text = _clean_short_clause(text)
    lowered = text.lower()
    if not text or lowered in STOP_TAGS or lowered in GENERIC_DROP:
        return ""
    if lowered.endswith((" moment", " atmosphere", " composition", " optional")):
        return ""
    return text


def rewrite_positive_tags(value: str) -> str:
    tags: list[str] = []
    for clause in split_clauses(value):
        tags.extend(clause_to_tags(clause))
    return join_tags(tags)


def rewrite_style_tags(value: str) -> str:
    kept: list[str] = []
    for tag in split_clauses(value):
        if STYLE_KEEP_RE.search(tag):
            kept.append(tag)
    merged = join_tags([*split_clauses(QUALITY_POSITIVE), *kept])
    return merged or QUALITY_POSITIVE


def _has_any(keys: set[str], candidates: set[str] | tuple[str, ...]) -> bool:
    for item in candidates:
        for key in keys:
            if key == item or key.startswith(item + " ") or key.endswith(" " + item):
                return True
    return False


def rewrite_negative_tags(value: str, positive: str = "") -> str:
    tags = split_clauses(value)
    positive_keys = tag_keys(positive)
    wants_viewer = _has_any(positive_keys, LOOKING_BACK_TAGS | {"looking at viewer"})
    wants_away = _has_any(positive_keys, LOOKING_AWAY_TAGS) and not wants_viewer

    cleaned: list[str] = []
    for tag in tags:
        key = tag.lower()
        if wants_viewer and key in GAZE_AT_VIEWER_TAGS:
            continue
        cleaned.append(tag)

    if not any(tag.lower().startswith("score_") for tag in cleaned):
        cleaned = [*split_clauses(QUALITY_NEGATIVE), *cleaned]
    else:
        for extra in ("bad hands", "extra limbs"):
            if extra not in {item.lower() for item in cleaned}:
                cleaned.append(extra)

    if _has_any(positive_keys, EXPRESSION_POSITIVE_HINTS):
        cleaned.extend(EXPRESSION_NEGATIVE_LOCKS)
    if wants_away:
        cleaned.extend(["looking at viewer", "eye contact", "facing camera"])

    return join_tags(cleaned)


TRY_ON_KEYS = {
    "trying on clothes",
    "changing clothes",
    "half undressed",
    "half-dressed",
    "putting on clothes",
    "undressing",
}
MIRROR_KEYS = {
    "mirror",
    "full-length mirror",
    "reflection",
    "looking at reflection",
    "looking at own reflection",
}
NUDE_KEYS = {
    "nude",
    "naked",
    "completely nude",
    "fully nude",
    "standing in front of mirror nude",
}
OUTDOOR_LOCATION_KEYS = {
    "beach",
    "beach setting",
    "ocean",
    "pool",
    "outdoor",
    "summer",
}
SMILE_OR_PLAYFUL_KEYS = {
    "happy expression",
    "playful pose",
    "light smile",
    "smile",
    "smiling",
}
CALM_OR_CLOSED_KEYS = {
    "calm expression",
    "closed mouth",
    "relaxed expression",
}
STACK_JUNK_KEYS = {
    "coverage",
    "in adorable bikini",
    "different clothes",
    "currently half undressed",
    "front of mirror trying",
}


def _stack_keys(value: str) -> set[str]:
    return {_key(tag) for tag in split_clauses(value)}


def _key(tag: str) -> str:
    return " ".join((tag or "").lower().replace("_", " ").split())


def _has_key(keys: set[str], candidates: set[str]) -> bool:
    for item in candidates:
        for key in keys:
            if key == item or item in key:
                return True
    return False


def _has_bikini(keys: set[str]) -> bool:
    return any("bikini" in key or key == "two piece swimsuit" or key == "two-piece swimsuit" for key in keys)


SCENE_CATEGORY_TYPES = {
    "场景",
    "浴室",
    "镜子",
}
GARMENT_CATEGORY_TYPES = {
    "泳装",
    "制服",
    "内衣",
    "家居服",
    "礼服",
    "哥特风",
    "传统服饰",
    "运动",
    "日常",
    "服饰",
    "服装",
}
SCENE_CLOTHING_TOKENS = {
    "dress",
    "sundress",
    "skirt",
    "bikini",
    "swimsuit",
    "kimono",
    "uniform",
    "clothes",
    "clothing",
    "outfit",
    "coat",
    "jacket",
    "shirt",
    "blouse",
    "sweater",
    "hoodie",
    "pantyhose",
    "thighhighs",
    "boots",
    "shoes",
    "veil",
    "hat",
    "hanfu",
    "maid",
    "nude",
    "naked",
}
GARMENT_LOCATION_TOKENS = {
    "beach",
    "ocean",
    "pool",
    "garden",
    "park",
    "street",
    "classroom",
    "office",
    "kitchen",
    "bedroom",
    "bathroom",
    "shrine",
    "cafe",
    "forest",
    "city",
    "rooftop",
    "train",
    "field",
}
COMPETING_GARMENTS_IF_BIKINI = {
    "dress",
    "sundress",
    "kimono",
    "hanfu",
    "china dress",
    "school uniform",
    "casual clothes",
    "clothing",
    "outfit",
    "coat",
    "jacket",
    "blouse",
    "shirt",
    "sweater",
    "nude",
    "naked",
    "fully nude",
    "standing in front of mirror nude",
}


def _tag_tokens(tag: str) -> set[str]:
    return set(re.findall(r"[a-z0-9-]+", _key(tag)))


def strip_layer_tokens(value: str, drop_tokens: set[str]) -> str:
    kept: list[str] = []
    for tag in split_clauses(value):
        tokens = _tag_tokens(tag)
        key = _key(tag)
        if key in drop_tokens or tokens.intersection(drop_tokens):
            continue
        kept.append(tag)
    return join_tags(kept)


COMPOSITION_CLOTHING_KEEP_IDS = {"sfw_pastel_prone_lookback"}
COMPOSITION_EXPRESSION_KEEP_IDS = {"sfw_melancholy", "sfw_emotional_closeup"}
SCENE_EXPRESSION_KEYS = {
    "calm expression",
    "closed mouth",
    "happy expression",
    "playful pose",
    "relaxed expression",
    "peaceful smile",
    "gentle smile",
    "soft smile",
    "light smile",
    "smile",
    "smiling",
    "grin",
    "innocent expression",
}


def strip_layer_keys(value: str, drop_keys: set[str]) -> str:
    kept: list[str] = []
    for tag in split_clauses(value):
        key = _key(tag)
        if key in drop_keys or any(item in key for item in drop_keys):
            continue
        kept.append(tag)
    return join_tags(kept)


def sanitize_preset_layer(preset: dict) -> dict:
    updated = dict(preset)
    category = str(preset.get("category") or "")
    category_type = str(preset.get("category_type") or "")
    preset_id = str(preset.get("id") or "")
    if category == "SFW" and category_type in SCENE_CATEGORY_TYPES:
        updated["trigger_words"] = strip_layer_tokens(str(preset.get("trigger_words") or ""), SCENE_CLOTHING_TOKENS)
        updated["default_positive"] = strip_layer_tokens(str(preset.get("default_positive") or ""), SCENE_CLOTHING_TOKENS)
        updated["trigger_words"] = strip_layer_keys(updated["trigger_words"], SCENE_EXPRESSION_KEYS)
        updated["default_positive"] = strip_layer_keys(updated["default_positive"], SCENE_EXPRESSION_KEYS)
    if category == "SFW" and category_type == "构图":
        if preset_id not in COMPOSITION_CLOTHING_KEEP_IDS:
            updated["trigger_words"] = strip_layer_tokens(str(updated.get("trigger_words") or preset.get("trigger_words") or ""), SCENE_CLOTHING_TOKENS)
            updated["default_positive"] = strip_layer_tokens(str(updated.get("default_positive") or preset.get("default_positive") or ""), SCENE_CLOTHING_TOKENS)
        if preset_id not in COMPOSITION_EXPRESSION_KEEP_IDS:
            updated["trigger_words"] = strip_layer_keys(str(updated.get("trigger_words") or ""), SCENE_EXPRESSION_KEYS)
            updated["default_positive"] = strip_layer_keys(str(updated.get("default_positive") or ""), SCENE_EXPRESSION_KEYS)
    if category_type in GARMENT_CATEGORY_TYPES:
        updated["trigger_words"] = strip_layer_tokens(str(updated.get("trigger_words") or preset.get("trigger_words") or ""), GARMENT_LOCATION_TOKENS)
        updated["default_positive"] = strip_layer_tokens(str(updated.get("default_positive") or preset.get("default_positive") or ""), GARMENT_LOCATION_TOKENS)
    return updated


def compose_stacked_prompt(positive: str) -> str:
    tags = split_clauses(positive)
    keys = {_key(tag) for tag in tags}
    has_bikini = _has_bikini(keys)
    has_try_on = _has_key(keys, TRY_ON_KEYS)
    has_mirror = _has_key(keys, MIRROR_KEYS)
    has_garment = has_bikini or _has_key(
        keys,
        {"dress", "skirt", "swimsuit", "one piece swimsuit", "school swimsuit"},
    )
    drop = set(STACK_JUNK_KEYS)
    extras: list[str] = []

    if has_garment and has_try_on:
        drop.update(NUDE_KEYS)
        drop.update({"different clothes", "currently half undressed"})
        if has_bikini:
            extras.extend(["trying on bikini", "putting on bikini"])
    if has_mirror:
        extras.extend(
            [
                "matching reflection",
                "same pose in reflection",
                "same expression in reflection",
            ]
        )
        if has_garment or has_try_on:
            drop.update(NUDE_KEYS)
            drop.update(OUTDOOR_LOCATION_KEYS)
    if keys & SMILE_OR_PLAYFUL_KEYS and keys & CALM_OR_CLOSED_KEYS:
        drop.update(CALM_OR_CLOSED_KEYS)
    if has_bikini:
        drop.update(COMPETING_GARMENTS_IF_BIKINI)

    kept = [
        tag for tag in tags
        if _key(tag) not in drop and not any(item in _key(tag) for item in drop)
    ]
    return join_tags([*kept, *extras])


def compose_stacked_negative(negative: str, positive: str = "") -> str:
    tags = split_clauses(negative)
    keys = _stack_keys(positive)
    drop: set[str] = set()
    if _has_bikini(keys) or _has_key(keys, TRY_ON_KEYS):
        drop.update({"clothed", "fully clothed"})
    if keys & SMILE_OR_PLAYFUL_KEYS:
        drop.update({"smiling", "smile", "open mouth", "grin", "winking"})
    return join_tags([tag for tag in tags if _key(tag) not in drop])


def rewrite_preset_fields(preset: dict) -> dict:
    trigger = rewrite_positive_tags(str(preset.get("trigger_words") or ""))
    positive = subtract_tags(rewrite_positive_tags(str(preset.get("default_positive") or "")), trigger)
    style = rewrite_style_tags(str(preset.get("style_tags") or ""))
    style = subtract_tags(style, trigger, positive)
    negative = rewrite_negative_tags(str(preset.get("default_negative") or ""), join_tags([trigger, positive]))
    updated = dict(preset)
    updated["trigger_words"] = trigger
    updated["default_positive"] = positive
    updated["style_tags"] = style
    updated["default_negative"] = negative
    return updated
