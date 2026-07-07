"""SQLite persistence layer: conversation history, long-term facts, scheduled jobs."""

import os
import sqlite3
import threading
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "memory.db")

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_lock = threading.Lock()

_conn.executescript("""
CREATE TABLE IF NOT EXISTS memory (
    user_id TEXT,
    role TEXT,
    content TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    fact TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT,
    prompt TEXT,
    schedule_type TEXT,        -- 'once' | 'daily' | 'every'
    daily_time TEXT,           -- 'HH:MM' UTC, for 'daily'
    interval_minutes INTEGER,  -- for 'every'
    next_run TEXT,             -- ISO timestamp UTC
    active INTEGER DEFAULT 1
);
""")
_conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- conversation history ----------

def save_message(user_id, role: str, content: str) -> None:
    with _lock:
        _conn.execute(
            "INSERT INTO memory (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (str(user_id), role, content, _now()),
        )
        _conn.commit()


def load_recent_messages(user_id, limit: int = 20) -> list[dict]:
    with _lock:
        rows = _conn.execute(
            "SELECT role, content FROM memory WHERE user_id=? ORDER BY rowid DESC LIMIT ?",
            (str(user_id), limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# ---------- long-term facts ----------

def add_fact(user_id, fact: str) -> int:
    with _lock:
        cur = _conn.execute(
            "INSERT INTO facts (user_id, fact, created_at) VALUES (?, ?, ?)",
            (str(user_id), fact, _now()),
        )
        _conn.commit()
        return cur.lastrowid


def list_facts(user_id) -> list[dict]:
    with _lock:
        rows = _conn.execute(
            "SELECT id, fact FROM facts WHERE user_id=? ORDER BY id",
            (str(user_id),),
        ).fetchall()
    return [{"id": r["id"], "fact": r["fact"]} for r in rows]


def delete_fact(user_id, fact_id: int) -> bool:
    with _lock:
        cur = _conn.execute(
            "DELETE FROM facts WHERE user_id=? AND id=?", (str(user_id), fact_id)
        )
        _conn.commit()
        return cur.rowcount > 0


# ---------- scheduled jobs ----------

def add_job(chat_id, prompt: str, schedule_type: str, next_run: str,
            daily_time: str | None = None, interval_minutes: int | None = None) -> int:
    with _lock:
        cur = _conn.execute(
            "INSERT INTO jobs (chat_id, prompt, schedule_type, daily_time, interval_minutes, next_run) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(chat_id), prompt, schedule_type, daily_time, interval_minutes, next_run),
        )
        _conn.commit()
        return cur.lastrowid


def list_jobs(chat_id) -> list[dict]:
    with _lock:
        rows = _conn.execute(
            "SELECT id, prompt, schedule_type, daily_time, interval_minutes, next_run "
            "FROM jobs WHERE chat_id=? AND active=1 ORDER BY id",
            (str(chat_id),),
        ).fetchall()
    return [dict(r) for r in rows]


def cancel_job(chat_id, job_id: int) -> bool:
    with _lock:
        cur = _conn.execute(
            "UPDATE jobs SET active=0 WHERE chat_id=? AND id=? AND active=1",
            (str(chat_id), job_id),
        )
        _conn.commit()
        return cur.rowcount > 0


def due_jobs() -> list[dict]:
    with _lock:
        rows = _conn.execute(
            "SELECT id, chat_id, prompt, schedule_type, daily_time, interval_minutes "
            "FROM jobs WHERE active=1 AND next_run <= ?",
            (_now(),),
        ).fetchall()
    return [dict(r) for r in rows]


def reschedule_job(job_id: int, next_run: str) -> None:
    with _lock:
        _conn.execute("UPDATE jobs SET next_run=? WHERE id=?", (next_run, job_id))
        _conn.commit()


def deactivate_job(job_id: int) -> None:
    with _lock:
        _conn.execute("UPDATE jobs SET active=0 WHERE id=?", (job_id,))
        _conn.commit()
