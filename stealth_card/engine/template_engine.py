"""自定义模板引擎：条件语法解析、变量插值与兜底渲染器（对应需求 3.2）。"""

import hashlib
import html
import logging
import math
import re

log = logging.getLogger(__name__)

_IF_BLOCK_RE = re.compile(r"\{\{#if\s+([\w\u4e00-\u9fff]+)\s*\}\}(.*?)\{\{/if\}\}", re.DOTALL)
_VAR_RE = re.compile(r"\{\{\s*([\w\u4e00-\u9fff]+)\s*\}\}")
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_NULLISH = {"", "nan", "none", "null"}

# 分类徽标配色（缩写速记卡片的 cat 字段：concept/reg/clk/bus）
CATEGORY_STYLES = {
    "concept": {"label": "GPIO 概念", "color": "#38bdf8", "bg": "#1b3446"},
    "reg": {"label": "GPIO 寄存器", "color": "#34d399", "bg": "#1a3a33"},
    "clk": {"label": "时钟源", "color": "#fbbf24", "bg": "#3a3320"},
    "bus": {"label": "总线与辅助", "color": "#f472b6", "bg": "#392331"},
}


def clean_value(value) -> str:
    """过滤 None / NaN / 空串等缺失值"""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in _NULLISH else text


def _escape(text: str) -> str:
    """转义尖括号等 HTML 特殊字符，并把换行转换为 <br>"""
    return html.escape(text, quote=False).replace("\r\n", "\n").replace("\n", "<br>")


class TemplateEngine:
    """解析 templates.yaml：皮肤 → 样式，模板 → 正反面 HTML 骨架。"""

    def __init__(self, config: dict):
        config = config or {}
        self._skins = config.get("skins") or {}
        self._templates = config.get("templates") or {}

    def has_template(self, template_id: str) -> bool:
        return template_id in self._templates

    def render_front(self, template_id: str, fields: dict) -> str:
        tpl = self._templates.get(template_id)
        if tpl is None:
            return self._fallback_front(fields)
        return self._render(tpl.get("front", ""), self._prepare_fields(fields))

    def render_back(self, template_id: str, fields: dict) -> str:
        tpl = self._templates.get(template_id)
        if tpl is None:
            return self._fallback_back(fields)
        return self._render(tpl.get("back", ""), self._prepare_fields(fields))

    def front_plain_text(self, template_id: str, fields: dict) -> str:
        """把渲染后的正面 HTML 还原为纯文本，用于生成卡片哈希"""
        text = _BR_RE.sub("\n", self.render_front(template_id, fields))
        text = _TAG_RE.sub("", text)
        lines = [line.strip() for line in html.unescape(text).splitlines()]
        return "\n".join(line for line in lines if line)

    def card_hash(self, template_id: str, fields: dict) -> str:
        plain = self.front_plain_text(template_id, fields)
        return hashlib.md5(plain.encode("utf-8")).hexdigest()

    def resolve_style(self, template_id: str, default_skin: str = None) -> dict:
        """模板样式优先，缺省回落到皮肤定义"""
        tpl = self._templates.get(template_id) or {}
        style = dict(tpl.get("style") or {})
        skin_name = style.get("skin") or default_skin or "excel_comment"
        skin = self._skins.get(skin_name) or {}
        resolved = {
            "skin": skin_name,
            "bg_color": skin.get("bg_color", "#FFFFE1"),
            "bg_gradient": skin.get("bg_gradient"),
            "border_color": skin.get("border_color"),
            "font_family": skin.get("font_family", "Microsoft YaHei"),
            "radius": skin.get("radius", 0),
            "text_color": skin.get("text_color", "#333333"),
            "muted_color": skin.get("muted_color", "#666666"),
            "accent_color": skin.get("accent_color", "#2b579a"),
            "text_bg_color": skin.get("text_bg_color"),
        }
        for key in (
            "bg_color", "bg_gradient", "font_family", "radius",
            "text_color", "muted_color", "accent_color", "text_bg_color",
        ):
            if key in style and style[key] not in (None, ""):
                resolved[key] = style[key]
        if "border_color" in style:
            resolved["border_color"] = style["border_color"]
        return resolved

    @staticmethod
    def _prepare_fields(fields: dict) -> dict:
        """注入分类徽标的派生字段（标签/前景色/底色），供模板直接引用"""
        prepared = dict(fields or {})
        category = clean_value(prepared.get("cat")).lower()
        palette = CATEGORY_STYLES.get(category)
        if palette:
            prepared.setdefault("cat_label", palette["label"])
            prepared["cat_color"] = palette["color"]
            prepared["cat_bg"] = palette["bg"]
        return prepared

    def _render(self, source: str, fields: dict) -> str:
        def _if_repl(match):
            return match.group(2) if clean_value(fields.get(match.group(1))) else ""

        text = _IF_BLOCK_RE.sub(_if_repl, source or "")

        def _var_repl(match):
            return _escape(clean_value(fields.get(match.group(1))))

        return _VAR_RE.sub(_var_repl, text)

    @staticmethod
    def _fallback_front(fields: dict) -> str:
        """模板缺失时的兜底正面：展示第一个非空字段"""
        for key, value in (fields or {}).items():
            if key == "template":
                continue
            text = clean_value(value)
            if text:
                return f'<div style="color:#333333; font-size:12px;"><b>{_escape(text)}</b></div>'
        return '<div style="color:#333333; font-size:12px;">（空卡片）</div>'

    @staticmethod
    def _fallback_back(fields: dict) -> str:
        """模板缺失时的兜底背面：通用键值对列表，确保数据不丢失"""
        rows = "".join(
            f"<div><b>{_escape(str(key))}：</b>{_escape(clean_value(value))}</div>"
            for key, value in (fields or {}).items()
            if key != "template" and clean_value(value)
        )
        if not rows:
            rows = "<div>（空卡片）</div>"
        return f'<div style="color:#333333; font-size:12px; line-height:1.4;">{rows}</div>'
