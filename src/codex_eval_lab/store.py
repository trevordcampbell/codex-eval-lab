"""SQLite event/state store. Reservations precede execution; completion is atomic."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from .util import LabError, canonical, finite, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS variants(label TEXT PRIMARY KEY, source_hash TEXT NOT NULL, hypothesis TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trials(
 label TEXT NOT NULL, split TEXT NOT NULL, case_id TEXT NOT NULL, rep INTEGER NOT NULL,
 status TEXT NOT NULL, reserved REAL NOT NULL, charged REAL NOT NULL,
 result TEXT, started TEXT NOT NULL, finished TEXT,
 PRIMARY KEY(label, split, case_id, rep));
CREATE TABLE IF NOT EXISTS optimizers(
 id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT NOT NULL, started TEXT NOT NULL,
 result TEXT, finished TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
"""


class Store:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *args: Any) -> None:
        self.db.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key: str, value: Any) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, canonical(value)))
        self.db.commit()

    def event(self, kind: str, data: Any) -> None:
        self.db.execute("INSERT INTO events(at,kind,data) VALUES(?,?,?)", (utc_now(), kind, canonical(data)))
        self.db.commit()

    def variant(self, label: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM variants WHERE label=?", (label,)).fetchone()
        return dict(row) if row else None

    def variants(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute("SELECT * FROM variants ORDER BY created,label")]

    def add_variant(self, label: str, source_hash: str, hypothesis: str) -> None:
        if self.variant(label):
            raise LabError(f"Variant already exists: {label}")
        self.db.execute("INSERT INTO variants VALUES(?,?,?,?)", (label, source_hash, hypothesis, utc_now()))
        self.db.commit()

    def budget(self) -> dict[str, Any]:
        row = self.db.execute("SELECT COUNT(*) AS trials, COALESCE(SUM(charged),0) AS charged, COALESCE(SUM(CASE WHEN status='pending' THEN reserved ELSE 0 END),0) AS pending FROM trials").fetchone()
        calls = self.db.execute("SELECT COUNT(*) FROM optimizers").fetchone()[0]
        return {"trials": row["trials"], "eval_charged_usd": row["charged"], "pending_reserved_usd": row["pending"], "optimizer_calls": calls,
                "optimizer_dollars": None, "note": "Eval charges include conservative reservations for unknown costs. Optimizer dollars are separate and may be unknown."}

    def reserve(self, label: str, split: str, case_id: str, rep: int, budget: dict[str, Any]) -> bool:
        with self.transaction():
            row = self.db.execute("SELECT status FROM trials WHERE label=? AND split=? AND case_id=? AND rep=?", (label, split, case_id, rep)).fetchone()
            if row:
                if row[0] == "pending":
                    raise LabError("An interrupted trial has indeterminate cost/outcome. Use recover; it will NOT be retried for free.")
                return False
            totals = self.budget()
            if totals["trials"] >= budget["max_trials"]:
                raise LabError("Trial budget exhausted")
            reserve = budget["trial_reserve_usd"]
            if totals["eval_charged_usd"] + totals["pending_reserved_usd"] + reserve > budget["max_eval_cost_usd"] + 1e-9:
                raise LabError("Evaluation cost reservation would exceed the approved budget")
            self.db.execute("INSERT INTO trials VALUES(?,?,?,?,?,?,?,?,?,?)", (label, split, case_id, rep, "pending", reserve, 0, None, utc_now(), None))
        return True

    def complete(self, label: str, split: str, case_id: str, rep: int, result: dict[str, Any], charged: float) -> None:
        charged = finite(charged, "charged cost", minimum=0)
        with self.transaction():
            cur = self.db.execute("UPDATE trials SET status=?,charged=?,result=?,finished=? WHERE label=? AND split=? AND case_id=? AND rep=? AND status='pending'", (result["status"], charged, canonical(result), utc_now(), label, split, case_id, rep))
            if cur.rowcount != 1:
                raise LabError("Trial was not reserved, or was already completed")

    def results(self, label: str, split: str) -> list[dict[str, Any]]:
        return [json.loads(row[0]) for row in self.db.execute("SELECT result FROM trials WHERE label=? AND split=? AND result IS NOT NULL ORDER BY case_id,rep", (label, split))]

    def pending(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM trials WHERE status='pending'").fetchone()[0]

    def recover(self) -> int:
        rows = self.db.execute("SELECT * FROM trials WHERE status='pending'").fetchall()
        for row in rows:
            result = {"case_id": row["case_id"], "rep": row["rep"], "status": "indeterminate", "metrics": {}, "error": "Interrupted attempt; outcome/cost unknown. Full reservation charged; no automatic retry."}
            self.complete(row["label"], row["split"], row["case_id"], row["rep"], result, row["reserved"])
        self.db.execute("UPDATE optimizers SET status='indeterminate',finished=? WHERE status='pending'", (utc_now(),))
        self.db.commit()
        self.event("recovery", {"trials_marked_indeterminate": len(rows)})
        return len(rows)

    def begin_optimizer(self, max_calls: int) -> int:
        with self.transaction():
            if self.db.execute("SELECT COUNT(*) FROM optimizers").fetchone()[0] >= max_calls:
                raise LabError("Optimizer call budget exhausted")
            cur = self.db.execute("INSERT INTO optimizers(status,started) VALUES('pending',?)", (utc_now(),))
            return int(cur.lastrowid)

    def finish_optimizer(self, id_: int, status: str, result: Any) -> None:
        self.db.execute("UPDATE optimizers SET status=?,result=?,finished=? WHERE id=?", (status, canonical(result), utc_now(), id_))
        self.db.commit()
