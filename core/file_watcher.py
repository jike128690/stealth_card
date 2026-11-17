"""watchdog 配置与题库热重载监听器（对应开发计划 2.2 防抖热重载）。

watchdog 事件在独立后台线程产生，这里只记录时间戳与待处理路径；
主线程 QTimer 检查“300 毫秒内无新事件”后再广播重载信号，
避免 Excel 保存过程的临时文件与重命名动作触发多次解析。
"""

import logging
import os
import threading
import time

from PyQt5.QtCore import QTimer
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

log = logging.getLogger(__name__)

_WATCH_EXTS = (".yaml", ".yml", ".xlsx", ".csv")


class _ReloadHandler(FileSystemEventHandler):
    def __init__(self, watcher):
        super().__init__()
        self._watcher = watcher

    def on_any_event(self, event):
        if event.is_directory:
            return
        path = str(getattr(event, "dest_path", "") or event.src_path)
        name = os.path.basename(path)
        if name.startswith("~$"):  # Office 打开文件时生成的临时锁文件
            return
        if not name.lower().endswith(_WATCH_EXTS):
            return
        self._watcher._mark_pending(path)


class HotReloadWatcher:
    """后台线程捕获文件保存事件，主线程 QTimer 防抖后广播重载信号。"""

    def __init__(self, bus, watch_dirs, debounce_ms: int = 300):
        self._bus = bus
        self._lock = threading.Lock()
        self._pending_paths = set()
        self._last_event_at = 0.0
        self._debounce_seconds = max(0.05, debounce_ms / 1000.0)
        self._observer = Observer()
        self._timer = QTimer()  # 必须在 GUI 主线程创建
        self._timer.setInterval(max(50, debounce_ms // 2))
        self._timer.timeout.connect(self._flush_if_quiet)
        for directory in watch_dirs:
            if directory and os.path.isdir(directory):
                self._observer.schedule(_ReloadHandler(self), directory, recursive=False)

    def _mark_pending(self, path: str):
        with self._lock:
            self._pending_paths.add(path)
            self._last_event_at = time.monotonic()

    def _flush_if_quiet(self):
        with self._lock:
            if not self._pending_paths:
                return
            if time.monotonic() - self._last_event_at < self._debounce_seconds:
                return
            paths = sorted(self._pending_paths)
            self._pending_paths.clear()
        log.info(
            "检测到文件保存事件，触发热重载：%s",
            ", ".join(os.path.basename(p) for p in paths),
        )
        self._bus.sig_reload_files.emit()

    def start(self):
        self._observer.start()
        self._timer.start()
        log.info("文件热重载监听已启动")

    def stop(self):
        self._timer.stop()
        try:
            self._observer.stop()
            self._observer.join(timeout=2)
        except Exception:
            log.debug("watchdog 停止异常", exc_info=True)
