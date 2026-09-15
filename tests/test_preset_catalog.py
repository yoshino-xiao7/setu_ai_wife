from __future__ import annotations

import json
import unittest
from collections import defaultdict
from pathlib import Path

from app.cloud_worker import scan_capabilities
from app.config import Settings
from app.main import GenerateRequest, build_positive_prompt, character_tags
from app.presets import (
    load_characters,
    load_checkpoint_metadata,
    load_lora_metadata,
    load_prompt_presets,
    list_loras,
)

ROOT = Path(__file__).resolve().parents[1]
PRESETS_PATH = ROOT / "config" / "prompt_presets.json"
CHARACTERS_PATH = ROOT / "config" / "characters.json"
LORA_PATH = ROOT / "config" / "lora_metadata.json"
CHECKPOINT_PATH = ROOT / "config" / "checkpoint_metadata.json"

WAI = "waiIllustriousSDXL_v170.safetensors"
ANI = "animagine-xl-4.0-opt.safetensors"

CATALOG_CHECKPOINTS = {WAI, ANI}


def _variant_rank(checkpoint: str) -> int:
    return {WAI: 0, ANI: 1}.get(checkpoint, 0)


class PresetCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            CHARACTERS_PATH=str(CHARACTERS_PATH),
            LORA_METADATA_PATH=str(LORA_PATH),
            CHECKPOINT_METADATA_PATH=str(CHECKPOINT_PATH),
            PROMPT_PRESETS_PATH=str(PRESETS_PATH),
            COMFYUI_MODELS_DIR=str(ROOT / "tools" / "ComfyUI_windows_portable" / "ComfyUI" / "models"),
        )
        self.raw_presets = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        self.presets = load_prompt_presets(PRESETS_PATH)
        self.characters = load_characters(CHARACTERS_PATH)
        self.lora_metadata = load_lora_metadata(LORA_PATH)
        self.checkpoint_metadata = load_checkpoint_metadata(CHECKPOINT_PATH)

    def test_real_loaders_accept_shipped_json(self) -> None:
        self.assertGreaterEqual(len(self.presets), 300)
        self.assertGreaterEqual(len(self.characters), 30)
        self.assertGreaterEqual(len(self.lora_metadata), 13)
        ids = [item.id for item in self.presets]
        self.assertEqual(len(ids), len(set(ids)))
        char_ids = [item.id for item in self.characters]
        self.assertEqual(len(char_ids), len(set(char_ids)))

    def test_each_installed_checkpoint_has_dedicated_style_presets(self) -> None:
        by_checkpoint: dict[str, list[str]] = defaultdict(list)
        for preset in self.presets:
            by_checkpoint[preset.recommended_checkpoint].append(preset.id)
        for checkpoint in CATALOG_CHECKPOINTS:
            self.assertGreaterEqual(
                len(by_checkpoint[checkpoint]),
                8,
                f"{checkpoint} needs dedicated style presets, got {by_checkpoint[checkpoint]}",
            )
        self.assertEqual(set(by_checkpoint) & {"hassakuXLPony_v13BetterEyesVersion.safetensors", "kohaku-xl-zeta.safetensors", "NoobAI-XL-v1.1.safetensors"}, set())
        self.assertIn("sfw_quality_baseline", by_checkpoint[WAI])
        self.assertIn("sfw_animagine_quality", by_checkpoint[ANI])

    def test_prompt_presets_follow_organization_rules(self) -> None:
        meta = self.raw_presets["_meta"]["organization_rules"]
        sfw_order = meta["sfw_order"]
        nsfw_order = meta["nsfw_order"]
        raw_items = self.raw_presets["prompt_presets"]

        sfw_types: list[str] = []
        nsfw_types: list[str] = []
        for item in raw_items:
            bucket = sfw_types if item["category"] == "SFW" else nsfw_types
            if not bucket or bucket[-1] != item["category_type"]:
                bucket.append(item["category_type"])
        self.assertEqual(sfw_types, sfw_order)
        self.assertEqual(nsfw_types, nsfw_order)

        grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
        for item in raw_items:
            grouped[(item["category"], item["category_type"])].append(
                _variant_rank(item["recommended_checkpoint"])
            )
        for key, ranks in grouped.items():
            self.assertEqual(ranks, sorted(ranks), f"model variants out of order in {key}")

    def test_recommended_loras_point_at_installed_files(self) -> None:
        lora_dir = self.settings.comfyui_models_dir / "loras"
        installed = {path.name for path in lora_dir.iterdir() if path.is_file()}
        referenced = {preset.recommended_lora for preset in self.presets if preset.recommended_lora}
        self.assertGreaterEqual(len(referenced), 4)
        missing = referenced - installed
        self.assertFalse(missing, f"presets recommend missing LoRAs: {missing}")

    def test_list_loras_exposes_new_style_loras_with_metadata(self) -> None:
        listed = list_loras(self.settings)
        by_name = {item["name"]: item for item in listed}
        for filename in (
            "watercolor.safetensors",
            "oil painting.safetensors",
            "cinematic lighting with moody ambiance.safetensors",
            "anime.safetensors",
            "90s anime.safetensors",
            "ani4.0-opt-pvc_00009e_065205s.safetensors",
        ):
            self.assertIn(filename, by_name)
            metadata_json = by_name[filename]["metadataJson"]
            self.assertTrue(metadata_json)
            payload = json.loads(metadata_json)
            self.assertEqual(payload["name"], filename)
            self.assertTrue(payload["display_name"])
            self.assertTrue(payload["trigger_words"] or filename.endswith("face-detailer-lora.safetensors"))

    def test_native_character_tags_enter_shipped_prompt_builder(self) -> None:
        hutao = next(item for item in self.characters if item.id == "hu_tao")
        self.assertEqual(hutao.lora_name, "")
        self.assertIn("hu tao (genshin impact)", hutao.trigger_words)
        tags = character_tags(hutao)
        self.assertIn("hu tao (genshin impact)", tags)
        self.assertIn("flower-shaped pupils", tags)

        payload = GenerateRequest(prompt_cn="雨夜街道", prompt_positive="rainy night street, modest coat")
        prompt = build_positive_prompt(payload, payload.prompt_positive, hutao, None, False)
        self.assertIn("hu tao (genshin impact)", prompt)
        self.assertIn("rainy night street", prompt)
        self.assertIn("twintails", prompt)
        self.assertNotIn("chinese clothes", prompt)

        changli = next(item for item in self.characters if item.id == "changli")
        dual = GenerateRequest(
            prompt_cn="拥抱",
            prompt_positive="two girls hugging, cozy room",
            generation_mode="DUAL",
        )
        dual_prompt = build_positive_prompt(dual, dual.prompt_positive, hutao, changli, True)
        self.assertIn("first character:", dual_prompt)
        self.assertIn("hu tao (genshin impact)", dual_prompt)
        self.assertIn("changli (wuthering waves)", dual_prompt)
        self.assertIn("2girls", dual_prompt)

    def test_character_presets_keep_identity_and_drop_outfits(self) -> None:
        yae = next(item for item in self.characters if item.id == "yae_miko")
        tags = character_tags(yae)
        self.assertIn("yae miko", tags)
        self.assertIn("fox ears", tags)
        self.assertIn("pink hair", tags)
        self.assertNotIn("japanese clothes", tags)
        self.assertNotIn("nontraditional miko", tags)
        self.assertNotIn("large breasts", tags)
        self.assertNotIn("anime style", tags)
        self.assertEqual(yae.style_tags, "")

        payload = GenerateRequest(
            prompt_cn="水光皮肤 回眸 比基尼",
            prompt_positive=(
                "shimmering body, yae miko, japanese clothes, nontraditional miko, "
                "bikini, beach setting, happy expression"
            ),
        )
        prompt = build_positive_prompt(payload, payload.prompt_positive, yae, None, False)
        self.assertIn("fox ears", prompt)
        self.assertIn("bikini", prompt)
        self.assertNotIn("japanese clothes", prompt)
        self.assertNotIn("nontraditional miko", prompt)

    def test_sd15_character_loras_are_not_wired_to_wai_presets(self) -> None:
        yae = next(item for item in self.characters if item.id == "yae_miko")
        raiden = next(item for item in self.characters if item.id == "raiden_shogun")
        lynette = next(item for item in self.characters if item.id == "lynette")
        self.assertNotEqual(yae.lora_name, "yae_miko_offset_9_6.safetensors")
        self.assertNotEqual(raiden.lora_name, "RaidenShogun-HandsFix.safetensors")
        self.assertEqual(lynette.lora_name, "")
        self.assertEqual(self.lora_metadata["yae_miko_offset_9_6.safetensors"].recommended_checkpoint, "")
        self.assertEqual(self.lora_metadata["RaidenShogun-HandsFix.safetensors"].recommended_checkpoint, "")
        self.assertEqual(self.lora_metadata["Genshin_Lynette_AP_v1.safetensors"].recommended_checkpoint, "")
        lora_dir = self.settings.comfyui_models_dir / "loras"
        self.assertTrue((lora_dir / "yae_miko_offset_9_6.safetensors").exists())
        self.assertTrue((lora_dir / "RaidenShogun-HandsFix.safetensors").exists())
        if (lora_dir / "yae_miko_illustrious.safetensors").exists():
            self.assertEqual(yae.lora_name, "yae_miko_illustrious.safetensors")
            self.assertIn("waiIllustriousSDXL_v170.safetensors", yae.recommended_checkpoints)
            self.assertIn("animagine-xl-4.0-opt.safetensors", yae.recommended_checkpoints)

    def test_scan_capabilities_includes_new_catalog_entries(self) -> None:
        capabilities = scan_capabilities(self.settings)
        character_names = {item["name"] for item in capabilities["characters"]}
        preset_names = {item["name"] for item in capabilities["promptPresets"]}
        lora_names = {item["name"] for item in capabilities["loras"]}
        self.assertIn("hu_tao", character_names)
        self.assertIn("changli", character_names)
        self.assertIn("ellen_joe", character_names)
        self.assertIn("kafka", character_names)
        self.assertNotIn("sfw_kohaku_cinematic_nl", preset_names)
        self.assertNotIn("sfw_noob_cinematic", preset_names)
        self.assertIn("sfw_animagine_quality", preset_names)
        self.assertIn("sfw_watercolor_illustration", preset_names)
        self.assertIn("watercolor.safetensors", lora_names)
        hutao_meta = json.loads(next(item["metadataJson"] for item in capabilities["characters"] if item["name"] == "hu_tao"))
        self.assertEqual(hutao_meta["name"], "胡桃")
        anima_meta = json.loads(
            next(item["metadataJson"] for item in capabilities["promptPresets"] if item["name"] == "sfw_animagine_quality")
        )
        self.assertEqual(anima_meta["recommended_checkpoint"], ANI)
        checkpoint_names = {item["name"] for item in capabilities["checkpoints"]}
        self.assertIn(WAI, checkpoint_names)
        self.assertIn(ANI, checkpoint_names)
        self.assertNotIn("hassakuXLPony_v13BetterEyesVersion.safetensors", checkpoint_names)
        self.assertNotIn("kohaku-xl-zeta.safetensors", checkpoint_names)
        self.assertNotIn("NoobAI-XL-v1.1.safetensors", checkpoint_names)

    def test_prompt_presets_use_short_tags_instead_of_prose(self) -> None:
        forbidden = (
            "beautiful girl",
            "cute girl",
            "excellent composition",
            "refined atmosphere",
            "modest clothing",
            "modest outfit",
        )
        for preset in self.presets:
            blob = " ".join(
                (
                    preset.trigger_words,
                    preset.default_positive,
                    preset.style_tags,
                )
            ).lower()
            for phrase in forbidden:
                self.assertNotIn(
                    phrase,
                    blob,
                    f"{preset.id} still contains prose {phrase!r}",
                )
            for field_name, value in (
                ("trigger_words", preset.trigger_words),
                ("default_positive", preset.default_positive),
            ):
                for clause in [part.strip() for part in value.split(",") if part.strip()]:
                    self.assertLessEqual(
                        len(clause.split()),
                        8,
                        f"{preset.id} {field_name} still has a long clause: {clause}",
                    )

    def test_over_shoulder_preset_does_not_ban_looking_at_viewer(self) -> None:
        lookback = next(item for item in self.presets if item.id == "sfw_over_shoulder")
        self.assertIn("looking back over shoulder", lookback.trigger_words)
        self.assertNotIn("looking at viewer", lookback.default_negative)

    def test_pastel_prone_lookback_preset_is_grouped_with_composition(self) -> None:
        ids = [item.id for item in self.presets]
        self.assertIn("sfw_pastel_prone_lookback", ids)
        self.assertEqual(ids.index("sfw_pastel_prone_lookback"), ids.index("sfw_over_shoulder") + 1)
        preset = next(item for item in self.presets if item.id == "sfw_pastel_prone_lookback")
        self.assertEqual(preset.category_type, "构图")
        self.assertIn("lying on stomach", preset.trigger_words)
        self.assertIn("white off-shoulder backless dress", preset.default_positive)
        self.assertIn("glossy skin", preset.style_tags)
        self.assertIn("open mouth", preset.default_negative)
        self.assertNotIn("looking at viewer", preset.default_negative)


if __name__ == "__main__":
    unittest.main()
