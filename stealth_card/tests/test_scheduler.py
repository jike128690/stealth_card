import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.scheduler import Scheduler

_TS_FMT = "%Y-%m-%d %H:%M:%S"


def hash_of(card):
    return card["h"]


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "progress.db")
        self.scheduler = Scheduler(self.db_path, intervals_minutes=[10, 720, 4320])

    def tearDown(self):
        self.scheduler.close()
        self._tmp.cleanup()

    def test_wal_mode_enabled(self):
        mode = self.scheduler._conn.execute("PRAGMA journal_mode;").fetchone()[0]
        self.assertEqual(mode.lower(), "wal")

    def test_record_shown_and_completed(self):
        self.scheduler.record_shown("h1", "tech_qa")
        state = self.scheduler.state_of("h1")
        self.assertEqual(state["review_count"], 1)
        self.assertEqual(state["familiarity"], 0)

        self.scheduler.record_completed("h1", "tech_qa")
        state = self.scheduler.state_of("h1")
        self.assertEqual(state["review_count"], 2)
        self.assertEqual(state["familiarity"], 1)
        next_at = datetime.strptime(state["next_review_at"], _TS_FMT)
        self.assertGreater(next_at, datetime.now())

    def test_familiarity_capped_at_two(self):
        for _ in range(4):
            self.scheduler.record_completed("h2", "tech_qa")
        self.assertEqual(self.scheduler.state_of("h2")["familiarity"], 2)

    def test_mark_unfamiliar_shortens_interval(self):
        self.scheduler.record_completed("h3", "tech_qa")
        self.scheduler.record_completed("h3", "tech_qa")
        self.assertEqual(self.scheduler.state_of("h3")["familiarity"], 2)

        self.scheduler.mark_unfamiliar("h3", "tech_qa")
        state = self.scheduler.state_of("h3")
        self.assertEqual(state["familiarity"], 0)
        actual = datetime.strptime(state["next_review_at"], _TS_FMT)
        expected = datetime.now() + timedelta(minutes=10)
        self.assertLess(abs((actual - expected).total_seconds()), 120)

    def test_build_queue_prioritizes_due_and_interleaves_new(self):
        cards = [{"h": f"h{i}", "template": "t"} for i in range(6)]
        self.scheduler.record_shown("h0", "t")
        self.scheduler.record_shown("h1", "t")
        self.scheduler.record_shown("h2", "t")
        self.scheduler._conn.execute(
            "UPDATE review_state SET next_review_at='2000-01-01 00:00:00', familiarity=0 "
            "WHERE card_hash='h0'"
        )
        self.scheduler._conn.execute(
            "UPDATE review_state SET next_review_at='2000-01-01 00:00:00', familiarity=2 "
            "WHERE card_hash='h1'"
        )
        self.scheduler._conn.execute(
            "UPDATE review_state SET next_review_at='2999-01-01 00:00:00' "
            "WHERE card_hash='h2'"
        )
        self.scheduler._conn.commit()
        self.scheduler._reload_states()

        queue = self.scheduler.build_queue(cards, hash_of)
        hashes = [card["h"] for card in queue]
        self.assertEqual(len(hashes), 6)
        self.assertEqual(hashes[0], "h0")  # 生疏到期卡片最优先
        self.assertEqual(hashes[1], "h1")  # 到期卡片其次
        self.assertLess(hashes.index("h3"), hashes.index("h2"))  # 新卡穿插在未到期卡之前
        self.assertEqual(hashes[-1], "h2")  # 未到期卡片排在最后

    def test_new_card_inserted_with_default_state(self):
        self.scheduler.record_shown("h4", "tech_qa")
        row = self.scheduler._conn.execute(
            "SELECT template_id, review_count, familiarity FROM review_state "
            "WHERE card_hash='h4'"
        ).fetchone()
        self.assertEqual(row[0], "tech_qa")
        self.assertEqual(row[1], 1)
        self.assertEqual(row[2], 0)


if __name__ == "__main__":
    unittest.main()
