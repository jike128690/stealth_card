import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from pynput import keyboard

from engine.excel_loader import load_cards
from engine.template_engine import TemplateEngine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ConfigIntegrationTest(unittest.TestCase):
    def _load(self, name):
        with open(os.path.join(BASE_DIR, name), encoding="utf-8-sig") as fp:
            return yaml.safe_load(fp)

    def test_settings_hotkeys_all_valid(self):
        settings = self._load(os.path.join("config", "settings.yaml"))
        hotkeys = settings["hotkeys"]
        self.assertEqual(len(hotkeys), 8)
        for action, combo in hotkeys.items():
            with self.subTest(action=action):
                keyboard.HotKey.parse(combo)  # 语法非法会抛出 ValueError

    def test_every_sample_card_renders(self):
        engine = TemplateEngine(self._load(os.path.join("config", "templates.yaml")))
        cards = load_cards(os.path.join(BASE_DIR, "data", "cards.xlsx"))
        self.assertGreaterEqual(len(cards), 10)

        hashes = set()
        for card in cards:
            template_id = card.get("template")
            self.assertTrue(engine.has_template(template_id), template_id)
            front = engine.render_front(template_id, card)
            back = engine.render_back(template_id, card)
            self.assertTrue(front.strip())
            self.assertTrue(back.strip())
            self.assertNotIn("{{", front)
            self.assertNotIn("{{", back)
            hashes.add(engine.card_hash(template_id, card))
        self.assertEqual(len(hashes), len(cards))

    def test_skins_cover_all_templates(self):
        config = self._load(os.path.join("config", "templates.yaml"))
        skins = config["skins"]
        for template_id, template in config["templates"].items():
            skin = (template.get("style") or {}).get("skin")
            with self.subTest(template=template_id):
                self.assertIn(skin, skins)


if __name__ == "__main__":
    unittest.main()
