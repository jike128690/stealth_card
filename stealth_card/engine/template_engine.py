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
        return self._render(tpl.get("front", ""), fields)

    def render_back(self, template_id: str, fields: dict) -> str:
        tpl = self._templates.get(template_id)
        if tpl is None:
            return self._fallback_back(fields)
        return self._render(tpl.get("back", ""), fields)

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
            "border_color": skin.get("border_color"),
            "font_family": skin.get("font_family", "Microsoft YaHei"),
        }
        if style.get("bg_color"):
            resolved["bg_color"] = style["bg_color"]
        if "border_color" in style:
            resolved["border_color"] = style["border_color"]
        if style.get("font_family"):
            resolved["font_family"] = style["font_family"]
        return resolved

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
