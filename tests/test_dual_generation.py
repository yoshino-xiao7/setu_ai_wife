from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import Settings
from app.main import (GenerateRequest, build_character_layout_hint, build_positive_prompt, build_regional_global_positive, build_regional_positive_prompts,
                      run_generation, should_use_dual_mask_conditioning, should_use_dual_regions)


class DualGenerationTest(unittest.IsolatedAsyncioTestCase):
    async def test_auto_with_painted_positions_keeps_one_global_sampler(self):
        mask = json.dumps({"strokes": [
            {"role": "primary", "points": [{"x": 0.5, "y": 0.25}], "brush": 0.4},
            {"role": "secondary", "points": [{"x": 0.5, "y": 0.75}], "brush": 0.4},
        ]})
        hint = build_character_layout_hint(mask)
        self.assertIn("above", hint)
        self.assertNotIn("left", hint)
        with tempfile.TemporaryDirectory() as directory:
            job = dict(id="test", generation_mode="DUAL", character_mask_json=mask,
                       prompt_positive="two adults hugging, " + hint, prompt_negative="low quality",
                       regional_left_positive="first person", regional_right_positive="second person",
                       seed=1, width=1024, height=768, steps=24, cfg=4.5, checkpoint="test.safetensors",
                       lora_name="", lora_strength=0, second_lora_name="", second_lora_strength=0)
            store = MagicMock()
            store.get_job.return_value = job
            with patch("app.main.JobStore", return_value=store), patch("app.main.queue_and_download", new_callable=AsyncMock) as run:
                run.return_value = Path(directory) / "test.png"
                await run_generation("test", Settings(DUAL_CHARACTER_STRATEGY="auto", OUTPUT_DIR=directory))
            graph = run.call_args.args[3]
            self.assertEqual(graph["6"]["inputs"]["text"], job["prompt_positive"])
            self.assertFalse(any(n["class_type"] in ("ConditioningSetArea", "ConditioningSetMask") for n in graph.values()))
            self.assertEqual(graph["3"]["inputs"]["positive"], ["6", 0])

    def test_interaction_prompt_has_no_automatic_left_right_assignment(self):
        payload = GenerateRequest(prompt_cn="two adults hugging", generation_mode="DUAL")
        first = SimpleNamespace(trigger_words="red hair", default_positive="blue eyes", style_tags="")
        second = SimpleNamespace(trigger_words="black hair", default_positive="green eyes", style_tags="")
        prompt = build_positive_prompt(payload, "two adults hugging face to face", first, second, True)
        self.assertTrue(prompt.startswith("two adults hugging face to face"))
        self.assertIn("red hair", prompt)
        self.assertIn("green eyes", prompt)
        self.assertIn("one continuous scene", prompt)
        self.assertNotIn("left", prompt)
        self.assertNotIn("right", prompt)
        explicit = build_positive_prompt(payload, "red haired woman on the left", first, second, True)
        self.assertIn("on the left", explicit)
        legacy = build_positive_prompt(
            payload, "two adults hugging, two distinct characters, left and right characters, no fusion, no mixed features",
            first, second, True)
        self.assertIn("two adults hugging", legacy)
        self.assertNotIn("left and right characters", legacy)
        self.assertNotIn("no fusion", legacy)

    def test_mask_prompts_keep_identity_regional_and_omit_layout_labels(self):
        payload = GenerateRequest(prompt_cn="two adults", generation_mode="DUAL")
        first = SimpleNamespace(trigger_words="red hair", default_positive="blue eyes", style_tags="")
        second = SimpleNamespace(trigger_words="black hair", default_positive="green eyes", style_tags="")
        scene = "two adults in a park, red hair, black hair"
        global_prompt = build_regional_global_positive(
            payload, scene, first, second, True, True, "character A position: left")
        left, right = build_regional_positive_prompts(payload, scene, first, second, True, True)
        self.assertIn("two adults in a park", global_prompt)
        for text in ("red hair", "black hair", "character A position"):
            self.assertNotIn(text, global_prompt)
        self.assertIn("red hair", left)
        self.assertNotIn("black hair", left)
        self.assertIn("green eyes", right)
        self.assertNotIn("blue eyes", right)

    async def test_explicit_area_mode_connects_regions_to_sampler(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(DUAL_CHARACTER_STRATEGY="regional-area", OUTPUT_DIR=directory)
            job = dict(
                id="test", generation_mode="DUAL", prompt_positive="mixed identities",
                prompt_negative="low quality", regional_global_positive="two adults in a park",
                regional_left_positive="red hair, blue jacket",
                regional_right_positive="black hair, green jacket",
                seed=1, width=1024, height=768, steps=28, cfg=4.5,
                checkpoint="test.safetensors", lora_name="", lora_strength=0,
                second_lora_name="", second_lora_strength=0,
            )
            store = MagicMock()
            store.get_job.return_value = job
            client = MagicMock()
            client.queue_prompt = AsyncMock(return_value="prompt")
            client.wait_for_history = AsyncMock(return_value={})
            client.download_first_image = AsyncMock(return_value=Path(directory) / "test.png")
            with patch("app.main.JobStore", return_value=store), patch("app.main.ComfyUIClient", return_value=client):
                await run_generation("test", settings)
            graph = client.queue_prompt.call_args.args[0]
            self.assertEqual(graph["6"]["inputs"]["text"], job["regional_global_positive"])
            self.assertEqual(graph["12"]["inputs"]["text"], job["regional_left_positive"])
            self.assertEqual(graph["13"]["inputs"]["text"], job["regional_right_positive"])
            self.assertEqual(graph["3"]["inputs"]["positive"], ["17", 0])
            store.update_job.assert_any_call("test", status="completed", image_path="test.png")

    def test_region_routing_preserves_single_and_legacy_modes(self):
        job = dict(generation_mode="DUAL", regional_left_positive="A", regional_right_positive="B")
        for strategy in ("auto", "mask-conditioning"):
            settings = Settings(DUAL_CHARACTER_STRATEGY=strategy)
            self.assertFalse(should_use_dual_regions(settings, job))
            self.assertFalse(should_use_dual_mask_conditioning(settings, job))
            self.assertFalse(should_use_dual_mask_conditioning(settings, {**job, "character_mask_json": "{}"}))
            mask = json.dumps({"strokes": [{"role": role, "points": [{"x": x, "y": 0.5}], "brush": 0.3} for role, x in [("primary", 0.25), ("secondary", 0.75)]]})
            self.assertEqual(should_use_dual_mask_conditioning(settings, {**job, "character_mask_json": mask}), strategy == "mask-conditioning")
            self.assertFalse(should_use_dual_regions(settings, {**job, "generation_mode": "SINGLE"}))
            self.assertFalse(should_use_dual_regions(settings, {**job, "regional_right_positive": ""}))
        for strategy in ("inpaint", "single-pass"):
            self.assertFalse(should_use_dual_regions(Settings(DUAL_CHARACTER_STRATEGY=strategy), job))
