from __future__ import annotations

import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app.cloud_worker import CloudCompletionDeliveryError, CloudWorker
from app.config import Settings


class CloudWorkerCompletionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.worker = CloudWorker(
            Settings(
                CLOUD_API_URL="https://cloud.example.test",
                AI_WORKER_TOKEN="token",
                AI_WORKER_ID="worker-1",
            )
        )

    async def test_complete_retries_server_error_then_succeeds(self) -> None:
        statuses = iter((500, 200))

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(next(statuses), request=request, text="result")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("app.cloud_worker.asyncio.sleep", new=AsyncMock()) as sleep:
                await self.worker._complete_cloud_job(
                    client,
                    82,
                    "local-82",
                    "comfy-82",
                    {},
                    b"image",
                    "82.png",
                )

        sleep.assert_awaited_once_with(1.0)

    async def test_complete_does_not_retry_client_error(self) -> None:
        requests = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal requests
            requests += 1
            return httpx.Response(400, request=request, text="invalid")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(RuntimeError, "HTTP 400"):
                await self.worker._complete_cloud_job(
                    client,
                    82,
                    "local-82",
                    "comfy-82",
                    {},
                    b"image",
                    "82.png",
                )

        self.assertEqual(requests, 1)

    async def test_complete_preserves_retryable_failure_classification(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, request=request, text="deadlock")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("app.cloud_worker.asyncio.sleep", new=AsyncMock()):
                with self.assertRaisesRegex(CloudCompletionDeliveryError, "after 5 attempts"):
                    await self.worker._complete_cloud_job(
                        client,
                        82,
                        "local-82",
                        "comfy-82",
                        {},
                        b"image",
                        "82.png",
                    )

    async def test_local_delete_only_removes_file_inside_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            worker = CloudWorker(
                Settings(
                    CLOUD_API_URL="https://cloud.example.test",
                    AI_WORKER_TOKEN="token",
                    AI_WORKER_ID="worker-1",
                    OUTPUT_DIR=temporary,
                )
            )
            image = Path(temporary) / "7" / "2026-06-30" / "local.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"image")
            requested_paths: list[str] = []

            def handler(request: httpx.Request) -> httpx.Response:
                requested_paths.append(request.url.path)
                return httpx.Response(200, request=request, json={"status": "SUCCEEDED"})

            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                await worker._process_local_image_delete(
                    client,
                    {"id": 9, "localRelativePath": "7/2026-06-30/local.png"},
                )

            self.assertFalse(image.exists())
            self.assertEqual(requested_paths, ["/ai-worker/local-image-deletions/9/complete"])

    async def test_queue_notice_posts_message_to_qq_bot(self) -> None:
        worker = CloudWorker(
            Settings(
                CLOUD_API_URL="https://cloud.example.test",
                AI_WORKER_TOKEN="token",
                AI_WORKER_ID="worker-1",
                QQ_BOT_SEND_MESSAGE_URL="https://bot.example.test/send-message",
                QQ_BOT_TOKEN="bot-token",
            )
        )
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, request=request, json={"ok": True})

        bot_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("app.cloud_worker.httpx.AsyncClient", return_value=bot_client) as async_client_factory:
            await worker._send_qq_queue_notice(
                {"id": 82, "userId": 7, "qqNumber": "123456", "promptCn": "画一张图"},
                "local-82",
            )

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url.path, "/send-message")
        self.assertEqual(async_client_factory.call_args.kwargs["headers"]["Authorization"], "Bearer bot-token")
        payload = json.loads(requests[0].content.decode("utf-8"))
        self.assertEqual(payload["type"], "message")
        self.assertEqual(payload["qq"], "123456")
        self.assertEqual(payload["jobId"], 82)
        self.assertEqual(payload["localJobId"], "local-82")
        self.assertIn("已进入本机队列", payload["message"])

    def test_output_path_rejects_directory_traversal(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "escapes OUTPUT_DIR"):
            self.worker._resolve_output_path("../outside.png")


if __name__ == "__main__":
    unittest.main()
