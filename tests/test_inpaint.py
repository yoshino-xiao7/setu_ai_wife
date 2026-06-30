from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.comfyui import build_inpaint_workflow
from app.main import (
    create_manual_inpaint_mask,
    inpaint_negative_prompt,
    inpaint_positive_prompt,
    inpaint_profile,
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

    def test_manual_mask_uses_block_region_instead_of_thin_line_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.png"
            create_manual_inpaint_mask(
                path,
                200,
                200,
                json.dumps({
                    "strokes": [{
                        "brush": 0.02,
                        "points": [{"x": 0.25, "y": 0.5}, {"x": 0.75, "y": 0.5}],
                    }],
                }),
            )

            with Image.open(path) as mask:
                pixels = mask.convert("L")
                self.assertGreater(pixels.getpixel((100, 82)), 0)
                self.assertGreater(pixels.getpixel((100, 118)), 0)

    def test_strong_profile_uses_more_denoise_and_mask_growth(self) -> None:
        self.assertEqual(inpaint_profile("LIGHT"), (0.38, 12))
        self.assertEqual(inpaint_profile("STRONG"), (0.58, 28))

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


if __name__ == "__main__":
    unittest.main()
