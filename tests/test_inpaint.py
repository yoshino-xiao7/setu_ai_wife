from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.comfyui import (
    INPAINT_BLEND_DENOISE,
    INPAINT_REDRAW_DENOISE,
    build_brushnet_inpaint_workflow,
    build_inpaint_workflow,
    build_redraw_inpaint_workflow,
)
from app.config import Settings
from app.main import (
    composite_inpaint_crop,
    create_manual_inpaint_mask,
    inpaint_crop_box,
    inpaint_negative_prompt,
    inpaint_positive_prompt,
    inpaint_profile,
    select_brushnet_model,
    select_fooocus_inpaint_models,
    should_use_brushnet_inpaint,
    should_use_redraw_inpaint,
)


class InpaintTest(unittest.TestCase):
    def test_manual_mask_rasterizes_normalized_stroke(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.png"
            create_manual_inpaint_mask(
                path,
                100,
                200,
                json.dumps({
                    "strokes": [{
                        "brush": 0.1,
                        "points": [{"x": 0.5, "y": 0.5}, {"x": 0.6, "y": 0.5}],
                    }],
                }),
            )

            with Image.open(path) as mask:
                self.assertGreater(mask.convert("L").getpixel((50, 100)), 0)
                self.assertEqual(mask.size, (100, 200))

    def test_manual_mask_expands_painted_line_into_soft_repair_region(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.png"
            create_manual_inpaint_mask(
                path,
                200,
                200,
                json.dumps({
                    "strokes": [{
                        "brush": 0.02,
                        "points": [{"x": 0.5, "y": 0.5}, {"x": 0.52, "y": 0.5}],
                    }],
                }),
            )

            with Image.open(path) as mask:
                pixels = mask.convert("L")
                self.assertGreater(pixels.getpixel((100, 100)), 0)
                self.assertGreater(pixels.getpixel((100, 112)), 0)

    def test_crop_box_expands_painted_area_and_aligns_to_model_grid(self) -> None:
        mask = Image.new("L", (512, 512), 0)
        for x in range(240, 272):
            for y in range(250, 266):
                mask.putpixel((x, y), 255)

        left, top, right, bottom = inpaint_crop_box(mask, 512, 512)

        self.assertLessEqual(left, 192)
        self.assertLessEqual(top, 202)
        self.assertGreaterEqual(right, 320)
        self.assertGreaterEqual(bottom, 314)
        self.assertEqual(left % 8, 0)
        self.assertEqual(top % 8, 0)
        self.assertEqual(right % 8, 0)
        self.assertEqual(bottom % 8, 0)

    def test_composite_inpaint_crop_only_changes_masked_area(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.png"
            mask_path = root / "mask.png"
            crop_path = root / "crop.png"
            output_path = root / "output.png"

            Image.new("RGB", (64, 64), (10, 20, 30)).save(source_path)
            mask = Image.new("L", (64, 64), 0)
            for x in range(28, 36):
                for y in range(28, 36):
                    mask.putpixel((x, y), 255)
            mask.save(mask_path)
            Image.new("RGB", (32, 32), (200, 40, 80)).save(crop_path)

            composite_inpaint_crop(
                source_path=source_path,
                mask_path=mask_path,
                repaired_crop_path=crop_path,
                crop_box=(16, 16, 48, 48),
                output_path=output_path,
            )

            with Image.open(output_path) as result:
                pixels = result.convert("RGB")
                self.assertEqual(pixels.getpixel((4, 4)), (10, 20, 30))
                self.assertNotEqual(pixels.getpixel((32, 32)), (10, 20, 30))

    def test_strong_profile_uses_more_denoise_and_mask_growth(self) -> None:
        self.assertEqual(inpaint_profile("LIGHT"), (0.42, 12))
        self.assertEqual(inpaint_profile("STRONG"), (0.62, 22))

    def test_inpaint_prompts_preserve_original_style_and_reject_brush_artifacts(self) -> None:
        self.assertIn("match original image style", inpaint_positive_prompt("yae miko"))
        self.assertIn("consistent lineart", inpaint_positive_prompt("yae miko"))
        self.assertIn("visible brush stroke", inpaint_negative_prompt("low quality"))
        self.assertIn("mismatched style", inpaint_negative_prompt("low quality"))

    def test_inpaint_workflow_chains_two_loras(self) -> None:
        workflow = build_inpaint_workflow(
            positive="positive",
            negative="negative",
            seed=1,
            steps=20,
            cfg=4,
            checkpoint="model.safetensors",
            sampler="euler",
            scheduler="normal",
            base_image="source.png",
            mask_image="mask.png",
            denoise=0.58,
            lora_name="a.safetensors",
            lora_strength=0.6,
            second_lora_name="b.safetensors",
            second_lora_strength=0.5,
            grow_mask_by=20,
        )

        self.assertEqual(workflow["3"]["inputs"]["model"], ["11", 0])
        self.assertEqual(workflow["11"]["inputs"]["model"], ["10", 0])
        self.assertEqual(workflow["5"]["inputs"]["grow_mask_by"], 20)

    def test_brushnet_workflow_uses_brushnet_node_and_chains_loras(self) -> None:
        workflow = build_brushnet_inpaint_workflow(
            positive="positive",
            negative="negative",
            seed=1,
            steps=20,
            cfg=4,
            checkpoint="model.safetensors",
            sampler="euler",
            scheduler="normal",
            base_image="source.png",
            mask_image="mask.png",
            denoise=0.52,
            brushnet_model="brushnet/random_mask.safetensors",
            lora_name="a.safetensors",
            lora_strength=0.6,
            second_lora_name="b.safetensors",
            second_lora_strength=0.5,
        )

        self.assertEqual(workflow["5"]["class_type"], "BrushNetLoader")
        self.assertEqual(workflow["12"]["class_type"], "BrushNet")
        self.assertEqual(workflow["12"]["inputs"]["model"], ["11", 0])
        self.assertEqual(workflow["3"]["inputs"]["latent_image"], ["12", 3])
        self.assertEqual(workflow["5"]["inputs"]["brushnet"], "brushnet/random_mask.safetensors")

    def test_selects_brushnet_model_and_falls_back_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            models_dir = Path(directory) / "models"
            inpaint_dir = models_dir / "inpaint" / "brushnet"
            inpaint_dir.mkdir(parents=True)
            (inpaint_dir / "random_mask.safetensors").write_bytes(b"fake")
            settings = Settings(COMFYUI_MODELS_DIR=models_dir)

            selected = select_brushnet_model(settings)

            self.assertEqual(selected, os.path.join("brushnet", "random_mask.safetensors"))
            self.assertTrue(should_use_redraw_inpaint(settings))
            self.assertTrue(should_use_brushnet_inpaint(settings, selected))
            legacy = Settings(COMFYUI_MODELS_DIR=models_dir, INPAINT_ENGINE="legacy")
            self.assertFalse(should_use_redraw_inpaint(legacy))
            self.assertFalse(should_use_brushnet_inpaint(legacy, selected))
            brushnet_only = Settings(COMFYUI_MODELS_DIR=models_dir, INPAINT_ENGINE="brushnet")
            self.assertFalse(should_use_redraw_inpaint(brushnet_only))
            self.assertTrue(should_use_brushnet_inpaint(brushnet_only, selected))

    def test_redraw_workflow_uses_full_image_differential_and_blend_pass(self) -> None:
        workflow = build_redraw_inpaint_workflow(
            positive="positive",
            negative="negative",
            seed=1,
            steps=20,
            cfg=4,
            checkpoint="model.safetensors",
            sampler="euler",
            scheduler="normal",
            base_image="source.png",
            mask_image="mask.png",
            grow_mask_by=16,
            lora_name="a.safetensors",
            lora_strength=0.6,
            second_lora_name="b.safetensors",
            second_lora_strength=0.5,
        )

        self.assertEqual(workflow["14"]["class_type"], "DifferentialDiffusion")
        self.assertEqual(workflow["15"]["class_type"], "InpaintModelConditioning")
        self.assertTrue(workflow["15"]["inputs"]["noise_mask"])
        self.assertEqual(workflow["15"]["inputs"]["pixels"], ["1", 0])
        self.assertEqual(workflow["15"]["inputs"]["mask"], ["13", 0])
        self.assertNotIn("23", workflow)
        self.assertEqual(workflow["3"]["inputs"]["denoise"], INPAINT_REDRAW_DENOISE)
        self.assertEqual(workflow["3"]["inputs"]["latent_image"], ["15", 2])
        self.assertEqual(workflow["14"]["inputs"]["model"], ["11", 0])
        self.assertEqual(workflow["20"]["inputs"]["denoise"], INPAINT_BLEND_DENOISE)
        self.assertEqual(workflow["9"]["inputs"]["images"], ["21", 0])

    def test_redraw_workflow_can_skip_blend_pass(self) -> None:
        workflow = build_redraw_inpaint_workflow(
            positive="positive",
            negative="negative",
            seed=1,
            steps=20,
            cfg=4,
            checkpoint="model.safetensors",
            sampler="euler",
            scheduler="normal",
            base_image="source.png",
            mask_image="mask.png",
            blend_denoise=0,
        )

        self.assertNotIn("20", workflow)
        self.assertEqual(workflow["9"]["inputs"]["images"], ["8", 0])

    def test_redraw_workflow_uses_fooocus_expand_blur_and_color_match(self) -> None:
        workflow = build_redraw_inpaint_workflow(
            positive="positive",
            negative="negative",
            seed=1,
            steps=20,
            cfg=4,
            checkpoint="model.safetensors",
            sampler="euler",
            scheduler="normal",
            base_image="source.png",
            mask_image="mask.png",
            fooocus_head="fooocus_inpaint_head.pth",
            fooocus_patch="inpaint_v26.fooocus.patch",
        )

        self.assertEqual(workflow["13"]["class_type"], "INPAINT_ExpandMask")
        self.assertEqual(workflow["13"]["inputs"]["blur_type"], "gaussian")
        self.assertEqual(workflow["25"]["class_type"], "INPAINT_LoadFooocusInpaint")
        self.assertEqual(workflow["26"]["class_type"], "INPAINT_ApplyFooocusInpaint")
        self.assertEqual(workflow["15"]["class_type"], "INPAINT_VAEEncodeInpaintConditioning")
        self.assertEqual(workflow["26"]["inputs"]["latent"], ["15", 2])
        self.assertEqual(workflow["3"]["inputs"]["latent_image"], ["15", 3])
        self.assertEqual(workflow["14"]["inputs"]["model"], ["26", 0])
        self.assertNotIn("20", workflow)
        self.assertEqual(workflow["27"]["class_type"], "INPAINT_ColorMatch")
        self.assertEqual(workflow["9"]["inputs"]["images"], ["27", 0])

    def test_selects_fooocus_models_and_skips_them_for_brushnet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            models_dir = Path(directory) / "models"
            inpaint_dir = models_dir / "inpaint"
            inpaint_dir.mkdir(parents=True)
            (inpaint_dir / "fooocus_inpaint_head.pth").write_bytes(b"head")
            (inpaint_dir / "inpaint_v26.fooocus.patch").write_bytes(b"patch")
            (inpaint_dir / "brushnet").mkdir()
            (inpaint_dir / "brushnet" / "random_mask.safetensors").write_bytes(b"fake")
            settings = Settings(COMFYUI_MODELS_DIR=models_dir)

            head, patch = select_fooocus_inpaint_models(settings)
            self.assertEqual(head, "")
            self.assertEqual(patch, "")
            explicit = Settings(
                COMFYUI_MODELS_DIR=models_dir,
                FOOOCUS_INPAINT_HEAD="fooocus_inpaint_head.pth",
                FOOOCUS_INPAINT_PATCH="inpaint_v26.fooocus.patch",
            )
            head, patch = select_fooocus_inpaint_models(explicit)
            self.assertEqual(head, "fooocus_inpaint_head.pth")
            self.assertEqual(patch, "inpaint_v26.fooocus.patch")
            self.assertEqual(
                select_brushnet_model(settings),
                os.path.join("brushnet", "random_mask.safetensors"),
            )

    def test_configured_brushnet_model_uses_runtime_path_separator(self) -> None:
        settings = Settings(BRUSHNET_MODEL="brushnet/random_mask.safetensors")

        selected = select_brushnet_model(settings)

        self.assertEqual(selected, os.path.join("brushnet", "random_mask.safetensors"))


if __name__ == "__main__":
    unittest.main()
