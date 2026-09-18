import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, timezone


DB_PATH = os.getenv("DB_PATH", "bot.db")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            blocked INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS access_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            key_hash TEXT UNIQUE NOT NULL,
            plan TEXT NOT NULL,
            daily_limit INTEGER NOT NULL,
            today_requests INTEGER NOT NULL DEFAULT 0,
            total_requests INTEGER NOT NULL DEFAULT 0,
            last_request_date TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_id INTEGER NOT NULL,
            query TEXT,
            success INTEGER NOT NULL,
            status_code INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Migration for old databases
    try:
        cur.execute(
            "ALTER TABLE users ADD COLUMN blocked INTEGER DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


def save_user(chat_id, username="", first_name=""):
    conn = get_connection()

    conn.execute("""
        INSERT INTO users (
            chat_id,
            username,
            first_name,
            created_at
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chat_id)
        DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
    """, (
        chat_id,
        username or "",
        first_name or "",
        now_iso()
    ))

    conn.commit()
    conn.close()


def is_user_blocked(chat_id):
    conn = get_connection()

    row = conn.execute("""
        SELECT blocked
        FROM users
        WHERE chat_id = ?
    """, (chat_id,)).fetchone()

    conn.close()

    if not row:
        return False

    return bool(row["blocked"])


def block_user(chat_id):
    conn = get_connection()

    conn.execute("""
        UPDATE users
        SET blocked = 1
        WHERE chat_id = ?
    """, (chat_id,))

    conn.commit()
    conn.close()


def unblock_user(chat_id):
    conn = get_connection()

    conn.execute("""
        UPDATE users
        SET blocked = 0
        WHERE chat_id = ?
    """, (chat_id,))

    conn.commit()
    conn.close()


def get_users(limit=30):
    conn = get_connection()

    rows = conn.execute("""
        SELECT *
        FROM users
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def create_request(chat_id, plan):
    conn = get_connection()

    cur = conn.execute("""
        INSERT INTO access_requests (
            chat_id,
            plan,
            status,
            created_at
        )
        VALUES (?, ?, 'pending', ?)
    """, (
        chat_id,
        plan,
        now_iso()
    ))

    request_id = cur.lastrowid

    conn.commit()
    conn.close()

    return request_id


def get_request(request_id):
    conn = get_connection()

    row = conn.execute("""
        SELECT *
        FROM access_requests
        WHERE id = ?
    """, (request_id,)).fetchone()

    conn.close()

    return dict(row) if row else None


def get_pending_requests(limit=30):
    conn = get_connection()

    rows = conn.execute("""
        SELECT *
        FROM access_requests
        WHERE status = 'pending'
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def update_request(request_id, status):
    conn = get_connection()

    conn.execute("""
        UPDATE access_requests
        SET status = ?
        WHERE id = ?
    """, (
        status,
        request_id
    ))

    conn.commit()
    conn.close()


def hash_key(api_key):
    return hashlib.sha256(
        api_key.encode("utf-8")
    ).hexdigest()


def create_api_key(
    chat_id,
    plan,
    daily_limit,
    days=30
):
    raw_key = (
        "KCE_"
        + secrets.token_urlsafe(32)
    )

    key_hash = hash_key(raw_key)

    from datetime import timedelta

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(days=days)
    ).isoformat()

    conn = get_connection()

    cur = conn.execute("""
        INSERT INTO api_keys (
            chat_id,
            key_hash,
            plan,
            daily_limit,
            expires_at,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        chat_id,
        key_hash,
        plan,
        daily_limit,
        expires_at,
        now_iso()
    ))

    key_id = cur.lastrowid

    conn.commit()
    conn.close()

    return raw_key, key_id


def get_api_key(raw_key):
    conn = get_connection()

    row = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE key_hash = ?
        AND status = 'active'
    """, (
        hash_key(raw_key),
    )).fetchone()

    conn.close()

    return dict(row) if row else None


def consume_request(raw_key):
    conn = get_connection()

    row = conn.execute("""
        SELECT
            api_keys.*,
            users.blocked
        FROM api_keys
        LEFT JOIN users
            ON users.chat_id = api_keys.chat_id
        WHERE api_keys.key_hash = ?
        AND api_keys.status = 'active'
    """, (
        hash_key(raw_key),
    )).fetchone()

    if not row:
        conn.close()
        return False, "invalid", None

    key = dict(row)

    if key.get("blocked"):
        conn.close()
        return False, "blocked", key

    today = datetime.now(
        timezone.utc
    ).date().isoformat()

    if key["last_request_date"] != today:
        today_requests = 0
    else:
        today_requests = key["today_requests"]

    if today_requests >= key["daily_limit"]:
        conn.close()
        return False, "daily_limit", key

    today_requests += 1
    total_requests = (
        key["total_requests"] + 1
    )

    conn.execute("""
        UPDATE api_keys
        SET
            today_requests = ?,
            total_requests = ?,
            last_request_date = ?
        WHERE id = ?
    """, (
        today_requests,
        total_requests,
        today,
        key["id"]
    ))

    conn.commit()

    updated = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE id = ?
    """, (
        key["id"],
    )).fetchone()

    conn.close()

    return True, "ok", dict(updated)


def get_user_keys(chat_id):
    conn = get_connection()

    rows = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE chat_id = ?
        ORDER BY id DESC
    """, (
        chat_id,
    )).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def get_all_keys(limit=50):
    conn = get_connection()

    rows = conn.execute("""
        SELECT *
        FROM api_keys
        ORDER BY id DESC
        LIMIT ?
    """, (
        limit,
    )).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def revoke_key(key_id):
    conn = get_connection()

    cur = conn.execute("""
        UPDATE api_keys
        SET status = 'revoked'
        WHERE id = ?
    """, (
        key_id,
    ))

    changed = cur.rowcount

    conn.commit()
    conn.close()

    return changed > 0


def log_request(
    api_key_id,
    query,
    success,
    status_code
):
    conn = get_connection()

    conn.execute("""
        INSERT INTO request_logs (
            api_key_id,
            query,
            success,
            status_code,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        api_key_id,
        query,
        1 if success else 0,
        status_code,
        now_iso()
    ))

    conn.commit()
    conn.close()


def get_usage_stats():
    conn = get_connection()

    users = conn.execute(
        "SELECT COUNT(*) AS c FROM users"
    ).fetchone()["c"]

    blocked = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE blocked = 1"
    ).fetchone()["c"]

    keys = conn.execute(
        "SELECT COUNT(*) AS c FROM api_keys"
    ).fetchone()["c"]

    active_keys = conn.execute(
        "SELECT COUNT(*) AS c FROM api_keys WHERE status = 'active'"
    ).fetchone()["c"]

    requests = conn.execute(
        "SELECT COUNT(*) AS c FROM request_logs"
    ).fetchone()["c"]

    successful = conn.execute(
        "SELECT COUNT(*) AS c FROM request_logs WHERE success = 1"
    ).fetchone()["c"]

    pending = conn.execute("""
        SELECT COUNT(*) AS c
        FROM access_requests
        WHERE status = 'pending'
    """).fetchone()["c"]

    total_usage = conn.execute("""
        SELECT COALESCE(SUM(total_requests), 0) AS c
        FROM api_keys
    """).fetchone()["c"]

    conn.close()

    return {
        "users": users,
        "blocked": blocked,
        "keys": keys,
        "active_keys": active_keys,
        "requests": requests,
        "successful": successful,
        "pending": pending,
        "total_usage": total_usage,
    }


def get_recent_logs(limit=20):
    conn = get_connection()

    rows = conn.execute("""
        SELECT *
        FROM request_logs
        ORDER BY id DESC
        LIMIT ?
    """, (
        limit,
    )).fetchall()

    conn.close()

    return [dict(row) for row in rows]
