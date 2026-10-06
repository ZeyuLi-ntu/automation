"""Append-only decisions/override revisions; atomic published snapshots."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS decisions (run_id TEXT, issue_id TEXT, fingerprint TEXT,
            payload TEXT, author TEXT, reason TEXT, at TEXT,
            PRIMARY KEY(run_id, issue_id, fingerprint));
        CREATE TABLE IF NOT EXISTS overrides (revision INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_key TEXT, payload TEXT, active INTEGER, author TEXT, reason TEXT, at TEXT);
        CREATE TABLE IF NOT EXISTS publications (run_id TEXT PRIMARY KEY, as_of TEXT, payload TEXT, at TEXT);
        """)

    def close(self):
        self.db.close()

    def decision(self, run, issue, fingerprint):
        row = self.db.execute("SELECT payload FROM decisions WHERE run_id=? AND issue_id=? AND fingerprint=?",
                              (run, issue, fingerprint)).fetchone()
        return json.loads(row[0]) if row else None

    def record_decision(self, run, issue, fingerprint, payload, author, reason):
        if not author.strip() or not reason.strip():
            raise ValueError("人工处理必须填写复核人和理由")
        with self.db:
            self.db.execute("INSERT INTO decisions VALUES(?,?,?,?,?,?,?)", (run, issue, fingerprint,
                            json.dumps(payload, ensure_ascii=False), author, reason, self.now()))

    def set_override(self, offer_key, patch, author, reason, active=True):
        # Price/description overrides do not silently retarget identity or expiry.
        if set(patch) - {"rate_pct", "product_name"}:
            raise ValueError("首版跨期修正支持利率/产品显示名；身份、条件、期限变更请建新记录并本期复核")
        if not author.strip() or not reason.strip():
            raise ValueError("人工修正必须填写人员及原因")
        with self.db:
            self.db.execute("INSERT INTO overrides(offer_key,payload,active,author,reason,at) VALUES(?,?,?,?,?,?)",
                            (offer_key, json.dumps(patch), int(active), author, reason, self.now()))

    def overrides(self):
        rows = self.db.execute("SELECT * FROM overrides WHERE revision IN (SELECT MAX(revision) FROM overrides GROUP BY offer_key)")
        return {r["offer_key"]: json.loads(r["payload"]) for r in rows if r["active"]}

    def previous(self, as_of):
        row = self.db.execute("SELECT payload FROM publications WHERE as_of < ? ORDER BY as_of DESC,at DESC LIMIT 1", (as_of,)).fetchone()
        return json.loads(row[0]) if row else {"offers": [], "order": {}}

    def publish(self, run, as_of, result):
        if result["pending"]:
            raise ValueError("仍有未处理记录，不能发布")
        with self.db:
            self.db.execute("INSERT INTO publications VALUES(?,?,?,?)", (run, as_of, json.dumps(result, ensure_ascii=False), self.now()))

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()
