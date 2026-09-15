from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from app.cloud_worker import CloudWorker
from app.comfyui import (
    IMG2IMG_DEFAULT_DENOISE,
    build_anima_img2img_workflow,
    build_img2img_workflow,
    clamp_img2img_denoise,
)
from app.config import Settings
from app.db import JobStore
from app.main import app, get_settings, get_store, save_source_image, cleanup_source_image_file


ONE_PIXEL_PNG = (
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class Img2ImgWorkflowTest(unittest.TestCase):
    def test_workflow_encodes_scaled_source_without_inpaint_mask(self) -> None:
        workflow = build_img2img_workflow(
            positive="1girl, looking back",
            negative="low quality",
            seed=7,
            width=832,
            height=1216,
            steps=28,
            cfg=4.5,
            checkpoint="waiIllustriousSDXL_v170.safetensors",
            sampler="euler",
            scheduler="normal",
            source_image="source.png",
            denoise=0.45,
            lora_name="yae.safetensors",
            lora_strength=0.6,
        )
        self.assertEqual(workflow["1"]["class_type"], "LoadImage")
        self.assertEqual(workflow["2"]["class_type"], "ImageScale")
        self.assertEqual(workflow["2"]["inputs"]["width"], 832)
        self.assertEqual(workflow["2"]["inputs"]["height"], 1216)
        self.assertEqual(workflow["5"]["class_type"], "VAEEncode")
        self.assertEqual(workflow["5"]["inputs"]["pixels"], ["2", 0])
        self.assertEqual(workflow["3"]["inputs"]["denoise"], 0.45)
        self.assertEqual(workflow["3"]["inputs"]["latent_image"], ["5", 0])
        self.assertEqual(workflow["10"]["class_type"], "LoraLoader")
        self.assertNotIn("VAEEncodeForInpaint", [node["class_type"] for node in workflow.values()])

    def test_anima_workflow_uses_anima_vae_to_encode_source(self) -> None:
        workflow = build_anima_img2img_workflow(
            positive="1girl",
            negative="low quality",
            seed=1,
            width=768,
            height=1024,
            steps=30,
            cfg=4,
            unet_name="anima-unet.safetensors",
            clip_name="anima-clip.safetensors",
            vae_name="anima-vae.safetensors",
            source_image="source.png",
            denoise=0.35,
        )
        self.assertEqual(workflow["6"]["class_type"], "VAEEncode")
        self.assertEqual(workflow["6"]["inputs"]["vae"], ["3", 0])
        self.assertEqual(workflow["7"]["inputs"]["denoise"], 0.35)
        self.assertEqual(workflow["7"]["inputs"]["latent_image"], ["6", 0])
        self.assertEqual(workflow["11"]["inputs"]["width"], 768)

    def test_denoise_is_clamped_to_supported_range(self) -> None:
        self.assertEqual(clamp_img2img_denoise(None), IMG2IMG_DEFAULT_DENOISE)
        self.assertEqual(clamp_img2img_denoise(0.1), 0.25)
        self.assertEqual(clamp_img2img_denoise(0.9), 0.70)
        workflow = build_img2img_workflow(
            positive="1girl",
            negative="low quality",
            seed=1,
            width=768,
            height=1024,
            steps=28,
            cfg=4.5,
            checkpoint="wai.safetensors",
            sampler="euler",
            scheduler="normal",
            source_image="source.png",
            denoise=0.99,
        )
        self.assertEqual(workflow["3"]["inputs"]["denoise"], 0.70)


class Img2ImgLocalApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.settings = Settings(
            DATABASE_PATH=str(root / "jobs.sqlite3"),
            OUTPUT_DIR=str(root / "outputs"),
        )
        self.store = JobStore(self.settings.database_path)
        app.dependency_overrides[get_settings] = lambda: self.settings
        app.dependency_overrides[get_store] = lambda: self.store
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.tempdir.cleanup()

    def test_img2img_rejects_missing_source(self) -> None:
        response = self.client.post(
            "/api/generate",
            json={"prompt_cn": "银发少女", "job_type": "IMG2IMG"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("源图", response.json()["detail"])

    def test_img2img_rejects_dual_character(self) -> None:
        response = self.client.post(
            "/api/generate",
            json={
                "prompt_cn": "银发少女",
                "job_type": "IMG2IMG",
                "generation_mode": "DUAL",
                "source_image_base64": ONE_PIXEL_PNG.decode("ascii"),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("双角色", response.json()["detail"])

    def test_save_source_image_accepts_data_url(self) -> None:
        encoded = "data:image/png;base64," + ONE_PIXEL_PNG.decode("ascii")
        path = Path(save_source_image(encoded, "job-1", self.settings))
        self.assertTrue(path.exists())
        with Image.open(path) as image:
            self.assertEqual(image.size, (1, 1))

    def test_cleanup_source_image_file_removes_saved_png(self) -> None:
        path = Path(save_source_image(ONE_PIXEL_PNG.decode("ascii"), "job-2", self.settings))
        self.assertTrue(path.exists())
        cleanup_source_image_file({"source_image_path": str(path)})
        self.assertFalse(path.exists())
        cleanup_source_image_file({"source_image_path": ""})


class Img2ImgCloudWorkerTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_local_generation_attaches_downloaded_source(self) -> None:
        worker = CloudWorker(
            Settings(
                CLOUD_API_URL="https://cloud.example.test",
                AI_WORKER_TOKEN="token",
                AI_WORKER_ID="worker-1",
                LOCAL_AI_URL="http://127.0.0.1:7861",
            )
        )
        with patch.object(
            worker,
            "_download_source_image_base64",
            new=AsyncMock(return_value=ONE_PIXEL_PNG.decode("ascii")),
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                return_value=httpx.Response(
                    200,
                    request=httpx.Request("POST", "http://127.0.0.1:7861/api/generate"),
                    json={"job_id": "local-1"},
                )
            )
            with patch("app.cloud_worker.httpx.AsyncClient") as client_cls:
                client_cls.return_value.__aenter__.return_value = mock_client
                result = await worker._start_local_generation(
                    {
                        "id": 82,
                        "promptCn": "银发少女",
                        "jobType": "IMG2IMG",
                        "denoise": 0.45,
                        "width": 832,
                        "height": 1216,
                    },
                    img2img_source_url="https://oss.example.test/source.png",
                )

        self.assertEqual(result["job_id"], "local-1")
        posted = mock_client.post.await_args.kwargs.get("json") or mock_client.post.await_args.args[1]
        if posted is None:
            posted = mock_client.post.await_args.kwargs["json"]
        self.assertEqual(posted["job_type"], "IMG2IMG")
        self.assertEqual(posted["source_image_base64"], ONE_PIXEL_PNG.decode("ascii"))
        self.assertEqual(posted["denoise"], 0.45)
        self.assertFalse(posted["light_hires"])


if __name__ == "__main__":
    unittest.main()
