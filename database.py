import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, timezone, timedelta


DB_PATH = os.getenv("DB_PATH", "bot.db")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    return conn


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            blocked INTEGER DEFAULT 0,
            api_enabled INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS access_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            username TEXT DEFAULT '',
            plan TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            processed_at TEXT
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
            api_key_id INTEGER,
            query TEXT,
            success INTEGER NOT NULL DEFAULT 0,
            status_code INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # =====================================================
    # MIGRATIONS
    # =====================================================

    # users.blocked
    try:
        cur.execute(
            "ALTER TABLE users ADD COLUMN blocked INTEGER DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass

    # users.api_enabled
    try:
        cur.execute(
            "ALTER TABLE users ADD COLUMN api_enabled INTEGER DEFAULT 1"
        )
    except sqlite3.OperationalError:
        pass

    # Old schema compatibility: user_id -> chat_id
    # This is mainly for fresh/known schema. Existing incompatible
    # databases should be backed up before migration.
    conn.commit()
    conn.close()


# =========================================================
# USERS
# =========================================================

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
        int(chat_id),
        username or "",
        first_name or "",
        now_iso(),
    ))

    conn.commit()
    conn.close()


def get_user(chat_id):
    conn = get_connection()

    row = conn.execute("""
        SELECT *
        FROM users
        WHERE chat_id = ?
    """, (int(chat_id),)).fetchone()

    conn.close()

    return dict(row) if row else None


def get_users(limit=50):
    conn = get_connection()

    rows = conn.execute("""
        SELECT *
        FROM users
        ORDER BY created_at DESC
        LIMIT ?
    """, (int(limit),)).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def is_user_blocked(chat_id):
    user = get_user(chat_id)

    if not user:
        return False

    return bool(user.get("blocked", 0))


def block_user(chat_id):
    conn = get_connection()

    cur = conn.execute("""
        UPDATE users
        SET blocked = 1
        WHERE chat_id = ?
    """, (int(chat_id),))

    conn.commit()
    conn.close()

    return cur.rowcount > 0


def unblock_user(chat_id):
    conn = get_connection()

    cur = conn.execute("""
        UPDATE users
        SET blocked = 0
        WHERE chat_id = ?
    """, (int(chat_id),))

    conn.commit()
    conn.close()

    return cur.rowcount > 0


# =========================================================
# API ON / OFF
# =========================================================

def is_api_enabled(chat_id):
    user = get_user(chat_id)

    if not user:
        return True

    return bool(user.get("api_enabled", 1))


def set_api_enabled(chat_id, enabled):
    conn = get_connection()

    cur = conn.execute("""
        UPDATE users
        SET api_enabled = ?
        WHERE chat_id = ?
    """, (
        1 if enabled else 0,
        int(chat_id),
    ))

    conn.commit()
    conn.close()

    return cur.rowcount > 0


def api_on(chat_id):
    return set_api_enabled(chat_id, True)


def api_off(chat_id):
    return set_api_enabled(chat_id, False)


# =========================================================
# ACCESS REQUESTS
# =========================================================

def create_access_request(chat_id, username, plan):
    conn = get_connection()

    existing = conn.execute("""
        SELECT id
        FROM access_requests
        WHERE chat_id = ?
        AND status = 'pending'
        LIMIT 1
    """, (int(chat_id),)).fetchone()

    if existing:
        conn.close()
        return existing["id"]

    cur = conn.execute("""
        INSERT INTO access_requests (
            chat_id,
            username,
            plan,
            status,
            created_at
        )
        VALUES (?, ?, ?, 'pending', ?)
    """, (
        int(chat_id),
        username or "",
        plan,
        now_iso(),
    ))

    request_id = cur.lastrowid

    conn.commit()
    conn.close()

    return request_id


def get_access_request(request_id):
    conn = get_connection()

    row = conn.execute("""
        SELECT *
        FROM access_requests
        WHERE id = ?
    """, (int(request_id),)).fetchone()

    conn.close()

    return dict(row) if row else None


def get_pending_requests(limit=50):
    conn = get_connection()

    rows = conn.execute("""
        SELECT *
        FROM access_requests
        WHERE status = 'pending'
        ORDER BY id ASC
        LIMIT ?
    """, (int(limit),)).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def update_access_request(request_id, status):
    conn = get_connection()

    conn.execute("""
        UPDATE access_requests
        SET
            status = ?,
            processed_at = ?
        WHERE id = ?
    """, (
        status,
        now_iso(),
        int(request_id),
    ))

    conn.commit()
    conn.close()


# =========================================================
# API KEYS
# =========================================================

PLANS = {
    "basic": {
        "daily_limit": 1000,
        "days": 30,
    },
    "pro": {
        "daily_limit": 10000,
        "days": 30,
    },
    "custom": {
        "daily_limit": 50000,
        "days": 30,
    },
}


def hash_key(raw_key):
    return hashlib.sha256(
        raw_key.encode("utf-8")
    ).hexdigest()


def create_api_key(
    chat_id,
    plan,
    daily_limit=None,
    days=None,
    revoke_previous=True,
):
    plan = plan.lower().strip()

    if plan not in PLANS:
        plan = "basic"

    if daily_limit is None:
        daily_limit = PLANS[plan]["daily_limit"]

    if days is None:
        days = PLANS[plan]["days"]

    raw_key = (
        "KCE_"
        + secrets.token_urlsafe(32)
    )

    key_hash = hash_key(raw_key)

    now = datetime.now(timezone.utc)

    expires_at = (
        now + timedelta(days=int(days))
    ).isoformat()

    conn = get_connection()

    if revoke_previous:
        conn.execute("""
            UPDATE api_keys
            SET status = 'revoked'
            WHERE chat_id = ?
            AND status = 'active'
        """, (int(chat_id),))

    cur = conn.execute("""
        INSERT INTO api_keys (
            chat_id,
            key_hash,
            plan,
            daily_limit,
            today_requests,
            total_requests,
            last_request_date,
            status,
            expires_at,
            created_at
        )
        VALUES (?, ?, ?, ?, 0, 0, ?, 'active', ?, ?)
    """, (
        int(chat_id),
        key_hash,
        plan,
        int(daily_limit),
        now.date().isoformat(),
        expires_at,
        now.isoformat(),
    ))

    key_id = cur.lastrowid

    conn.commit()
    conn.close()

    return raw_key, key_id


def get_api_key(raw_key):
    key_hash = hash_key(raw_key)

    conn = get_connection()

    row = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE key_hash = ?
        LIMIT 1
    """, (key_hash,)).fetchone()

    conn.close()

    return dict(row) if row else None


def get_key_by_id(key_id):
    conn = get_connection()

    row = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE id = ?
    """, (int(key_id),)).fetchone()

    conn.close()

    return dict(row) if row else None


def consume_api_request(raw_key):
    key_hash = hash_key(raw_key)

    conn = get_connection()

    row = conn.execute("""
        SELECT
            api_keys.*,
            COALESCE(users.blocked, 0) AS blocked,
            COALESCE(users.api_enabled, 1) AS api_enabled
        FROM api_keys
        LEFT JOIN users
            ON users.chat_id = api_keys.chat_id
        WHERE api_keys.key_hash = ?
        LIMIT 1
    """, (key_hash,)).fetchone()

    if not row:
        conn.close()
        return False, "invalid_api_key", None

    key = dict(row)

    if key["status"] != "active":
        conn.close()
        return False, "invalid_api_key", key

    if key.get("blocked"):
        conn.close()
        return False, "blocked", key

    if not key.get("api_enabled", 1):
        conn.close()
        return False, "api_disabled", key

    now = datetime.now(timezone.utc)

    try:
        expires = datetime.fromisoformat(
            key["expires_at"]
        )

        if expires < now:
            conn.execute("""
                UPDATE api_keys
                SET status = 'expired'
                WHERE id = ?
            """, (key["id"],))

            conn.commit()
            conn.close()

            key["status"] = "expired"

            return False, "expired", key

    except Exception:
        pass

    today = now.date().isoformat()

    if key["last_request_date"] != today:
        today_requests = 0
    else:
        today_requests = key["today_requests"]

    if today_requests >= key["daily_limit"]:
        conn.close()
        return False, "daily_limit", key

    new_today = today_requests + 1
    new_total = key["total_requests"] + 1

    conn.execute("""
        UPDATE api_keys
        SET
            today_requests = ?,
            total_requests = ?,
            last_request_date = ?
        WHERE id = ?
    """, (
        new_today,
        new_total,
        today,
        key["id"],
    ))

    conn.commit()

    updated = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE id = ?
    """, (key["id"],)).fetchone()

    conn.close()

    return True, "ok", dict(updated)


def get_user_keys(chat_id):
    conn = get_connection()

    rows = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE chat_id = ?
        ORDER BY id DESC
    """, (int(chat_id),)).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def get_all_keys(limit=100):
    conn = get_connection()

    rows = conn.execute("""
        SELECT
            api_keys.*,
            users.username,
            users.first_name,
            users.blocked,
            users.api_enabled
        FROM api_keys
        LEFT JOIN users
            ON users.chat_id = api_keys.chat_id
        ORDER BY api_keys.id DESC
        LIMIT ?
    """, (int(limit),)).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def revoke_key(key_id):
    conn = get_connection()

    cur = conn.execute("""
        UPDATE api_keys
        SET status = 'revoked'
        WHERE id = ?
    """, (int(key_id),))

    conn.commit()
    conn.close()

    return cur.rowcount > 0


def delete_key(key_id):
    conn = get_connection()

    cur = conn.execute("""
        DELETE FROM api_keys
        WHERE id = ?
    """, (int(key_id),))

    conn.commit()
    conn.close()

    return cur.rowcount > 0


# =========================================================
# LOGS / USAGE
# =========================================================

def log_request(
    api_key_id,
    query,
    success,
    status_code,
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
        int(status_code),
        now_iso(),
    ))

    conn.commit()
    conn.close()


def get_recent_logs(limit=30):
    conn = get_connection()

    rows = conn.execute("""
        SELECT
            request_logs.*,
            api_keys.chat_id,
            api_keys.plan
        FROM request_logs
        LEFT JOIN api_keys
            ON api_keys.id = request_logs.api_key_id
        ORDER BY request_logs.id DESC
        LIMIT ?
    """, (int(limit),)).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def get_usage_stats():
    conn = get_connection()

    users = conn.execute("""
        SELECT COUNT(*) AS c
        FROM users
    """).fetchone()["c"]

    blocked = conn.execute("""
        SELECT COUNT(*) AS c
        FROM users
        WHERE blocked = 1
    """).fetchone()["c"]

    api_enabled = conn.execute("""
        SELECT COUNT(*) AS c
        FROM users
        WHERE api_enabled = 1
    """).fetchone()["c"]

    api_disabled = conn.execute("""
        SELECT COUNT(*) AS c
        FROM users
        WHERE api_enabled = 0
    """).fetchone()["c"]

    keys = conn.execute("""
        SELECT COUNT(*) AS c
        FROM api_keys
    """).fetchone()["c"]

    active_keys = conn.execute("""
        SELECT COUNT(*) AS c
        FROM api_keys
        WHERE status = 'active'
    """).fetchone()["c"]

    revoked_keys = conn.execute("""
        SELECT COUNT(*) AS c
        FROM api_keys
        WHERE status = 'revoked'
    """).fetchone()["c"]

    expired_keys = conn.execute("""
        SELECT COUNT(*) AS c
        FROM api_keys
        WHERE status = 'expired'
    """).fetchone()["c"]

    requests = conn.execute("""
        SELECT COUNT(*) AS c
        FROM request_logs
    """).fetchone()["c"]

    successful = conn.execute("""
        SELECT COUNT(*) AS c
        FROM request_logs
        WHERE success = 1
    """).fetchone()["c"]

    failed = conn.execute("""
        SELECT COUNT(*) AS c
        FROM request_logs
        WHERE success = 0
    """).fetchone()["c"]

    pending = conn.execute("""
        SELECT COUNT(*) AS c
        FROM access_requests
        WHERE status = 'pending'
    """).fetchone()["c"]

    total_usage = conn.execute("""
        SELECT COALESCE(
            SUM(total_requests),
            0
        ) AS c
        FROM api_keys
    """).fetchone()["c"]

    conn.close()

    return {
        "users": users,
        "blocked": blocked,
        "api_enabled": api_enabled,
        "api_disabled": api_disabled,
        "keys": keys,
        "active_keys": active_keys,
        "revoked_keys": revoked_keys,
        "expired_keys": expired_keys,
        "requests": requests,
        "successful": successful,
        "failed": failed,
        "pending": pending,
        "total_usage": total_usage,
    }
