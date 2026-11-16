"""SQLite WAL 学习状态存储与基于熟练度的卡片抽题调度（对应需求 6.1 / 开发计划 2.3）。"""

import logging
import os
import sqlite3
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

_TS_FMT = "%Y-%m-%d %H:%M:%S"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_state (
    card_hash      TEXT PRIMARY KEY,
    template_id    TEXT DEFAULT 'tech_qa',
    review_count   INTEGER DEFAULT 0,
    familiarity    INTEGER DEFAULT 0,
    next_review_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


class Scheduler:
    """复习状态读写与抽题队列构建，全部调用均在 GUI 主线程内完成。"""

    def __init__(self, db_path: str, intervals_minutes=(10, 720, 4320)):
        self._intervals = [
            timedelta(minutes=max(1, int(minutes))) for minutes in intervals_minutes
        ]
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(_SCHEMA)
        self._conn.commit()
        self._states = {}
        self._reload_states()

    def _reload_states(self):
        rows = self._conn.execute(
            "SELECT card_hash, template_id, review_count, familiarity, next_review_at "
            "FROM review_state"
        ).fetchall()
        self._states = {
            row[0]: {
                "template_id": row[1],
                "review_count": int(row[2] or 0),
                "familiarity": int(row[3] or 0),
                "next_review_at": str(row[4] or ""),
            }
            for row in rows
        }

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime(_TS_FMT)

    def _interval_for(self, familiarity: int) -> timedelta:
        index = min(max(int(familiarity), 0), len(self._intervals) - 1)
        return self._intervals[index]

    def state_of(self, card_hash: str):
        return self._states.get(card_hash)

    def record_shown(self, card_hash: str, template_id: str):
        """累计复习展示次数（首次展示或翻页进入时调用）"""
        now = self._now()
        state = self._states.get(card_hash)
        if state is None:
            self._conn.execute(
                "INSERT INTO review_state "
                "(card_hash, template_id, review_count, familiarity, next_review_at) "
                "VALUES (?, ?, 1, 0, ?)",
                (card_hash, template_id, now),
            )
            self._states[card_hash] = {
                "template_id": template_id,
                "review_count": 1,
                "familiarity": 0,
                "next_review_at": now,
            }
        else:
            state["review_count"] += 1
            self._conn.execute(
                "UPDATE review_state SET review_count = ? WHERE card_hash = ?",
                (state["review_count"], card_hash),
            )
        self._conn.commit()

    def record_completed(self, card_hash: str, template_id: str):
        """展开态确认已读：熟练度晋级，并按新等级顺延下次复习时间"""
        state = self._states.get(card_hash)
        if state is None:
            self.record_shown(card_hash, template_id)
            state = self._states[card_hash]
        state["review_count"] += 1
        state["familiarity"] = min(2, int(state["familiarity"]) + 1)
        next_at = (datetime.now() + self._interval_for(state["familiarity"])).strftime(_TS_FMT)
        state["next_review_at"] = next_at
        self._conn.execute(
            "UPDATE review_state SET review_count = ?, familiarity = ?, next_review_at = ? "
            "WHERE card_hash = ?",
            (state["review_count"], state["familiarity"], next_at, card_hash),
        )
        self._conn.commit()

    def mark_unfamiliar(self, card_hash: str, template_id: str):
        """Alt+M：标记生疏，缩短下次复习间隔"""
        state = self._states.get(card_hash)
        if state is None:
            self.record_shown(card_hash, template_id)
            state = self._states[card_hash]
        state["familiarity"] = 0
        next_at = (datetime.now() + self._interval_for(0)).strftime(_TS_FMT)
        state["next_review_at"] = next_at
        self._conn.execute(
            "UPDATE review_state SET familiarity = 0, next_review_at = ? WHERE card_hash = ?",
            (next_at, card_hash),
        )
        self._conn.commit()

    def build_queue(self, cards: list, hash_of) -> list:
        """到期未复习与生疏卡片优先，新卡片按工作表顺序 2:1 穿插推送"""
        now = self._now()
        due, fresh, later = [], [], []
        for card in cards:
            state = self._states.get(hash_of(card))
            if state is None:
                fresh.append(card)
            elif str(state["next_review_at"]) <= now:
                due.append((card, state))
            else:
                later.append((card, state))

        due.sort(
            key=lambda pair: (
                int(pair[1]["familiarity"]),
                str(pair[1]["next_review_at"]),
            )
        )

        queue = []
        due_index = fresh_index = 0
        while due_index < len(due) or fresh_index < len(fresh):
            for _ in range(2):
                if due_index < len(due):
                    queue.append(due[due_index][0])
                    due_index += 1
            if fresh_index < len(fresh):
                queue.append(fresh[fresh_index])
                fresh_index += 1

        later.sort(key=lambda pair: str(pair[1]["next_review_at"]))
        queue.extend(card for card, _ in later)
        return queue

    def close(self):
        try:
            self._conn.commit()
            self._conn.close()
        except Exception:
            log.debug("数据库关闭异常", exc_info=True)
