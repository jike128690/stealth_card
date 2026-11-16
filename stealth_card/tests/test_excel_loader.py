import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl

from engine.excel_loader import append_card, load_cards


class ExcelLoaderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.xlsx_path = os.path.join(self._tmp.name, "cards.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "tech_qa"
        ws.append(["title", "tag", "core"])
        ws.append(["TCP 三次握手", "网络", "SYN/SYN+ACK/ACK"])
        ws.append([None, None, None])
        ws.append(["GIL", None, "全局解释器锁"])
        ws2 = wb.create_sheet("vocab")
        ws2.append(["template", "word", "meaning"])
        ws2.append(["cmd_cheat", "git stash", "暂存改动"])
        ws2.append([None, "robust", "强健的"])
        wb.save(self.xlsx_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_multi_sheet_and_filter_missing(self):
        cards = load_cards(self.xlsx_path)
        self.assertEqual(len(cards), 4)

        self.assertEqual(cards[0]["template"], "tech_qa")
        self.assertEqual(cards[0]["title"], "TCP 三次握手")
        self.assertEqual(cards[0]["tag"], "网络")

        # 空单元格被过滤，不产生 tag 键
        self.assertNotIn("tag", cards[1])
        self.assertEqual(cards[1]["core"], "全局解释器锁")

        # 单表混排：template 列覆盖工作表名
        self.assertEqual(cards[2]["template"], "cmd_cheat")
        self.assertEqual(cards[2]["word"], "git stash")

        # template 列为空时回退到工作表名
        self.assertEqual(cards[3]["template"], "vocab")
        self.assertEqual(cards[3]["word"], "robust")

    def test_load_csv(self):
        csv_path = os.path.join(self._tmp.name, "my_vocab.csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as fp:
            fp.write("word,meaning\nobscure,难懂的\n")
        cards = load_cards(csv_path)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["template"], "my_vocab")
        self.assertEqual(cards[0]["meaning"], "难懂的")

    def test_append_card_creates_sheet(self):
        ok = append_card(self.xlsx_path, "capture", {"title": "摘录", "content": "某段文字"})
        self.assertTrue(ok)
        cards = load_cards(self.xlsx_path)
        captured = [c for c in cards if c["template"] == "capture"]
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["title"], "摘录")
        self.assertEqual(captured[0]["content"], "某段文字")

    def test_append_card_existing_sheet(self):
        ok = append_card(self.xlsx_path, "tech_qa", {"title": "新题", "core": "答案"})
        self.assertTrue(ok)
        cards = load_cards(self.xlsx_path)
        tech = [c for c in cards if c["template"] == "tech_qa"]
        self.assertEqual(len(tech), 3)
        self.assertEqual(tech[-1]["title"], "新题")

    def test_missing_file_returns_empty(self):
        self.assertEqual(load_cards(os.path.join(self._tmp.name, "ghost.xlsx")), [])


if __name__ == "__main__":
    unittest.main()
