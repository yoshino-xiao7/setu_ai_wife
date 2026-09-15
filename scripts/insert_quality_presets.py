from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRESETS_PATH = ROOT / "config" / "prompt_presets.json"
WAI = "waiIllustriousSDXL_v170.safetensors"
ANI = "animagine-xl-4.0-opt.safetensors"
QNEG = (
    "low quality, worst quality, bad anatomy, bad hands, extra fingers, missing fingers, "
    "deformed, blurry, text, watermark, logo, cropped, lowres, jpeg artifacts, chromatic aberration"
)


def quality_preset(**kwargs) -> dict:
    base = {
        "style_tags": "masterpiece, best quality, highres",
        "default_positive": "",
        "default_negative": QNEG,
        "recommended_checkpoint": WAI,
        "recommended_lora": "",
        "recommended_lora_strength": 0.0,
        "nsfw_only": False,
        "category": "SFW",
        "category_type": "构图",
    }
    base.update(kwargs)
    return base


NEW_PRESETS = {
    "sfw_watercolor_illustration": [
        quality_preset(
            id="sfw_quality_baseline",
            name="画质基线",
            trigger_words="masterpiece, best quality, highres, absurdres",
            style_tags="masterpiece, best quality, highres, absurdres",
            default_positive="sharp focus, intricate details",
            notes="质量层：通用画质基线。可和任意场景/衣服叠用，不含人物、地点、表情。",
        ),
        quality_preset(
            id="sfw_quality_eyes_hair",
            name="五官发丝细节",
            trigger_words="detailed eyes, detailed face, detailed hair",
            style_tags="masterpiece, best quality, highres, detailed eyes",
            default_positive="finely detailed eyelashes, individual hair strands",
            default_negative=QNEG + ", extra pupils, asymmetrical eyes, messy hair",
            notes="质量层：眼睛、脸、头发细节。不锁表情、不改构图。",
        ),
        quality_preset(
            id="sfw_quality_skin",
            name="皮肤质感",
            trigger_words="detailed skin, skin texture",
            style_tags="masterpiece, best quality, highres, detailed skin",
            default_positive="smooth skin, subtle skin pores",
            notes="质量层：皮肤质感。和水光皮肤可叠，本身不加水光。",
        ),
        quality_preset(
            id="sfw_quality_fabric",
            name="布料纹理",
            trigger_words="detailed fabric, fabric texture",
            style_tags="masterpiece, best quality, highres, detailed fabric",
            default_positive="fabric folds, textile weave",
            notes="质量层：衣服布料纹理。只加强材质，不指定穿什么。",
        ),
        quality_preset(
            id="sfw_quality_lineart",
            name="干净线稿",
            trigger_words="clean lineart, sharp lines",
            style_tags="masterpiece, best quality, highres",
            default_positive="precise linework, clean edges",
            default_negative=QNEG + ", sketch, messy lines, broken lineart",
            notes="质量层：干净线稿和边缘。适合二次元插画。",
        ),
        quality_preset(
            id="sfw_quality_lighting",
            name="立体光照",
            trigger_words="beautiful lighting, rim light",
            style_tags="masterpiece, best quality, highres, beautiful lighting",
            default_positive="volumetric lighting, soft shadows, depth",
            default_negative=QNEG + ", flat lighting, overexposed, underexposed",
            notes="质量层：立体光和体积光。不指定场景，可和电影光影、窗边侧光叠用。",
        ),
        quality_preset(
            id="sfw_quality_detail_lora",
            name="细节滑杆",
            trigger_words="extremely detailed",
            style_tags="masterpiece, best quality, highres, extremely detailed",
            recommended_lora="extremely detailed.safetensors",
            recommended_lora_strength=0.45,
            default_negative=QNEG + ", oversharpened, dirty details",
            notes="质量层：细节滑杆 LoRA。不锁半身，全身和场景也能用。建议强度 0.35-0.55。",
        ),
        quality_preset(
            id="sfw_quality_face_lora",
            name="脸部细化",
            trigger_words="detailed face, detailed eyes",
            style_tags="masterpiece, best quality, highres, detailed face",
            recommended_lora="sdxl-pdxl-tuning-face-detailer-lora.safetensors",
            recommended_lora_strength=0.4,
            default_negative=QNEG + ", extra pupils, asymmetrical eyes, plastic skin",
            notes="质量层：脸部细化 LoRA。不强制特写，半身全身都能叠。建议强度 0.25-0.5。",
        ),
    ],
    "sfw_animagine_low_angle": [
        quality_preset(
            id="sfw_animagine_quality",
            name="Anima 画质",
            trigger_words="masterpiece, best quality, newest, absurdres, amazing",
            style_tags="masterpiece, best quality, highres, newest, absurdres",
            default_positive="very aesthetic, highres",
            recommended_checkpoint=ANI,
            notes="质量层：Anima / Animagine XL 质量词。newest/absurdres/amazing，不含人物和场景。",
        ),
    ],
}


def main() -> None:
    payload = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    presets = payload["prompt_presets"]
    ids = {item["id"] for item in presets}
    for before_id, items in NEW_PRESETS.items():
        insert_at = next(i for i, item in enumerate(presets) if item["id"] == before_id)
        for offset, item in enumerate(items):
            if item["id"] in ids:
                continue
            presets.insert(insert_at + offset, item)
            ids.add(item["id"])
    payload["prompt_presets"] = presets
    PRESETS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("presets", len(presets))


if __name__ == "__main__":
    main()
