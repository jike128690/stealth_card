"""pynput 全局热键监听与跨线程 Qt 信号分发（精简版）。"""

import logging

from pynput import keyboard
from pynput.keyboard import GlobalHotKeys
from PyQt5.QtCore import QObject, pyqtSignal

log = logging.getLogger(__name__)

_HOTKEY_SIGNALS = {
    "toggle_expand": "sig_toggle_expand",
    "next_card": "sig_next_card",
    "prev_card": "sig_prev_card",
    "mark_unfamiliar": "sig_mark_unfamiliar",
    "quick_capture": "sig_quick_capture",
    "boss_key": "sig_boss_key",
    "opacity_up": "sig_opacity_up",
    "opacity_down": "sig_opacity_down",
}


class SignalBus(QObject):
    """全局跨线程信号中枢，将后台监听事件安全分发至 GUI 主线程"""

    sig_toggle_expand = pyqtSignal()      # 展开背面或切至下一张
    sig_next_card = pyqtSignal()          # 下一张卡片
    sig_prev_card = pyqtSignal()          # 上一张卡片
    sig_mark_unfamiliar = pyqtSignal()    # 标记生疏
    sig_quick_capture = pyqtSignal()      # 剪贴板划词摘录
    sig_boss_key = pyqtSignal()           # 全局老板键显隐
    sig_opacity_up = pyqtSignal()         # 提高窗口不透明度
    sig_opacity_down = pyqtSignal()       # 降低窗口不透明度
    sig_reload_files = pyqtSignal()       # 配置文件或题库热重载


class HotkeyService:
    """注册 settings.yaml 中的全局热键。"""

    def __init__(self, bus: SignalBus, hotkey_map: dict):
        self._bus = bus
        self._hotkeys = None
        self._callbacks = {}
        for action, combo in (hotkey_map or {}).items():
            signal_name = _HOTKEY_SIGNALS.get(action)
            if signal_name is None or not combo:
                continue
            try:
                keyboard.HotKey.parse(combo)  # 提前校验组合键语法
            except ValueError:
                log.warning("热键语法无效，已跳过：%s = %r", action, combo)
                continue
            self._callbacks[combo] = getattr(bus, signal_name).emit

    def start(self):
        if self._callbacks:
            self._hotkeys = GlobalHotKeys(self._callbacks)
            self._hotkeys.start()
            log.info("全局热键监听已启动：%s", ", ".join(self._callbacks))

    def stop(self):
        if self._hotkeys is not None:
            try:
                self._hotkeys.stop()
            except Exception:
                log.debug("热键监听停止失败", exc_info=True)
            self._hotkeys = None
