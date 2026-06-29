from __future__ import annotations

import unittest
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


if __name__ == "__main__":
    unittest.main()
