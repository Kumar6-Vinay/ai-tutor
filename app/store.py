"""SQLite persistence. Identity (children) is kept apart from learning data
(learners, sessions), which reference only the pseudonymous child id."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS children (
  id TEXT PRIMARY KEY, nickname TEXT NOT NULL, grade INTEGER NOT NULL, board TEXT NOT NULL,
  age_band TEXT NOT NULL, consent_at REAL NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS learners (child_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, child_id TEXT NOT NULL, data TEXT NOT NULL, updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS sessions_child ON sessions(child_id);
"""


class Store:
    def __init__(self, path: str = "tutor.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    # identity
    def create_child(self, nickname: str, grade: int, board: str, age_band: str) -> dict:
        cid = uuid.uuid4().hex
        now = time.time()
        self._exec("INSERT INTO children VALUES (?,?,?,?,?,?,?)", (cid, nickname, grade, board, age_band, now, now))
        return self.get_child(cid)

    def get_child(self, cid: str) -> Optional[dict]:
        row = self._exec("SELECT * FROM children WHERE id=?", (cid,)).fetchone()
        return dict(row) if row else None

    def delete_child(self, cid: str) -> None:
        """Parent deletes everything about the child."""
        for t, col in (("sessions", "child_id"), ("learners", "child_id"), ("children", "id")):
            self._exec(f"DELETE FROM {t} WHERE {col}=?", (cid,))

    # learning data
    def get_learner(self, cid: str) -> dict:
        row = self._exec("SELECT data FROM learners WHERE child_id=?", (cid,)).fetchone()
        return json.loads(row["data"]) if row else {}

    def save_learner(self, cid: str, data: dict) -> None:
        self._exec("INSERT INTO learners VALUES (?,?,?) ON CONFLICT(child_id) DO UPDATE SET data=excluded.data, "
                   "updated=excluded.updated", (cid, json.dumps(data), time.time()))

    def get_session(self, sid: str) -> Optional[dict]:
        row = self._exec("SELECT data FROM sessions WHERE id=?", (sid,)).fetchone()
        return json.loads(row["data"]) if row else None

    def save_session(self, data: dict) -> None:
        self._exec("INSERT INTO sessions VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data, "
                   "updated=excluded.updated", (data["id"], data["child_id"], json.dumps(data), time.time()))
