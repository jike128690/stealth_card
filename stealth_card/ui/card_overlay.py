"""PyQt5 无边框悬浮卡片组件（精简版）。

特性：常驻置顶、任意位置按住左键即可拖动、文字背景板、
双段式折叠/展开动画、老板键显隐、防投屏隔离。
"""

import json
import logging
import os

from PyQt5.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QVariantAnimation
from PyQt5.QtGui import QCursor, QGuiApplication
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.win_stealth import WinStealthController
from paths import get_external_path

log = logging.getLogger(__name__)

_MIN_OPACITY = 0.25  # 透明调节下限，避免完全看不见


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
        self._expanded = False
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
        self._front_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._back_label = QLabel(self)
        self._back_label.setTextFormat(Qt.RichText)
        self._back_label.setWordWrap(True)
        self._back_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._back_label.setFixedWidth(self._width - 18)
        self._back_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._back_label.hide()

        layout.addWidget(self._front_label, 0)
        layout.addWidget(self._back_label, 1)

        self.setCursor(Qt.SizeAllCursor)
        self.setFixedHeight(self._collapsed_h)
        self._apply_skin()
        self.setWindowOpacity(self._opacity)
        self._pos_path = get_external_path(os.path.join("data", "window_pos.json"))
        self._restore_position()

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
        self._security = settings.get("security") or {}
        self._width = int(self._appearance.get("width", 300))
        self._collapsed_h = int(self._appearance.get("collapsed_height", 45))
        self._expanded_min = int(self._appearance.get("expanded_height_min", 140))
        self._expanded_max = int(self._appearance.get("expanded_height_max", 180))
        if not hasattr(self, "_opacity"):
            self._opacity = float(self._appearance.get("window_opacity", 0.9))
        self._default_skin = self._appearance.get("default_skin", "excel_comment")
        self._anti_capture = bool(self._security.get("anti_capture", True))

    def apply_settings(self, settings: dict):
        """热重载 settings.yaml 后刷新外观配置"""
        self._apply_config(settings)
        self._apply_skin()
        if self.isVisible():
            self.setWindowOpacity(self._opacity)

    def set_engine(self, engine):
        self._engine = engine

    def _apply_skin(self):
        bg_color = self._style.get("bg_color", "#141a26")
        bg_gradient = self._style.get("bg_gradient")
        border_color = self._style.get("border_color")
        font_family = self._style.get("font_family", "Microsoft YaHei")
        radius = int(self._style.get("radius") or 0)
        text_color = self._style.get("text_color", "#e6e9f0")
        border_css = f"1px solid {border_color}" if border_color else "none"
        background_css = bg_gradient or bg_color
        radius_css = f" border-radius: {radius}px;" if radius else ""
        self.setStyleSheet(
            f"CardOverlay {{ background: {background_css}; border: {border_css};"
            f"{radius_css} }}"
            f"QLabel {{ background: transparent; color: {text_color}; font-size: 12px;"
            f" font-family: '{font_family}'; }}"
        )

    def _default_position(self) -> QPoint:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return QPoint(0, 0)
        geometry = screen.availableGeometry()
        margin_right = int(self._appearance.get("margin_right", 24))
        margin_bottom = int(self._appearance.get("margin_bottom", 24))
        x = geometry.right() - self._width - margin_right
        y = geometry.bottom() - self._collapsed_h - margin_bottom
        return QPoint(max(geometry.left(), x), max(geometry.top(), y))

    def _restore_position(self):
        """优先恢复上次拖动保存的位置与透明度，否则回落屏幕右下角"""
        point = None
        saved_opacity = None
        try:
            with open(self._pos_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            point = QPoint(int(data["x"]), int(data["y"]))
            if "opacity" in data:
                saved_opacity = float(data["opacity"])
        except Exception:
            point = None
        if point is None or not self._point_on_some_screen(point):
            point = self._default_position()
        if saved_opacity is not None:
            self._opacity = max(_MIN_OPACITY, min(1.0, saved_opacity))
            self.setWindowOpacity(self._opacity)
        self.move(point)

    @staticmethod
    def _point_on_some_screen(point: QPoint) -> bool:
        for screen in QGuiApplication.screens():
            if screen.availableGeometry().adjusted(0, 0, 1, 1).contains(point):
                return True
        return False

    def _clamp_to_screen(self):
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        x = min(max(self.x(), geometry.left()), geometry.right() - self.width())
        y = min(max(self.y(), geometry.top()), geometry.bottom() - self.height())
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    def _save_position(self):
        try:
            os.makedirs(os.path.dirname(self._pos_path), exist_ok=True)
            with open(self._pos_path, "w", encoding="utf-8") as fp:
                json.dump(
                    {"x": self.x(), "y": self.y(), "opacity": round(self._opacity, 3)},
                    fp,
                )
        except Exception:
            log.debug("窗口位置保存失败", exc_info=True)

    # ---------- 透明度调节 ----------

    def adjust_opacity(self, delta: float):
        """±5% 调节窗口不透明度，实时生效并持久化"""
        self._opacity = max(_MIN_OPACITY, min(1.0, self._opacity + delta))
        if self.isVisible():
            self._opacity_anim.stop()
            self.setWindowOpacity(self._opacity)
        self._save_position()
        log.info("窗口透明度：%d%%", round(self._opacity * 100))

    # ---------- 内容渲染 ----------

    def apply_card(self, card):
        self._card = card
        self._render_card()

    def _with_text_bg(self, html_text: str) -> str:
        """按皮肤给文字垫一块背景板，让字体更醒目"""
        color = self._style.get("text_bg_color")
        if not color:
            return html_text
        return (
            '<table width="100%" cellspacing="0" cellpadding="3">'
            f'<tr><td bgcolor="{color}">{html_text}</td></tr></table>'
        )

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
            self._front_label.setText(
                self._with_text_bg(self._engine.render_front(template_id, self._card))
            )
            self._back_label.setText(
                self._with_text_bg(self._engine.render_back(template_id, self._card))
            )
        if self._expanded:
            self.setFixedHeight(self._compute_expanded_height())

    # ---------- 显示与隐藏 ----------

    def _animate_opacity(self, target: float):
        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(max(0.0, self.windowOpacity()))
        self._opacity_anim.setEndValue(target)
        self._opacity_anim.start()

    def reveal(self):
        """淡入显示窗口"""
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
        self._animate_opacity(max(0.05, min(1.0, self._opacity)))

    def ensure_visible(self):
        """热键操作前确保窗口可见"""
        if not self.isVisible():
            self.reveal()

    def toggle_boss_key(self):
        if self.isVisible():
            self._opacity_anim.stop()
            self.hide()
            log.info("老板键：窗口已隐藏")
        else:
            self.reveal()
            log.info("老板键：窗口已恢复")

    # ---------- 双段式展开 ----------

    def toggle_expand(self) -> bool:
        """折叠态展开背面；展开态返回 True 表示调用方应标记已读并翻页"""
        self.ensure_visible()
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

    # ---------- 拖动（任意位置按住左键即可） ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = QCursor.pos() - self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(QCursor.pos() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_offset is not None:
            self._clamp_to_screen()
            self._save_position()
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
