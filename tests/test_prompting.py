from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

import httpx

from app.config import Settings
from app.prompting import (
    DEFAULT_NEGATIVE,
    PromptTranslationError,
    build_translation_prompts,
    finalize_prompt_result,
    translate_prompt,
)


class PromptingTest(unittest.IsolatedAsyncioTestCase):
    async def test_total_deadline_cancels_ollama(self) -> None:
        stopped = []
        async def slow_provider(*args, **kwargs):
            try:
                await asyncio.sleep(10)
            finally:
                stopped.append(True)
        settings = Settings(PROMPT_TRANSLATION_TOTAL_TIMEOUT_SECONDS=0.02)
        with patch("app.prompting.translate_prompt_with_ollama", side_effect=slow_provider):
            with self.assertRaisesRegex(PromptTranslationError, "total timeout"):
                await translate_prompt("雨夜", settings)
        self.assertEqual(len(stopped), 1)

    async def test_retries_chinese_positive_as_english_json(self) -> None:
        responses = iter(
            (
                {
                    "response": json.dumps(
                        {
                            "positive": "成年女性, 银发, rainy night",
                            "negative": "low quality",
                            "style_notes": "initial",
                        }
                    )
                },
                {
                    "response": "",
                    "thinking": json.dumps(
                        {
                            "positive": "adult woman, silver hair, rainy night",
                            "negative": "low quality",
                            "style_notes": "corrected",
                        }
                    )
                },
            )
        )
        payloads: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payloads.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, request=request, json=next(responses))

        clients = [
            httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ]
        settings = Settings(
            OLLAMA_URL="http://ollama.test",
            OLLAMA_MODEL="qwen3:4b",
            OLLAMA_PROMPT_NUM_GPU=-1,
        )

        with patch("app.prompting.httpx.AsyncClient", side_effect=clients):
            result = await translate_prompt("银发成年女性，雨夜", settings)

        self.assertEqual(result.positive, "adult woman, silver hair, rainy night")
        self.assertEqual(result.style_notes, "corrected")
        self.assertEqual([payload["options"]["num_gpu"] for payload in payloads], [-1, -1])
        self.assertTrue(all(payload["think"] is False for payload in payloads))
        self.assertTrue(all(payload["keep_alive"] == 0 for payload in payloads))

    async def test_malformed_correction_keeps_usable_english_tags(self) -> None:
        responses = iter(
            (
                {
                    "response": json.dumps(
                        {
                            "positive": "adult woman, 银发, rainy night",
                            "negative": "low quality",
                            "style_notes": "initial",
                        }
                    )
                },
                {"response": "not valid json"},
            )
        )
        payloads: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payloads.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, request=request, json=next(responses))

        clients = [
            httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ]
        settings = Settings(
            OLLAMA_URL="http://ollama.test",
            OLLAMA_MODEL="qwen3:4b",
            OLLAMA_PROMPT_NUM_GPU=-1,
        )

        with patch("app.prompting.httpx.AsyncClient", side_effect=clients):
            result = await translate_prompt("银发成年女性，雨夜", settings)

        self.assertEqual(result.positive, "adult woman, rainy night")
        self.assertEqual(result.style_notes, "initial")
        self.assertEqual([payload["options"]["num_gpu"] for payload in payloads], [-1, -1])

    async def test_prompt_translation_can_be_configured_to_use_gpu(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            self.assertEqual(payload["options"]["num_gpu"], 1)
            return httpx.Response(
                200,
                request=request,
                json={
                    "response": json.dumps(
                        {
                            "positive": "adult woman, silver hair, rainy night",
                            "negative": "low quality",
                            "style_notes": "configured",
                        }
                    )
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        settings = Settings(
            OLLAMA_URL="http://ollama.test",
            OLLAMA_MODEL="qwen3:4b",
            OLLAMA_PROMPT_NUM_GPU=1,
        )

        with patch("app.prompting.httpx.AsyncClient", return_value=client):
            result = await translate_prompt("silver hair adult woman, rainy night", settings)

        self.assertEqual(result.positive, "adult woman, silver hair, rainy night")

    async def test_style_tags_are_not_sent_to_ollama_context(self) -> None:
        payloads: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            payloads.append(payload)
            return httpx.Response(
                200,
                request=request,
                json={
                    "response": json.dumps(
                        {
                            "positive": "adult woman, rainy night",
                            "negative": "low quality",
                            "style_notes": "translated",
                        }
                    )
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        settings = Settings(
            OLLAMA_URL="http://ollama.test",
            OLLAMA_MODEL="qwen3:4b",
        )

        with patch("app.prompting.httpx.AsyncClient", return_value=client):
            await translate_prompt(
                "adult woman in rainy night",
                settings,
                style_tags="masterpiece, best quality, very long preset tag list",
            )

        self.assertEqual(len(payloads), 1)
        self.assertNotIn("very long preset tag list", payloads[0]["prompt"])

    def test_default_negative_is_quality_only(self) -> None:
        self.assertIn("bad anatomy", DEFAULT_NEGATIVE)
        self.assertNotIn("looking at viewer", DEFAULT_NEGATIVE)
        self.assertNotIn("eye contact", DEFAULT_NEGATIVE)

    def test_translation_prompt_asks_for_danbooru_layers(self) -> None:
        settings = Settings()
        system_prompt, _user_prompt = build_translation_prompts("回眸趴在床上", settings, "", False)
        self.assertIn("Danbooru", system_prompt)
        self.assertIn("one expression", system_prompt)
        self.assertIn("looking back", system_prompt)
        self.assertNotIn("Add 'not looking at viewer'", system_prompt)

    def test_finalize_injects_lookback_and_glossy_skin_knowledge(self) -> None:
        from pathlib import Path

        knowledge_path = Path(__file__).resolve().parents[1] / "config" / "prompt_knowledge.json"
        result = finalize_prompt_result(
            {
                "positive": "bikini, two piece swimsuit, in adorable bikini, beach setting, happy expression, coverage",
                "negative": "low quality, looking at viewer",
                "style_notes": "ok",
            },
            negative_prompt="",
            nsfw_mode=False,
            nsfw_visibility_level="STANDARD",
            provider="ollama",
            model="qwen3:4b",
            used_ollama=True,
            prompt_cn="八重神子 水光皮肤 回眸 可爱比基尼 沙滩",
            knowledge_path=knowledge_path,
        )
        self.assertIn("looking back over shoulder", result.positive)
        self.assertNotIn("closed mouth", result.positive)
        self.assertIn("glossy skin", result.positive)
        self.assertIn("wet skin", result.positive)
        self.assertIn("shimmering body", result.positive)
        self.assertIn("bikini", result.positive)
        self.assertIn("happy expression", result.positive)
        self.assertNotIn("coverage", result.positive)
        self.assertNotIn("looking at viewer", result.negative)
        self.assertNotIn("open mouth", result.negative)
        self.assertNotIn("smiling", result.negative)

    def test_lookback_smile_keeps_smile_and_drops_closed_mouth(self) -> None:
        from pathlib import Path

        knowledge_path = Path(__file__).resolve().parents[1] / "config" / "prompt_knowledge.json"
        result = finalize_prompt_result(
            {
                "positive": "bikini, closed mouth, calm expression",
                "negative": "low quality, smiling, open mouth, looking at viewer",
                "style_notes": "ok",
            },
            negative_prompt="",
            nsfw_mode=False,
            nsfw_visibility_level="STANDARD",
            provider="ollama",
            model="qwen3:4b",
            used_ollama=True,
            prompt_cn="八重神子 回眸一笑",
            knowledge_path=knowledge_path,
        )
        self.assertIn("looking back over shoulder", result.positive)
        self.assertIn("light smile", result.positive)
        self.assertNotIn("closed mouth", result.positive)
        self.assertNotIn("calm expression", result.positive)
        self.assertNotIn("smiling", result.negative)
        self.assertNotIn("open mouth", result.negative)
        self.assertNotIn("looking at viewer", result.negative)

    def test_finalize_does_not_inject_gaze_lock(self) -> None:
        result = finalize_prompt_result(
            {
                "positive": "1girl, looking back over shoulder, closed mouth",
                "negative": "low quality",
                "style_notes": "ok",
            },
            negative_prompt="",
            nsfw_mode=False,
            nsfw_visibility_level="STANDARD",
            provider="ollama",
            model="qwen3:4b",
            used_ollama=True,
        )
        self.assertEqual(result.positive, "1girl, looking back over shoulder, closed mouth")
        self.assertNotIn("looking at viewer", result.negative)


if __name__ == "__main__":
    unittest.main()
