import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from fastapi import HTTPException
from app import control_service


class ControlHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_running_monitor_is_healthy(self):
        monitor = asyncio.create_task(asyncio.sleep(60))
        try:
            with patch.dict(control_service._background_tasks, {"autoRecovery": monitor}, clear=True):
                self.assertEqual((await control_service.health())["tasks"], {"autoRecovery": True})
        finally:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)

    async def test_dead_monitor_triggers_service_recovery(self):
        monitor = asyncio.create_task(asyncio.sleep(0))
        await monitor
        with patch.dict(control_service._background_tasks, {"autoRecovery": monitor}, clear=True):
            with self.assertRaises(HTTPException) as error:
                await control_service.health()
            self.assertEqual(error.exception.status_code, 503)

    async def test_unexpected_stack_exit_starts_recovery(self):
        settings = SimpleNamespace(auto_recover_enabled=True, auto_recover_interval_seconds=30,
                                   auto_recover_cooldown_seconds=120)
        action = AsyncMock(return_value={"running": True})
        with patch.object(control_service, "get_settings", return_value=settings), \
             patch.object(control_service, "_auto_recovery_paused", False), \
             patch.object(control_service, "_stack_status", AsyncMock(return_value={"running": False})), \
             patch.object(control_service, "_execute_action", action), \
             patch.object(control_service.asyncio, "sleep", AsyncMock(side_effect=[None, asyncio.CancelledError])):
            with self.assertRaises(asyncio.CancelledError):
                await control_service._monitor_local_stack()
        action.assert_awaited_once_with("START", settings)

    async def test_intentional_stop_does_not_auto_restart(self):
        settings = SimpleNamespace(auto_recover_enabled=True, auto_recover_interval_seconds=30)
        action = AsyncMock()
        with patch.object(control_service, "get_settings", return_value=settings), \
             patch.object(control_service, "_auto_recovery_paused", True), \
             patch.object(control_service, "_execute_action", action), \
             patch.object(control_service.asyncio, "sleep", AsyncMock(side_effect=[None, asyncio.CancelledError])):
            with self.assertRaises(asyncio.CancelledError):
                await control_service._monitor_local_stack()
        action.assert_not_awaited()
