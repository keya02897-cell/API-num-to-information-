import os
import sqlite3
import hashlib
from datetime import datetime, timezone


DB_PATH = os.getenv("DB_PATH", "bot.db")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        created_at TEXT NOT NULL,
        last_seen TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS access_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        plan TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        key_hash TEXT NOT NULL UNIQUE,
        key_prefix TEXT NOT NULL,
        plan TEXT NOT NULL,
        daily_limit INTEGER NOT NULL,
        total_requests INTEGER NOT NULL DEFAULT 0,
        today_requests INTEGER NOT NULL DEFAULT 0,
        usage_date TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        expires_at TEXT
    );

    CREATE TABLE IF NOT EXISTS request_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key_id INTEGER,
        query TEXT,
        success INTEGER NOT NULL DEFAULT 0,
        status_code INTEGER,
        created_at TEXT NOT NULL
    );
    """)

    conn.commit()
    conn.close()


def upsert_user(user_id, username=None, first_name=None):
    conn = get_connection()

    existing = conn.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE users
            SET username = ?,
                first_name = ?,
                last_seen = ?
            WHERE user_id = ?
        """, (
            username,
            first_name,
            now_iso(),
            user_id
        ))
    else:
        conn.execute("""
            INSERT INTO users
            (user_id, username, first_name, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            username,
            first_name,
            now_iso(),
            now_iso()
        ))

    conn.commit()
    conn.close()


def create_access_request(user_id, plan):
    conn = get_connection()

    # Avoid duplicate pending request
    pending = conn.execute("""
        SELECT id
        FROM access_requests
        WHERE user_id = ?
        AND status = 'pending'
    """, (user_id,)).fetchone()

    if pending:
        conn.close()
        return False, pending["id"]

    cur = conn.execute("""
        INSERT INTO access_requests
        (user_id, plan, status, created_at, updated_at)
        VALUES (?, ?, 'pending', ?, ?)
    """, (
        user_id,
        plan,
        now_iso(),
        now_iso()
    ))

    request_id = cur.lastrowid

    conn.commit()
    conn.close()

    return True, request_id


def get_access_request(request_id):
    conn = get_connection()

    row = conn.execute("""
        SELECT *
        FROM access_requests
        WHERE id = ?
    """, (request_id,)).fetchone()

    conn.close()
    return row


def update_access_request(request_id, status):
    conn = get_connection()

    conn.execute("""
        UPDATE access_requests
        SET status = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        status,
        now_iso(),
        request_id
    ))

    conn.commit()
    conn.close()


def hash_api_key(api_key):
    return hashlib.sha256(
        api_key.encode("utf-8")
    ).hexdigest()


def create_api_key(
    user_id,
    api_key,
    plan,
    daily_limit,
    expires_at=None
):
    key_hash = hash_api_key(api_key)
    key_prefix = api_key[:12]

    conn = get_connection()

    cur = conn.execute("""
        INSERT INTO api_keys
        (
            user_id,
            key_hash,
            key_prefix,
            plan,
            daily_limit,
            total_requests,
            today_requests,
            usage_date,
            status,
            created_at,
            expires_at
        )
        VALUES (?, ?, ?, ?, ?, 0, 0, ?, 'active', ?, ?)
    """, (
        user_id,
        key_hash,
        key_prefix,
        plan,
        daily_limit,
        datetime.now(timezone.utc).date().isoformat(),
        now_iso(),
        expires_at
    ))

    key_id = cur.lastrowid

    conn.commit()
    conn.close()

    return key_id


def get_api_key(api_key):
    key_hash = hash_api_key(api_key)

    conn = get_connection()

    row = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE key_hash = ?
        AND status = 'active'
    """, (key_hash,)).fetchone()

    conn.close()

    return row


def reset_daily_usage_if_needed(conn, key_row):
    today = datetime.now(timezone.utc).date().isoformat()

    if key_row["usage_date"] != today:
        conn.execute("""
            UPDATE api_keys
            SET today_requests = 0,
                usage_date = ?
            WHERE id = ?
        """, (
            today,
            key_row["id"]
        ))

        conn.commit()

        return 0

    return key_row["today_requests"]


def consume_request(api_key):
    key_hash = hash_api_key(api_key)

    conn = get_connection()

    row = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE key_hash = ?
        AND status = 'active'
    """, (key_hash,)).fetchone()

    if not row:
        conn.close()
        return False, "invalid_key", None

    today_count = reset_daily_usage_if_needed(
        conn,
        row
    )

    if today_count >= row["daily_limit"]:
        conn.close()
        return False, "daily_limit", row

    conn.execute("""
        UPDATE api_keys
        SET today_requests = today_requests + 1,
            total_requests = total_requests + 1
        WHERE id = ?
    """, (row["id"],))

    conn.commit()

    updated = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE id = ?
    """, (row["id"],)).fetchone()

    conn.close()

    return True, "ok", updated


def get_user_keys(user_id):
    conn = get_connection()

    rows = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,)).fetchall()

    conn.close()

    return rows


def revoke_key(key_id):
    conn = get_connection()

    cur = conn.execute("""
        UPDATE api_keys
        SET status = 'revoked'
        WHERE id = ?
    """, (key_id,))

    conn.commit()
    changed = cur.rowcount

    conn.close()

    return changed > 0


def get_pending_requests():
    conn = get_connection()

    rows = conn.execute("""
        SELECT
            ar.*,
            u.username,
            u.first_name
        FROM access_requests ar
        LEFT JOIN users u
            ON u.user_id = ar.user_id
        WHERE ar.status = 'pending'
        ORDER BY ar.id ASC
    """).fetchall()

    conn.close()

    return rows


def get_stats():
    conn = get_connection()

    users = conn.execute(
        "SELECT COUNT(*) AS c FROM users"
    ).fetchone()["c"]

    active_keys = conn.execute("""
        SELECT COUNT(*) AS c
        FROM api_keys
        WHERE status = 'active'
    """).fetchone()["c"]

    requests = conn.execute("""
        SELECT COALESCE(SUM(total_requests), 0) AS c
        FROM api_keys
    """).fetchone()["c"]

    pending = conn.execute("""
        SELECT COUNT(*) AS c
        FROM access_requests
        WHERE status = 'pending'
    """).fetchone()["c"]

    conn.close()

    return {
        "users": users,
        "active_keys": active_keys,
        "total_requests": requests,
        "pending_requests": pending
    }


def log_request(api_key_id, query, success, status_code):
    conn = get_connection()

    conn.execute("""
        INSERT INTO request_logs
        (api_key_id, query, success, status_code, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        api_key_id,
        query[:500],
        1 if success else 0,
        status_code,
        now_iso()
    ))

    conn.commit()
    conn.close()


init_db()
