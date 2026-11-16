import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.template_engine import TemplateEngine, clean_value

CONFIG = {
    "skins": {
        "excel_comment": {
            "bg_color": "#FFFFE1",
            "border_color": "#D4D4D4",
            "font_family": "Microsoft YaHei",
        },
        "web_blank": {
            "bg_color": "#FFFFFF",
            "border_color": None,
            "font_family": "Calibri",
        },
    },
    "templates": {
        "tech_qa": {
            "style": {"skin": "excel_comment", "border_color": "#D4D4D4"},
            "front": (
                '<div><b>[批注]</b> {{title}}'
                "{{#if tag}}<span> ({{tag}})</span>{{/if}}</div>"
            ),
            "back": (
                "<div><b>核心：</b>{{core}}"
                "{{#if detail}}<div>{{detail}}</div>{{/if}}</div>"
            ),
        },
    },
}


class TemplateEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = TemplateEngine(CONFIG)

    def test_variable_interpolation(self):
        html_text = self.engine.render_front("tech_qa", {"title": "TCP", "tag": "网络"})
        self.assertIn("TCP", html_text)
        self.assertIn(" (网络)", html_text)
        self.assertNotIn("{{", html_text)

    def test_conditional_block_removed_when_empty(self):
        html_text = self.engine.render_front("tech_qa", {"title": "TCP", "tag": ""})
        self.assertNotIn("<span>", html_text)
        self.assertNotIn("{{", html_text)
        self.assertIn("TCP", html_text)

    def test_conditional_block_removed_when_key_missing(self):
        html_text = self.engine.render_back("tech_qa", {"core": "三次握手"})
        self.assertNotIn("<div></div>", html_text)
        self.assertIn("三次握手", html_text)

    def test_html_escaping(self):
        html_text = self.engine.render_front("tech_qa", {"title": "<script>alert(1)</script>"})
        self.assertIn("&lt;script&gt;", html_text)
        self.assertNotIn("<script>", html_text)

    def test_newline_to_br(self):
        html_text = self.engine.render_back(
            "tech_qa", {"core": "第一行", "detail": "甲\n乙"}
        )
        self.assertIn("甲<br>乙", html_text)

    def test_clean_value(self):
        self.assertEqual(clean_value(None), "")
        self.assertEqual(clean_value(float("nan")), "")
        self.assertEqual(clean_value("  nan "), "")
        self.assertEqual(clean_value("None"), "")
        self.assertEqual(clean_value("  有用  "), "有用")

    def test_fallback_rendering_for_unknown_template(self):
        fields = {"title": "未知模板", "core": "兜底内容", "template": "ghost"}
        front = self.engine.render_front("ghost", fields)
        back = self.engine.render_back("ghost", fields)
        self.assertIn("未知模板", front)
        self.assertIn("core：", back)
        self.assertIn("兜底内容", back)
        self.assertNotIn("template：", back)

    def test_resolve_style(self):
        style = self.engine.resolve_style("tech_qa")
        self.assertEqual(style["bg_color"], "#FFFFE1")
        self.assertEqual(style["border_color"], "#D4D4D4")
        self.assertEqual(style["font_family"], "Microsoft YaHei")

        fallback = self.engine.resolve_style("ghost", default_skin="web_blank")
        self.assertEqual(fallback["bg_color"], "#FFFFFF")
        self.assertIsNone(fallback["border_color"])

    def test_card_hash_stable_and_sensitive(self):
        fields = {"title": "TCP", "tag": "网络"}
        first = self.engine.card_hash("tech_qa", fields)
        second = self.engine.card_hash("tech_qa", dict(fields))
        self.assertEqual(first, second)
        changed = self.engine.card_hash("tech_qa", {"title": "UDP", "tag": "网络"})
        self.assertNotEqual(first, changed)

    def test_front_plain_text_strips_tags(self):
        plain = self.engine.front_plain_text("tech_qa", {"title": "TCP", "tag": "网络"})
        self.assertNotIn("<", plain)
        self.assertIn("TCP", plain)


if __name__ == "__main__":
    unittest.main()
