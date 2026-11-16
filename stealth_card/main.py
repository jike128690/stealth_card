"""StealthCard 程序入口：单实例锁、全局异常捕获、事件循环初始化。

运行方式：python main.py
冒烟测试：设置环境变量 STEALTHCARD_EXIT_AFTER=8（秒）后自动退出
"""

import logging
import logging.handlers
import math
import os
import sys

import yaml
from PyQt5.QtCore import QObject, Qt, QTimer
from PyQt5.QtWidgets import QApplication

from core.file_watcher import HotReloadWatcher
from core.hotkey_bus import HotkeyService, SignalBus
from core.process_watcher import ProcessWatcher
from core.win_stealth import WinStealthController
from engine.excel_loader import append_card, load_cards
from engine.scheduler import Scheduler
from engine.template_engine import TemplateEngine
from paths import get_external_path
from ui.card_overlay import CardOverlay

log = logging.getLogger("stealthcard")

_DEFAULTS = {
    "appearance": {
        "default_skin": "excel_comment",
        "width": 300,
        "collapsed_height": 45,
        "expanded_height_min": 140,
        "expanded_height_max": 180,
        "window_opacity": 0.9,
        "auto_popup_opacity": 0.65,
        "margin_right": 24,
        "margin_bottom": 24,
    },
    "hotkeys": {
        "toggle_expand": "<alt>+<space>",
        "next_card": "<alt>+j",
        "prev_card": "<alt>+k",
        "mark_unfamiliar": "<alt>+m",
        "quick_capture": "<alt>+c",
        "toggle_penetrate": "<alt>+t",
        "boss_key": "<alt>+h",
    },
    "behavior": {
        "idle_seconds": 15,
        "poll_interval_ms": 500,
        "mouse_jump_pixels": 700,
        "intervals_minutes": [10, 720, 4320],
        "capture_sheet": "capture",
    },
    "security": {
        "anti_capture": True,
        "click_through_default": True,
        "process_whitelist": ["chrome", "msedge", "excel", "et"],
        "decoy_texts": {
            "excel": "#N/A 引用区域存在文本型数字，建议执行分列校验",
            "browser": "[Cache] 静态资源哈希校验完成，DOM 渲染耗时 18ms",
            "default": "正在同步最近使用的文件索引…",
        },
    },
}


def _merge_defaults(loaded: dict) -> dict:
    def merge(base: dict, override: dict) -> dict:
        result = dict(base)
        for key, value in (override or {}).items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                result[key] = merge(base[key], value)
            else:
                result[key] = value
        return result

    return merge(_DEFAULTS, loaded or {})


def _load_yaml(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8-sig") as fp:
            return yaml.safe_load(fp) or {}
    except FileNotFoundError:
        log.warning("配置文件不存在：%s", path)
    except Exception:
        log.error("配置文件解析失败：%s", path, exc_info=True)
    return {}


def _setup_logging():
    log_path = get_external_path(os.path.join("data", "app.log"))
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=256 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    if not getattr(sys, "frozen", False):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)


class AppController(QObject):
    """把信号总线、悬浮窗、题库与调度器接线为完整的交互闭环。"""

    def __init__(self, app: QApplication):
        super().__init__()
        self._app = app
        self._settings_path = get_external_path(os.path.join("config", "settings.yaml"))
        self._templates_path = get_external_path(os.path.join("config", "templates.yaml"))
        self._cards_path = get_external_path(os.path.join("data", "cards.xlsx"))
        self._db_path = get_external_path(os.path.join("data", "progress.db"))

        self.settings = _merge_defaults(_load_yaml(self._settings_path))
        self.engine = TemplateEngine(_load_yaml(self._templates_path))
        self.bus = SignalBus()
        self.overlay = CardOverlay(self.engine, self.settings)
        self.scheduler = Scheduler(
            self._db_path,
            self.settings["behavior"].get("intervals_minutes", [10, 720, 4320]),
        )
        self.watcher = ProcessWatcher(
            self.settings["security"].get("process_whitelist", [])
        )

        self._cards = []
        self._queue = []
        self._index = 0
        self._cursor = WinStealthController.get_cursor_pos()

        self._hotkeys = HotkeyService(self.bus, self.settings.get("hotkeys") or {})
        self._hotkeys.start()
        self._file_watcher = HotReloadWatcher(
            self.bus,
            [
                os.path.dirname(self._settings_path),
                os.path.dirname(self._cards_path),
            ],
        )
        self._file_watcher.start()

        self._connect_signals()
        self._load_cards_from_disk()
        self._rebuild_queue()

        self._env_timer = QTimer(self)
        self._env_timer.setInterval(
            int(self.settings["behavior"].get("poll_interval_ms", 500))
        )
        self._env_timer.timeout.connect(self._poll_environment)
        self._env_timer.start()

        self._show_current()
        self.overlay.reveal(auto=False)
        log.info("StealthCard 启动完成：%d 张卡片", len(self._queue))

    # ---------- 信号接线 ----------

    def _connect_signals(self):
        self.bus.sig_toggle_expand.connect(self._on_toggle_expand)
        self.bus.sig_next_card.connect(self._on_next_card)
        self.bus.sig_prev_card.connect(self._on_prev_card)
        self.bus.sig_mark_unfamiliar.connect(self._on_mark_unfamiliar)
        self.bus.sig_quick_capture.connect(self._on_quick_capture)
        self.bus.sig_toggle_penetrate.connect(self._on_toggle_penetrate)
        self.bus.sig_boss_key.connect(self._on_boss_key)
        self.bus.sig_reload_files.connect(self._on_reload_files)
        self.bus.sig_keyboard_activity.connect(self.overlay.on_keyboard_activity)

    # ---------- 卡片队列 ----------

    def _hash_of(self, card: dict) -> str:
        return self.engine.card_hash(card.get("template") or "", card)

    def _load_cards_from_disk(self):
        self._cards = load_cards(self._cards_path)
        log.info("题库加载完成：%d 张卡片", len(self._cards))

    def _rebuild_queue(self):
        self._queue = self.scheduler.build_queue(self._cards, self._hash_of)
        self._index = 0

    def _current_card(self):
        if not self._queue:
            return None
        if self._index >= len(self._queue):
            self._index = 0
        return self._queue[self._index]

    def _show_current(self, count_shown: bool = True):
        card = self._current_card()
        if card is not None and count_shown:
            self.scheduler.record_shown(
                self._hash_of(card), card.get("template") or ""
            )
        self.overlay.apply_card(card)

    def _advance(self, step: int = 1):
        if not self._queue:
            self.overlay.apply_card(None)
            return
        self._index = (self._index + step) % len(self._queue)
        if step > 0 and self._index == 0:
            self._rebuild_queue()  # 浏览一轮后按最新到期状态重建队列
        self.overlay.ensure_visible()
        self._show_current()

    # ---------- 热键动作 ----------

    def _on_toggle_expand(self):
        if not self._queue:
            self.overlay.ensure_visible()
            return
        completed = self.overlay.toggle_expand()
        if completed:
            card = self._current_card()
            if card is not None:
                self.scheduler.record_completed(
                    self._hash_of(card), card.get("template") or ""
                )
            self._advance(1)

    def _on_next_card(self):
        self._advance(1)

    def _on_prev_card(self):
        self._advance(-1)

    def _on_mark_unfamiliar(self):
        card = self._current_card()
        if card is None:
            return
        self.scheduler.mark_unfamiliar(
            self._hash_of(card), card.get("template") or ""
        )
        self.overlay.ensure_visible()
        log.info("已标记生疏：%s", self._hash_of(card)[:12])

    def _on_quick_capture(self):
        text = QApplication.clipboard().text().strip()
        if not text:
            log.info("剪贴板为空，忽略摘录")
            return
        title = next(
            (line.strip() for line in text.splitlines() if line.strip()), "摘录"
        )[:48]
        content = text[:5000]
        sheet = self.settings["behavior"].get("capture_sheet", "capture")
        if not append_card(self._cards_path, sheet, {"title": title, "content": content}):
            log.warning("摘录写入题库失败，题库可能正被 Excel 占用")
            return

        self._load_cards_from_disk()
        self._rebuild_queue()
        target_hash = self.engine.card_hash(sheet, {"title": title, "content": content})
        found = False
        for index, card in enumerate(self._queue):
            if self._hash_of(card) == target_hash:
                self._index = index
                found = True
                break
        if not found:
            self._index = 0
        self.overlay.ensure_visible()
        self._show_current()
        log.info("已摘录并生成新卡片：%s", title)

    def _on_toggle_penetrate(self):
        self.overlay.set_penetration(not self.overlay.is_penetrating())

    def _on_boss_key(self):
        self.overlay.toggle_boss_key()

    # ---------- 热重载 ----------

    def _on_reload_files(self):
        current_hash = None
        current = self._current_card()
        if current is not None:
            current_hash = self._hash_of(current)
        old_hotkeys = dict(self.settings.get("hotkeys") or {})

        self.settings = _merge_defaults(_load_yaml(self._settings_path))
        self.engine = TemplateEngine(_load_yaml(self._templates_path))
        self.overlay.set_engine(self.engine)
        self.overlay.apply_settings(self.settings)
        self.watcher.update_whitelist(
            self.settings["security"].get("process_whitelist", [])
        )
        self._env_timer.setInterval(
            int(self.settings["behavior"].get("poll_interval_ms", 500))
        )

        self._load_cards_from_disk()
        self._queue = self.scheduler.build_queue(self._cards, self._hash_of)
        self._index = 0
        if current_hash:
            for index, card in enumerate(self._queue):
                if self._hash_of(card) == current_hash:
                    self._index = index
                    break
        self.overlay.apply_card(self._current_card())
        if dict(self.settings.get("hotkeys") or {}) != old_hotkeys:
            log.warning("热键绑定已修改，重启程序后生效")
        log.info("热重载完成：%d 张卡片", len(self._queue))

    # ---------- 环境感知 ----------

    def _poll_environment(self):
        info = self.watcher.snapshot()
        cursor = WinStealthController.get_cursor_pos()
        jumped = False
        if cursor is not None and self._cursor is not None:
            dx = cursor[0] - self._cursor[0]
            dy = cursor[1] - self._cursor[1]
            threshold = float(
                self.settings["behavior"].get("mouse_jump_pixels", 700)
            )
            if math.hypot(dx, dy) >= threshold:
                jumped = True
        self._cursor = cursor

        idle_needed = float(self.settings["behavior"].get("idle_seconds", 15))
        self.overlay.environment_update(
            allowed=info["allowed"],
            idle_enough=info["idle_seconds"] >= idle_needed,
            cursor_jumped=jumped,
            decoy_env=self._decoy_env_for(info["process"]),
        )

    @staticmethod
    def _decoy_env_for(process_name: str) -> str:
        name = (process_name or "").strip().lower()
        if name.endswith(".exe"):
            name = name[:-4]
        if name in ("excel", "et", "wps", "wpp", "kspread"):
            return "excel"
        if name in ("chrome", "msedge", "firefox", "brave", "opera"):
            return "browser"
        return "default"

    # ---------- 生命周期 ----------

    def shutdown(self):
        self._env_timer.stop()
        self._file_watcher.stop()
        self._hotkeys.stop()
        self.scheduler.close()
        log.info("控制器已关闭")


def main() -> int:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    _setup_logging()

    if not WinStealthController.acquire_single_instance():
        log.info("检测到 StealthCard 已在运行，本次启动静默退出")
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("StealthCard")
    app.setQuitOnLastWindowClosed(False)

    try:
        controller = AppController(app)
    except Exception:
        log.critical("初始化失败", exc_info=True)
        WinStealthController.release_single_instance()
        return 1

    app.aboutToQuit.connect(controller.shutdown)

    exit_after = os.environ.get("STEALTHCARD_EXIT_AFTER")
    if exit_after:
        seconds = max(1, int(float(exit_after)))
        log.info("冒烟测试模式：%d 秒后自动退出", seconds)
        QTimer.singleShot(seconds * 1000, app.quit)

    code = app.exec_()
    WinStealthController.release_single_instance()
    log.info("StealthCard 退出，返回码 %s", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
