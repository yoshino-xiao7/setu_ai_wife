from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.comfyui import build_anima_workflow, is_anima_checkpoint
from app.config import Settings
from app.presets import list_anima_models


class AnimaWorkflowTest(unittest.TestCase):
    def test_checkpoint_name_detects_anima_not_animagine(self) -> None:
        self.assertTrue(is_anima_checkpoint("anima-base-v1.0.safetensors"))
        self.assertTrue(is_anima_checkpoint("diffusion_models/anima-aesthetic-v1.1.safetensors"))
        self.assertFalse(is_anima_checkpoint("animagine-xl-4.0-opt.safetensors"))
        self.assertFalse(is_anima_checkpoint("waiIllustriousSDXL_v170.safetensors"))
        self.assertFalse(is_anima_checkpoint(""))

    def test_anima_graph_uses_qwen_nodes(self) -> None:
        workflow = build_anima_workflow(
            positive="1girl, solo",
            negative="low quality",
            seed=1,
            width=1024,
            height=1024,
            steps=30,
            cfg=4,
            unet_name="anima-base-v1.0.safetensors",
            clip_name="qwen_3_06b_base.safetensors",
            vae_name="qwen_image_vae.safetensors",
        )
        self.assertEqual(workflow["1"]["class_type"], "UNETLoader")
        self.assertEqual(workflow["2"]["inputs"]["type"], "qwen_image")
        self.assertEqual(workflow["7"]["inputs"]["sampler_name"], "er_sde")
        self.assertNotIn("10", workflow)

    def test_list_anima_models_only_reports_anima_unets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            models = Path(directory)
            unet_dir = models / "diffusion_models"
            unet_dir.mkdir()
            (unet_dir / "anima-base-v1.0.safetensors").write_bytes(b"x" * 32)
            (unet_dir / "other-unet.safetensors").write_bytes(b"x" * 32)
            settings = Settings(COMFYUI_MODELS_DIR=str(models))
            listed = list_anima_models(settings)
            self.assertEqual([item["name"] for item in listed], ["anima-base-v1.0.safetensors"])
            metadata = json.loads(listed[0]["metadataJson"])
            self.assertEqual(metadata["pipeline"], "anima")
