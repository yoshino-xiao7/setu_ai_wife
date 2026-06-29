from __future__ import annotations

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

        def handler(request: httpx.Request) -> httpx.Response:
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

        def handler(request: httpx.Request) -> httpx.Response:
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


if __name__ == "__main__":
    unittest.main()
