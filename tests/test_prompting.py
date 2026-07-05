from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

import httpx

from app.config import Settings
from app.prompting import translate_prompt


class PromptingTest(unittest.IsolatedAsyncioTestCase):
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
        )

        with patch("app.prompting.httpx.AsyncClient", side_effect=clients):
            result = await translate_prompt("银发成年女性，雨夜", settings)

        self.assertEqual(result.positive, "adult woman, silver hair, rainy night")
        self.assertEqual(result.style_notes, "corrected")
        self.assertEqual([payload["options"]["num_gpu"] for payload in payloads], [1, 1])

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
        )

        with patch("app.prompting.httpx.AsyncClient", side_effect=clients):
            result = await translate_prompt("银发成年女性，雨夜", settings)

        self.assertEqual(result.positive, "adult woman, rainy night")
        self.assertEqual(result.style_notes, "initial")
        self.assertEqual([payload["options"]["num_gpu"] for payload in payloads], [1, 1])

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

    async def test_grok2api_and_ollama_race_uses_faster_result(self) -> None:
        async def slow_ollama_handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0.05)
            return httpx.Response(
                200,
                request=request,
                json={
                    "response": json.dumps(
                        {
                            "positive": "slow local result",
                            "negative": "low quality",
                            "style_notes": "ollama",
                        }
                    )
                },
            )

        async def fast_grok_handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            self.assertEqual(payload["model"], "grok-4.20-0309-non-reasoning")
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "positive": "fast grok result",
                                        "negative": "low quality",
                                        "style_notes": "grok",
                                    }
                                )
                            }
                        }
                    ]
                },
            )

        clients = [
            httpx.AsyncClient(transport=httpx.MockTransport(slow_ollama_handler)),
            httpx.AsyncClient(transport=httpx.MockTransport(fast_grok_handler)),
        ]
        settings = Settings(
            OLLAMA_URL="http://ollama.test",
            OLLAMA_MODEL="qwen3:4b",
            GROK2API_URL="http://grok.test/v1",
            GROK2API_API_KEY="test-key",
            GROK2API_MODEL="grok-4.20-0309-non-reasoning",
        )

        with patch("app.prompting.httpx.AsyncClient", side_effect=clients):
            result = await translate_prompt("银发成年女性，雨夜", settings)

        self.assertEqual(result.positive, "fast grok result")
        self.assertFalse(result.used_ollama)

    async def test_prompt_race_waits_for_ollama_when_grok2api_fails_first(self) -> None:
        def ollama_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                request=request,
                json={
                    "response": json.dumps(
                        {
                            "positive": "local fallback result",
                            "negative": "low quality",
                            "style_notes": "ollama",
                        }
                    )
                },
            )

        def grok_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, request=request, json={"error": "upstream failed"})

        clients = [
            httpx.AsyncClient(transport=httpx.MockTransport(ollama_handler)),
            httpx.AsyncClient(transport=httpx.MockTransport(grok_handler)),
        ]
        settings = Settings(
            OLLAMA_URL="http://ollama.test",
            OLLAMA_MODEL="qwen3:4b",
            GROK2API_URL="http://grok.test/v1",
            GROK2API_API_KEY="test-key",
        )

        with patch("app.prompting.httpx.AsyncClient", side_effect=clients):
            result = await translate_prompt("银发成年女性，雨夜", settings)

        self.assertEqual(result.positive, "local fallback result")
        self.assertTrue(result.used_ollama)

    async def test_grok2api_can_run_without_api_key(self) -> None:
        seen_headers: list[httpx.Headers] = []

        async def slow_ollama_handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0.05)
            return httpx.Response(
                200,
                request=request,
                json={
                    "response": json.dumps(
                        {
                            "positive": "slow local result",
                            "negative": "low quality",
                            "style_notes": "ollama",
                        }
                    )
                },
            )

        def grok_handler(request: httpx.Request) -> httpx.Response:
            seen_headers.append(request.headers)
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "positive": "grok no auth result",
                                        "negative": "low quality",
                                        "style_notes": "grok",
                                    }
                                )
                            }
                        }
                    ]
                },
            )

        clients = [
            httpx.AsyncClient(transport=httpx.MockTransport(slow_ollama_handler)),
            httpx.AsyncClient(transport=httpx.MockTransport(grok_handler)),
        ]
        settings = Settings(
            OLLAMA_URL="http://ollama.test",
            OLLAMA_MODEL="qwen3:4b",
            GROK2API_URL="http://grok.test/v1",
            GROK2API_API_KEY="",
        )

        with patch("app.prompting.httpx.AsyncClient", side_effect=clients):
            result = await translate_prompt("银发成年女性，雨夜", settings)

        self.assertEqual(result.positive, "grok no auth result")
        self.assertNotIn("authorization", seen_headers[0])


if __name__ == "__main__":
    unittest.main()
