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
CREATE TABLE IF NOT EXISTS paired_cohorts(
 id TEXT PRIMARY KEY, spec TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paired_trials(
 cohort TEXT NOT NULL, label TEXT NOT NULL, split TEXT NOT NULL, case_id TEXT NOT NULL, rep INTEGER NOT NULL,
 status TEXT NOT NULL, reserved REAL NOT NULL, charged REAL NOT NULL,
 result TEXT, started TEXT NOT NULL, finished TEXT,
 PRIMARY KEY(cohort, label, split, case_id, rep));
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

    def record_manual_selection(self, candidate: str, decision: dict[str, Any], *, promoted: bool) -> None:
        """Commit the promotion and its audit record atomically, including rejected attempts."""
        with self.transaction():
            if promoted:
                self.db.execute("INSERT OR REPLACE INTO meta VALUES('best',?)", (canonical(candidate),))
            self.db.execute("INSERT INTO events(at,kind,data) VALUES(?,?,?)",
                            (utc_now(), "manual_selection", canonical({**decision, "promoted": promoted})))

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
        row = self.db.execute("SELECT COUNT(*) AS trials, COALESCE(SUM(charged),0) AS charged, COALESCE(SUM(CASE WHEN status='pending' THEN reserved ELSE 0 END),0) AS pending FROM (SELECT status,charged,reserved FROM trials UNION ALL SELECT status,charged,reserved FROM paired_trials)").fetchone()
        calls = self.db.execute("SELECT COUNT(*) FROM optimizers").fetchone()[0]
        return {"trials": row["trials"], "eval_charged_usd": row["charged"], "pending_reserved_usd": row["pending"], "optimizer_calls": calls,
                "optimizer_dollars": None, "note": "Eval charges include conservative reservations for unknown costs. Optimizer dollars are separate and may be unknown."}

    def cohort(self, id_: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT spec FROM paired_cohorts WHERE id=?", (id_,)).fetchone()
        return json.loads(row[0]) if row else None

    def add_cohort(self, id_: str, spec: dict[str, Any]) -> None:
        # A persisted specification is append-only; never replace measurement history.
        with self.transaction():
            current = self.cohort(id_)
            if current is not None:
                if current != spec:
                    raise LabError("Paired cohort specification changed; start a new experiment")
                return
            self.db.execute("INSERT INTO paired_cohorts VALUES(?,?,?)", (id_, canonical(spec), utc_now()))

    def _trial_key(self, label, split, case_id, rep, cohort):
        if cohort is None:
            return "trials", "label=? AND split=? AND case_id=? AND rep=?", (label, split, case_id, rep)
        spec = self.cohort(cohort)
        if not spec or label not in spec["arms"] or split != spec["split"]:
            raise LabError("Trial must belong to a persisted paired cohort")
        return "paired_trials", "cohort=? AND label=? AND split=? AND case_id=? AND rep=?", (cohort, label, split, case_id, rep)

    def reserve(self, label: str, split: str, case_id: str, rep: int, budget: dict[str, Any], *, cohort: str | None = None) -> bool:
        table, where, key = self._trial_key(label, split, case_id, rep, cohort)
        with self.transaction():
            row = self.db.execute(f"SELECT status FROM {table} WHERE {where}", key).fetchone()
            if row:
                if row[0] == "pending":
                    raise LabError("An interrupted trial has indeterminate cost/outcome. Use recover; it will NOT be retried for free.")
                return False
            totals = self.budget()
            final_reserve = self.get("protected_final_trials", 0) if split != "test" else 0
            if totals["trials"] + final_reserve >= budget["max_trials"]:
                raise LabError("Trial budget exhausted")
            reserve = budget["trial_reserve_usd"]
            if totals["eval_charged_usd"] + totals["pending_reserved_usd"] + reserve * (1 + final_reserve) > budget["max_eval_cost_usd"] + 1e-9:
                raise LabError("Evaluation cost reservation would exceed the approved budget")
            values = (*key, "pending", reserve, 0, None, utc_now(), None)
            self.db.execute(f"INSERT INTO {table} VALUES({','.join('?' for _ in values)})", values)
        return True

    def complete(self, label: str, split: str, case_id: str, rep: int, result: dict[str, Any], charged: float, *, cohort: str | None = None) -> None:
        charged = finite(charged, "charged cost", minimum=0)
        table, where, key = self._trial_key(label, split, case_id, rep, cohort)
        with self.transaction():
            cur = self.db.execute(f"UPDATE {table} SET status=?,charged=?,result=?,finished=? WHERE {where} AND status='pending'", (result["status"], charged, canonical(result), utc_now(), *key))
            if cur.rowcount != 1:
                raise LabError("Trial was not reserved, or was already completed")

    def results(self, label: str, split: str, *, cohort: str | None = None) -> list[dict[str, Any]]:
        table = "trials" if cohort is None else "paired_trials"
        where = "label=? AND split=?" if cohort is None else "cohort=? AND label=? AND split=?"
        key = (label, split) if cohort is None else (cohort, label, split)
        return [json.loads(row[0]) for row in self.db.execute(f"SELECT result FROM {table} WHERE {where} AND result IS NOT NULL ORDER BY case_id,rep", key)]

    def cohort_statuses(self, cohort: str) -> dict[tuple[str, str, int], str]:
        return {(r["label"], r["case_id"], r["rep"]): r["status"] for r in self.db.execute("SELECT * FROM paired_trials WHERE cohort=?", (cohort,))}

    def pending(self) -> int:
        return sum(self.db.execute(f"SELECT COUNT(*) FROM {table} WHERE status='pending'").fetchone()[0] for table in ("trials", "paired_trials"))

    def recover(self) -> int:
        count = 0
        for table in ("trials", "paired_trials"):
            rows = self.db.execute(f"SELECT * FROM {table} WHERE status='pending'").fetchall()
            for row in rows:
                result = {"case_id": row["case_id"], "rep": row["rep"], "status": "indeterminate", "metrics": {}, "error": "Interrupted attempt; outcome/cost unknown. Full reservation charged; no automatic retry."}
                self.complete(row["label"], row["split"], row["case_id"], row["rep"], result, row["reserved"], cohort=row["cohort"] if table == "paired_trials" else None)
            count += len(rows)
        self.db.execute("UPDATE optimizers SET status='indeterminate',finished=? WHERE status='pending'", (utc_now(),))
        self.db.commit()
        self.event("recovery", {"trials_marked_indeterminate": count})
        return count

    def unresolved_optimizers(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM optimizers WHERE status IN ('pending','indeterminate')").fetchone()[0]

    def begin_optimizer(self, max_calls: int) -> int:
        with self.transaction():
            if self.unresolved_optimizers():
                raise LabError("Optimizer execution is unresolved; preserve its response and charges, do not silently dispatch another call")
            if self.db.execute("SELECT COUNT(*) FROM optimizers").fetchone()[0] >= max_calls:
                raise LabError("Optimizer call budget exhausted")
            cur = self.db.execute("INSERT INTO optimizers(status,started) VALUES('pending',?)", (utc_now(),))
            return int(cur.lastrowid)

    def finish_optimizer(self, id_: int, status: str, result: Any) -> None:
        self.db.execute("UPDATE optimizers SET status=?,result=?,finished=? WHERE id=?", (status, canonical(result), utc_now(), id_))
        self.db.commit()
