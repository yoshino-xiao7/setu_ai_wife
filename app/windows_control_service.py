from __future__ import annotations

import socket
import threading
from pathlib import Path

import servicemanager
import win32event
import win32service
import win32serviceutil

from app.control_service_supervisor import ControlServiceSupervisor

BOOT_LOG = Path(__file__).resolve().parent.parent / "logs" / "windows-control-service.log"


def _boot_log(message: str) -> None:
    BOOT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with BOOT_LOG.open("a", encoding="utf-8") as log:
        log.write(f"{message}\n")


class XueliangAiControlService(win32serviceutil.ServiceFramework):
    _svc_name_ = "XueliangAiControlService"
    _svc_display_name_ = "Xueliang AI Control Service"
    _svc_description_ = "Keeps the local AI control endpoint on 127.0.0.1:7878 running for cloud start/stop commands."

    def __init__(self, args: list[str]) -> None:
        win32serviceutil.ServiceFramework.__init__(self, args)
        socket.setdefaulttimeout(60)
        self.stop_event_handle = win32event.CreateEvent(None, 0, 0, None)
        self.stop_event = threading.Event()
        self.supervisor = ControlServiceSupervisor()

    def SvcStop(self) -> None:
        _boot_log("SvcStop called")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stop_event.set()
        win32event.SetEvent(self.stop_event_handle)

    def SvcDoRun(self) -> None:
        _boot_log("SvcDoRun started")
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self.supervisor.run(self.stop_event)
        _boot_log("SvcDoRun stopped")
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, ""),
        )


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(
        XueliangAiControlService,
        serviceClassString="app.windows_control_service.XueliangAiControlService",
    )
