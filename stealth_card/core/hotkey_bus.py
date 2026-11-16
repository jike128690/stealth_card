"""pynput 全局热键监听与跨线程 Qt 信号分发（对应需求 4.2 与开发计划 2.4 / 3.3）。"""

import logging
import time

from pynput import keyboard
from pynput.keyboard import GlobalHotKeys, Key
from PyQt5.QtCore import QObject, pyqtSignal

log = logging.getLogger(__name__)

_MODIFIER_KEYS = {
    Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr,
    Key.ctrl, Key.ctrl_l, Key.ctrl_r,
    Key.cmd, Key.cmd_l, Key.cmd_r,
    Key.shift, Key.shift_l, Key.shift_r,
}

# 带这些修饰键的按键属于组合键操作（如热键、Ctrl+C），不计入“连续打字”
_COMBO_MODIFIERS = {
    Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr,
    Key.ctrl, Key.ctrl_l, Key.ctrl_r,
    Key.cmd, Key.cmd_l, Key.cmd_r,
}

_HOTKEY_SIGNALS = {
    "toggle_expand": "sig_toggle_expand",
    "next_card": "sig_next_card",
    "prev_card": "sig_prev_card",
    "mark_unfamiliar": "sig_mark_unfamiliar",
    "quick_capture": "sig_quick_capture",
    "toggle_penetrate": "sig_toggle_penetrate",
    "boss_key": "sig_boss_key",
}


class SignalBus(QObject):
    """全局跨线程信号中枢，将后台监听事件安全分发至 GUI 主线程"""

    sig_toggle_expand = pyqtSignal()      # 展开背面或切至下一张
    sig_next_card = pyqtSignal()          # 下一张卡片
    sig_prev_card = pyqtSignal()          # 上一张卡片
    sig_mark_unfamiliar = pyqtSignal()    # 标记生疏
    sig_quick_capture = pyqtSignal()      # 剪贴板划词摘录
    sig_toggle_penetrate = pyqtSignal()   # 切换鼠标穿透
    sig_boss_key = pyqtSignal()           # 全局老板键显隐
    sig_reload_files = pyqtSignal()       # 配置文件或题库热重载
    sig_keyboard_activity = pyqtSignal()  # 普通键入活动（触发瞬时退避）


class HotkeyService:
    """注册 settings.yaml 中的全局热键，并旁路监听普通键盘输入活动。"""

    def __init__(self, bus: SignalBus, hotkey_map: dict):
        self._bus = bus
        self._hotkeys = None
        self._activity_listener = None
        self._held_modifiers = set()
        self._last_activity_emit = 0.0
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
        self._activity_listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        self._activity_listener.start()

    def stop(self):
        for listener in (self._hotkeys, self._activity_listener):
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    log.debug("监听线程停止失败", exc_info=True)
        self._hotkeys = None
        self._activity_listener = None

    def _on_press(self, key):
        if key in _MODIFIER_KEYS:
            self._held_modifiers.add(key)
            return
        if self._held_modifiers & _COMBO_MODIFIERS:
            return
        now = time.monotonic()
        if now - self._last_activity_emit >= 0.2:  # 节流，避免逐键触发信号风暴
            self._last_activity_emit = now
            self._bus.sig_keyboard_activity.emit()

    def _on_release(self, key):
        self._held_modifiers.discard(key)
