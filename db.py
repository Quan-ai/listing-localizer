import json
import os
import sqlite3
import threading

from config import DAILY_FREE_LIMIT, DATABASE_PATH

_local = threading.local()


def get_db() -> sqlite3.Connection:
    """Return thread-local database connection with WAL mode."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def init_db():
    """Create tables and indexes. Safe to call multiple times."""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email           TEXT UNIQUE NOT NULL,
            password_hash   TEXT NOT NULL,
            is_pro          INTEGER NOT NULL DEFAULT 0,
            stripe_customer_id       TEXT,
            stripe_subscription_id   TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS daily_usage (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL REFERENCES users(id),
            date      TEXT NOT NULL,
            count     INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, date)
        );

        CREATE INDEX IF NOT EXISTS idx_usage_user_date
            ON daily_usage(user_id, date);

        CREATE TABLE IF NOT EXISTS generations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL REFERENCES users(id),
            input_type    TEXT NOT NULL,
            input_summary TEXT,
            style         TEXT NOT NULL DEFAULT 'balanced',
            discount      INTEGER,
            markets       TEXT NOT NULL,
            result_json   TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_generations_user_ts
            ON generations(user_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS signup_ips (
            ip      TEXT PRIMARY KEY,
            count   INTEGER NOT NULL DEFAULT 1
        );
    """
    )
    conn.commit()


# ---------- User CRUD ----------


def db_create_user(email: str, password_hash: str) -> dict:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO users(email, password_hash) VALUES(?, ?)",
        (email, password_hash),
    )
    conn.commit()
    return dict(
        conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    )


def db_get_user_by_id(user_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def db_get_user_by_email(email: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    return dict(row) if row else None


def db_set_pro_status(
    user_id: int,
    is_pro: bool,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
):
    conn = get_db()
    conn.execute(
        "UPDATE users SET is_pro=?, stripe_customer_id=?, stripe_subscription_id=? WHERE id=?",
        (1 if is_pro else 0, stripe_customer_id, stripe_subscription_id, user_id),
    )
    conn.commit()


def db_set_pro_status_by_subscription(subscription_id: str, is_pro: bool):
    conn = get_db()
    conn.execute(
        "UPDATE users SET is_pro=? WHERE stripe_subscription_id=?",
        (1 if is_pro else 0, subscription_id),
    )
    conn.commit()


# ---------- Daily Usage ----------


def _local_today() -> str:
    from datetime import datetime, timezone, timedelta

    from config import LOCAL_UTC_OFFSET

    now = datetime.now(timezone.utc) + timedelta(hours=LOCAL_UTC_OFFSET)
    return now.strftime("%Y-%m-%d")


def check_and_increment_daily_usage(
    user_id: int, is_pro: bool
) -> tuple[bool, int, int]:
    """Returns (allowed: bool, used: int, limit: int). Increments count if allowed."""
    if is_pro:
        return (True, 0, 999_999)

    today = _local_today()
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        "SELECT count FROM daily_usage WHERE user_id=? AND date=?",
        (user_id, today),
    ).fetchone()

    current = row["count"] if row else 0
    allowed = current < DAILY_FREE_LIMIT

    if allowed:
        conn.execute(
            "INSERT INTO daily_usage(user_id, date, count) VALUES(?, ?, 1) "
            "ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1",
            (user_id, today),
        )
    conn.commit()

    used = current + 1 if allowed else current
    return (allowed, used, DAILY_FREE_LIMIT)


def get_todays_usage(user_id: int, is_pro: bool) -> tuple[int, int]:
    """Returns (used: int, limit: int) without incrementing."""
    if is_pro:
        return (0, 999_999)

    today = _local_today()
    conn = get_db()
    row = conn.execute(
        "SELECT count FROM daily_usage WHERE user_id=? AND date=?",
        (user_id, today),
    ).fetchone()

    current = row["count"] if row else 0
    return (current, DAILY_FREE_LIMIT)


# ---------- Generations ----------


def db_save_generation(
    user_id: int,
    input_type: str,
    input_summary: str,
    style: str,
    discount: int | None,
    markets: list[str],
    result_json: str,
) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO generations(user_id, input_type, input_summary, style, discount, markets, result_json) "
        "VALUES(?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            input_type,
            input_summary,
            style,
            discount,
            json.dumps(markets),
            result_json,
        ),
    )
    conn.commit()
    return cur.lastrowid


def db_get_generations(
    user_id: int, limit: int = 20, offset: int = 0
) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, input_type, input_summary, style, markets, created_at "
        "FROM generations WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (user_id, limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def db_get_generation_by_id(gen_id: int, user_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM generations WHERE id=? AND user_id=?", (gen_id, user_id)
    ).fetchone()
    if row:
        d = dict(row)
        d["markets"] = json.loads(d["markets"])
        d["result_json"] = json.loads(d["result_json"])
        return d
    return None


def db_get_generation_count(user_id: int) -> int:
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM generations WHERE user_id=?", (user_id,)
    ).fetchone()
    return row["cnt"]


# ---------- Signup IP tracking ----------


def db_check_signup_ip(ip: str, max_allowed: int = 2) -> bool:
    conn = get_db()
    row = conn.execute("SELECT count FROM signup_ips WHERE ip=?", (ip,)).fetchone()
    return (row["count"] if row else 0) < max_allowed


def db_record_signup_ip(ip: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO signup_ips(ip, count) VALUES(?, 1) "
        "ON CONFLICT(ip) DO UPDATE SET count = count + 1",
        (ip,),
    )
    conn.commit()
