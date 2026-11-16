"""PyQt5 无边框悬浮卡片组件与折叠/展开/伪装状态机（对应需求 2 / 4）。

可见性状态：
  VIS_HIDDEN  窗口隐藏（自动退避或老板键）
  VIS_AUTO    闲置自动浮现（低透明度，键盘输入立即退避）
  VIS_MANUAL  热键手动唤出（正常透明度，不因键击隐藏）
"""

import html
import logging

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, Qt, QVariantAnimation
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from core.win_stealth import WinStealthController

log = logging.getLogger(__name__)

VIS_HIDDEN = "hidden"
VIS_AUTO = "auto"
VIS_MANUAL = "manual"

_ADJUST_BORDER = "#2962FF"  # 调节锁定态的高亮边框


class CardOverlay(QWidget):
    def __init__(self, engine, settings: dict):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self._apply_config(settings)
        self._engine = engine
        self._hwnd = 0
        self._visibility = VIS_HIDDEN
        self._boss_hidden = False
        self._manual_suspended = False
        self._expanded = False
        self._decoy = False
        self._card = None
        self._style = {}
        self._drag_offset = None

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(self._width)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        self._front_label = QLabel(self)
        self._front_label.setTextFormat(Qt.RichText)
        self._front_label.setWordWrap(True)
        self._front_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._front_label.setFixedHeight(self._collapsed_h - 10)

        self._back_label = QLabel(self)
        self._back_label.setTextFormat(Qt.RichText)
        self._back_label.setWordWrap(True)
        self._back_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._back_label.setFixedWidth(self._width - 18)
        self._back_label.hide()

        layout.addWidget(self._front_label, 0)
        layout.addWidget(self._back_label, 1)

        self.setFixedHeight(self._collapsed_h)
        self._apply_skin()
        self.setWindowOpacity(self._manual_opacity)
        self._move_to_default_position()

        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._opacity_anim.setDuration(240)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._height_anim = QVariantAnimation(self)
        self._height_anim.setDuration(180)
        self._height_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._height_anim.valueChanged.connect(lambda value: self.setFixedHeight(int(value)))
        self._height_anim.finished.connect(self._on_height_anim_finished)

    # ---------- 配置与外观 ----------

    def _apply_config(self, settings: dict):
        settings = settings or {}
        self._appearance = settings.get("appearance") or {}
        self._behavior = settings.get("behavior") or {}
        self._security = settings.get("security") or {}
        self._width = int(self._appearance.get("width", 300))
        self._collapsed_h = int(self._appearance.get("collapsed_height", 45))
        self._expanded_min = int(self._appearance.get("expanded_height_min", 140))
        self._expanded_max = int(self._appearance.get("expanded_height_max", 180))
        self._manual_opacity = float(self._appearance.get("window_opacity", 0.9))
        self._auto_opacity = float(self._appearance.get("auto_popup_opacity", 0.65))
        self._default_skin = self._appearance.get("default_skin", "excel_comment")
        self._decoy_texts = dict(self._security.get("decoy_texts") or {})
        self._anti_capture = bool(self._security.get("anti_capture", True))
        self._penetrate = bool(self._security.get("click_through_default", True))

    def apply_settings(self, settings: dict):
        """热重载 settings.yaml 后刷新外观配置"""
        self._apply_config(settings)
        self._apply_skin()
        if self.isVisible():
            self.setWindowOpacity(self._target_opacity())

    def set_engine(self, engine):
        self._engine = engine

    def _apply_skin(self):
        bg_color = self._style.get("bg_color", "#FFFFE1")
        border_color = self._style.get("border_color")
        font_family = self._style.get("font_family", "Microsoft YaHei")
        if not self._penetrate:
            border_css = f"1px solid {_ADJUST_BORDER}"
        elif border_color:
            border_css = f"1px solid {border_color}"
        else:
            border_css = "none"
        self.setStyleSheet(
            f"CardOverlay {{ background-color: {bg_color}; border: {border_css}; }}"
            f"QLabel {{ background: transparent; color: #333333; font-size: 12px;"
            f" font-family: '{font_family}'; }}"
        )

    def _move_to_default_position(self):
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        margin_right = int(self._appearance.get("margin_right", 24))
        margin_bottom = int(self._appearance.get("margin_bottom", 24))
        x = geometry.right() - self._width - margin_right
        y = geometry.bottom() - self._collapsed_h - margin_bottom
        self.move(max(geometry.left(), x), max(geometry.top(), y))

    # ---------- 内容渲染 ----------

    def apply_card(self, card):
        self._card = card
        self._decoy = False
        self._render_card()

    def _render_card(self):
        if self._card is None:
            self._front_label.setText(
                '<div style="color:#333333; font-size:12px;">'
                "题库为空：请编辑 data/cards.xlsx</div>"
            )
            self._back_label.setText("")
        else:
            template_id = self._card.get("template") or "default"
            self._style = self._engine.resolve_style(template_id, self._default_skin)
            self._apply_skin()
            self._front_label.setText(self._engine.render_front(template_id, self._card))
            self._back_label.setText(self._engine.render_back(template_id, self._card))
        if self._expanded:
            self.setFixedHeight(self._compute_expanded_height())

    # ---------- 可见性与淡入淡出 ----------

    def _target_opacity(self) -> float:
        base = self._auto_opacity if self._visibility == VIS_AUTO else self._manual_opacity
        return max(0.05, min(1.0, float(base)))

    def _animate_opacity(self, target: float):
        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(max(0.0, self.windowOpacity()))
        self._opacity_anim.setEndValue(target)
        self._opacity_anim.start()

    def reveal(self, auto: bool = False):
        """显示窗口；auto=True 表示闲置自动浮现（低透明度）"""
        self._visibility = VIS_AUTO if auto else VIS_MANUAL
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
        self._animate_opacity(self._target_opacity())

    def ensure_visible(self):
        """热键操作前确保窗口可见（视为手动唤出）"""
        if not self.isVisible():
            self._boss_hidden = False
            self._manual_suspended = False
            if self._decoy:
                self._exit_decoy()
            self.reveal(auto=False)

    def _hide_instant(self):
        self._opacity_anim.stop()
        self._visibility = VIS_HIDDEN
        self.hide()

    def toggle_boss_key(self):
        if self.isVisible():
            self._boss_hidden = True
            self._manual_suspended = False
            self._hide_instant()
            log.info("老板键：窗口已隐藏")
        else:
            self._boss_hidden = False
            if self._decoy:
                self._exit_decoy()
            self.reveal(auto=False)
            log.info("老板键：窗口已恢复")

    # ---------- 环境感知状态机 ----------

    def environment_update(self, allowed: bool, idle_enough: bool,
                           cursor_jumped: bool, decoy_env: str = "default"):
        """由主线程每 500ms 调用，驱动显示 / 隐藏 / 伪装态流转"""
        if not allowed:
            # 前台切入微信、钉钉、会议软件或资源管理器等：立即隐藏
            if self.isVisible():
                if self._visibility == VIS_MANUAL:
                    self._manual_suspended = True
                self._hide_instant()
            return

        if self._manual_suspended:
            self._manual_suspended = False
            self.reveal(auto=False)

        if cursor_jumped and self.isVisible():
            self._enter_decoy(decoy_env)

        if self._boss_hidden:
            return

        if idle_enough:
            if self._decoy:
                self._exit_decoy()
            if not self.isVisible():
                self.reveal(auto=True)

    def on_keyboard_activity(self):
        """敲击键盘瞬间：自动浮现的卡片立即隐藏，不干扰打字办公"""
        if self._visibility == VIS_AUTO:
            self._hide_instant()

    # ---------- 伪装态 ----------

    def _enter_decoy(self, env_key: str):
        if self._decoy:
            return
        text = (
            self._decoy_texts.get(env_key)
            or self._decoy_texts.get("default")
            or "正在同步最近使用的文件索引…"
        )
        self._decoy = True
        self._front_label.setText(
            f'<div style="color:#666666; font-size:12px;">{html.escape(text)}</div>'
        )
        if self._expanded:
            self._back_label.clear()
        log.info("进入伪装态：%s", env_key)

    def _exit_decoy(self):
        self._decoy = False
        self._render_card()

    # ---------- 双段式展开 ----------

    def toggle_expand(self) -> bool:
        """折叠态展开背面；展开态返回 True 表示调用方应标记已读并翻页"""
        self.ensure_visible()
        if self._decoy:
            self._exit_decoy()
        if not self._expanded:
            self._expand()
            return False
        self._collapse()
        return True

    def _expand(self):
        self._expanded = True
        self._back_label.show()
        self._animate_height(self._compute_expanded_height())

    def _collapse(self):
        self._expanded = False
        self._animate_height(self._collapsed_h)

    def _compute_expanded_height(self) -> int:
        needed = self._back_label.heightForWidth(self._width - 18)
        if needed <= 0:
            self._back_label.adjustSize()
            needed = self._back_label.height()
        total = self._collapsed_h + max(0, needed)
        return int(max(self._expanded_min, min(self._expanded_max, total)))

    def _animate_height(self, target: int):
        self._height_anim.stop()
        self._height_anim.setStartValue(self.height())
        self._height_anim.setEndValue(int(target))
        self._height_anim.start()

    def _on_height_anim_finished(self):
        if not self._expanded:
            self._back_label.hide()

    # ---------- 鼠标穿透与拖动 ----------

    def is_penetrating(self) -> bool:
        return self._penetrate

    def set_penetration(self, penetrate: bool):
        self._penetrate = penetrate
        if self._hwnd:
            WinStealthController.set_click_through(self._hwnd, penetrate)
        self._apply_skin()
        self.setCursor(Qt.ArrowCursor if penetrate else Qt.SizeAllCursor)
        log.info("鼠标穿透%s", "开启" if penetrate else "关闭（可拖动调节位置）")

    def mousePressEvent(self, event):
        if not self._penetrate and event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            not self._penetrate
            and self._drag_offset is not None
            and event.buttons() & Qt.LeftButton
        ):
            self.move(event.globalPos() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    # ---------- 系统级隐蔽绑定 ----------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._hwnd:
            self._hwnd = int(self.winId())
            self.setWindowOpacity(self.windowOpacity())  # 确保 Qt 走分层窗口路径
            if self._anti_capture:
                ok = WinStealthController.enable_anti_capture(self._hwnd, True)
                log.info("防投屏/防截图隔离：%s", "已开启" if ok else "设置失败")
            WinStealthController.set_click_through(self._hwnd, self._penetrate)
