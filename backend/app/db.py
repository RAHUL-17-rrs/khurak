"""SQLite persistence (stdlib sqlite3; zero setup). JSON columns hold traces."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

from .config import DB_PATH

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
  id TEXT PRIMARY KEY, name TEXT, age INT, gender TEXT, city TEXT, language TEXT, voice TEXT,
  call_time TEXT, phone_masked TEXT, family_json TEXT, regimen TEXT, story TEXT, noise_json TEXT,
  name_local TEXT, name_hi TEXT, start_day INT DEFAULT 1, active INT DEFAULT 1
);
CREATE TABLE IF NOT EXISTS calls (
  id TEXT PRIMARY KEY, patient_id TEXT, day INT, attempt INT, kind TEXT, state TEXT, stage TEXT,
  status TEXT, rule TEXT, rule_text TEXT, reasons_json TEXT, actions_json TEXT, memory_json TEXT,
  trace_json TEXT, source TEXT, mode TEXT, scheduled_for TEXT, started_at TEXT, ended_at TEXT,
  seeded INT DEFAULT 0
);
CREATE INDEX IF NOT EXISTS calls_patient_day ON calls(patient_id, day);
CREATE TABLE IF NOT EXISTS turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT, call_id TEXT, idx INT, stage TEXT,
  prompt_json TEXT, answer_audio TEXT, transcript TEXT, understanding_json TEXT, evon_json TEXT,
  stt_ms INT, stt_mock INT, source TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, call_id TEXT, day INT, level TEXT,
  rule TEXT, reason TEXT, quote TEXT, created_at TEXT, resolved INT DEFAULT 0, resolved_at TEXT,
  resolution TEXT
);
CREATE TABLE IF NOT EXISTS daily_status (
  patient_id TEXT, day INT, status TEXT, note TEXT, call_id TEXT, PRIMARY KEY (patient_id, day)
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


_con = _connect()
_con.executescript(SCHEMA)


@contextmanager
def tx():
    with _lock:
        try:
            yield _con
            _con.commit()
        except Exception:
            _con.rollback()
            raise


def q(sql: str, *args) -> list[dict]:
    with _lock:
        return [dict(r) for r in _con.execute(sql, args).fetchall()]


def q1(sql: str, *args) -> dict | None:
    rows = q(sql, *args)
    return rows[0] if rows else None


def ex(sql: str, *args) -> int:
    with tx() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def unj(s, default=None):
    if s is None:
        return default
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default


def kv_get(k: str, default=None):
    r = q1("SELECT v FROM kv WHERE k=?", k)
    return unj(r["v"], default) if r else default


def kv_set(k: str, v) -> None:
    ex("INSERT INTO kv(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", k, j(v))


def reset() -> None:
    with tx() as c:
        for t in ("patients", "calls", "turns", "alerts", "daily_status", "kv"):
            c.execute(f"DELETE FROM {t}")


# ----------------------------------------------------------------------------- row helpers


def patient_row(r: dict) -> dict:
    r = dict(r)
    r["family"] = unj(r.pop("family_json"), {})
    r["noise"] = unj(r.pop("noise_json"), None)
    return r


def call_row(r: dict) -> dict:
    r = dict(r)
    for k in ("reasons", "actions", "memory", "trace"):
        r[k] = unj(r.pop(f"{k}_json"), None)
    return r


def turn_row(r: dict) -> dict:
    r = dict(r)
    r["prompt"] = unj(r.pop("prompt_json"), None)
    r["understanding"] = unj(r.pop("understanding_json"), None)
    r["evon"] = unj(r.pop("evon_json"), None)
    return r
