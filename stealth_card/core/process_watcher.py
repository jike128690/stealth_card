"""前台活动窗口轮询与进程白名单比对服务（对应需求 5.4）。"""

import logging

import psutil

from core import win_stealth

log = logging.getLogger(__name__)


def _normalize(process_name: str) -> str:
    name = (process_name or "").strip().lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


class ProcessWatcher:
    """无状态轮询服务：由主线程 QTimer 每 500ms 调用一次 snapshot()。"""

    def __init__(self, whitelist):
        self.whitelist = {_normalize(p) for p in (whitelist or []) if p}

    def update_whitelist(self, whitelist):
        self.whitelist = {_normalize(p) for p in (whitelist or []) if p}

    def current_process_name(self) -> str:
        pid = win_stealth.WinStealthController.get_foreground_process_pid()
        if not pid:
            return ""
        try:
            return psutil.Process(pid).name()
        except (psutil.Error, OSError):
            return ""

    def is_allowed(self, process_name: str) -> bool:
        return _normalize(process_name) in self.whitelist

    def snapshot(self) -> dict:
        """采集一次前台进程、白名单判定与键鼠闲置时长"""
        name = self.current_process_name()
        return {
            "process": name,
            "allowed": self.is_allowed(name),
            "idle_seconds": win_stealth.WinStealthController.get_idle_seconds(),
        }
