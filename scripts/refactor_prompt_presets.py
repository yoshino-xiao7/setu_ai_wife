from __future__ import annotations

import json
from pathlib import Path

from app.prompt_tags import rewrite_preset_fields

ROOT = Path(__file__).resolve().parents[1]
PRESETS_PATH = ROOT / "config" / "prompt_presets.json"

PASTEL_PRONE_LOOKBACK = {
    "id": "sfw_pastel_prone_lookback",
    "name": "粉彩趴姿回眸",
    "category": "SFW",
    "category_type": "构图",
    "trigger_words": (
        "1girl, solo, looking back over shoulder, lying on stomach, "
        "arched back, bent knees, soles of feet facing viewer"
    ),
    "style_tags": (
        "masterpiece, best quality, highres, glossy skin, wet skin, "
        "shimmering body, high luminosity, bright ambient light"
    ),
    "default_positive": (
        "closed mouth, slight blush, calm expression, white off-shoulder backless dress, "
        "light blue ribbon, white frilly bikini bottom, pastel color palette, "
        "white bedsheet background"
    ),
    "default_negative": (
        "low quality, worst quality, bad anatomy, bad hands, extra limbs, deformed feet, "
        "crooked spine, winking, open mouth, smiling, deep blue dress, dark clothing, "
        "heavy shadows, dark background, cluttered background, text, watermark"
    ),
    "recommended_checkpoint": "waiIllustriousSDXL_v170.safetensors",
    "recommended_lora": "",
    "recommended_lora_strength": 0.0,
    "nsfw_only": False,
    "notes": "高光粉彩趴姿回眸。表情、色板和关节姿势都在正负面双向锁定。",
}


def main() -> None:
    payload = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    presets = [rewrite_preset_fields(item) for item in payload["prompt_presets"]]
    ids = [item["id"] for item in presets]
    if PASTEL_PRONE_LOOKBACK["id"] not in ids:
        insert_at = next(
            (index + 1 for index, item in enumerate(presets) if item["id"] == "sfw_over_shoulder"),
            None,
        )
        if insert_at is None:
            raise SystemExit("sfw_over_shoulder is missing; cannot insert the lookback preset.")
        presets.insert(insert_at, PASTEL_PRONE_LOOKBACK)
    payload["prompt_presets"] = presets
    meta = payload.get("_meta")
    if isinstance(meta, dict):
        meta["version"] = "2026-09-14"
    PRESETS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"rewrote {len(presets)} presets")


if __name__ == "__main__":
    main()
