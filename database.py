import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, timezone


DB_PATH = os.getenv("DB_PATH", "bot.db")

APP_NAME = "KRUTIK CYBER EXPERT API"


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
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            processed_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            key_hash TEXT UNIQUE NOT NULL,
            key_name TEXT DEFAULT 'API KEY',
            plan TEXT DEFAULT 'custom',
            daily_limit INTEGER NOT NULL DEFAULT 1000,
            today_requests INTEGER NOT NULL DEFAULT 0,
            total_limit INTEGER,
            total_requests INTEGER NOT NULL DEFAULT 0,
            last_request_date TEXT,
            start_at TEXT,
            expires_at TEXT,
            rate_limit INTEGER,
            rate_window_start TEXT,
            rate_window_count INTEGER DEFAULT 0,
            last_used_at TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_id INTEGER,
            chat_id INTEGER,
            query TEXT,
            success INTEGER NOT NULL,
            status_code INTEGER NOT NULL,
            error TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    migrations = [
        ("users", "blocked", "INTEGER DEFAULT 0"),
        ("users", "api_enabled", "INTEGER DEFAULT 1"),

        ("access_requests", "username", "TEXT DEFAULT ''"),
        ("access_requests", "processed_at", "TEXT"),

        ("api_keys", "key_name", "TEXT DEFAULT 'API KEY'"),
        ("api_keys", "total_limit", "INTEGER"),
        ("api_keys", "start_at", "TEXT"),
        ("api_keys", "rate_limit", "INTEGER"),
        ("api_keys", "rate_window_start", "TEXT"),
        ("api_keys", "rate_window_count", "INTEGER DEFAULT 0"),
        ("api_keys", "last_used_at", "TEXT"),

        ("request_logs", "chat_id", "INTEGER"),
        ("request_logs", "error", "TEXT DEFAULT ''"),
    ]

    for table, column, definition in migrations:
        try:
            cur.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )
        except sqlite3.OperationalError:
            pass

    defaults = {
        "global_api_enabled": "1",

        "welcome_text": (
            "🔥 KRUTIK CYBER EXPERT API\n\n"
            "Welcome!\n\n"
            "Choose an option below:"
        ),

        "support_text": (
            "🆘 Support\n\n"
            "Contact the owner for support."
        ),

        "howto_text": (
            "📖 How to Use API\n\n"
            "Use GET /api/search with your API key "
            "and query."
        ),

        "docs_text": (
            "📚 API Documentation\n\n"
            "GET /api/search\n"
            "GET /api/status\n"
            "GET /api/stats"
        ),

        "basic_daily": "1000",
        "basic_days": "30",

        "pro_daily": "10000",
        "pro_days": "30",

        "custom_daily": "50000",
        "custom_days": "30",

        "api_url": (
            "https://krutik-cyber-expert-api.onrender.com"
        ),

        "button_plans": "🔑 API Plans",
        "button_request": "🚀 Request API Access",
        "button_keys": "🔐 My API Keys",
        "button_usage": "📊 My Usage",
        "button_howto": "📖 How to Use API",
        "button_docs": "📚 API Docs",
        "button_support": "🆘 Support",
    }

    for key, value in defaults.items():
        cur.execute("""
            INSERT OR IGNORE INTO settings(key, value)
            VALUES (?, ?)
        """, (key, value))

    conn.commit()
    conn.close()


# =========================================================
# SETTINGS
# =========================================================

def get_setting(key, default=""):
    conn = get_connection()

    row = conn.execute("""
        SELECT value
        FROM settings
        WHERE key = ?
    """, (key,)).fetchone()

    conn.close()

    if not row:
        return default

    return row["value"]


def set_setting(key, value):
    conn = get_connection()

    conn.execute("""
        INSERT INTO settings(key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
    """, (
        key,
        str(value),
    ))

    conn.commit()
    conn.close()


def get_all_settings():
    conn = get_connection()

    rows = conn.execute("""
        SELECT key, value
        FROM settings
        ORDER BY key
    """).fetchall()

    conn.close()

    return {
        row["key"]: row["value"]
        for row in rows
    }


# =========================================================
# USERS
# =========================================================

def save_user(chat_id, username="", first_name=""):
    conn = get_connection()

    conn.execute("""
        INSERT INTO users(
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


def get_users(limit=100):
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
    return bool(user and user.get("blocked"))


def block_user(chat_id):
    conn = get_connection()

    conn.execute("""
        INSERT INTO users(
            chat_id,
            blocked,
            api_enabled,
            created_at
        )
        VALUES (?, 1, 0, ?)
        ON CONFLICT(chat_id)
        DO UPDATE SET blocked = 1
    """, (
        int(chat_id),
        now_iso(),
    ))

    conn.commit()
    conn.close()


def unblock_user(chat_id):
    conn = get_connection()

    conn.execute("""
        UPDATE users
        SET blocked = 0
        WHERE chat_id = ?
    """, (int(chat_id),))

    conn.commit()
    conn.close()


def set_api_enabled(chat_id, enabled):
    conn = get_connection()

    conn.execute("""
        INSERT INTO users(
            chat_id,
            api_enabled,
            created_at
        )
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id)
        DO UPDATE SET api_enabled = excluded.api_enabled
    """, (
        int(chat_id),
        1 if enabled else 0,
        now_iso(),
    ))

    conn.commit()
    conn.close()


def api_on(chat_id):
    set_api_enabled(chat_id, True)


def api_off(chat_id):
    set_api_enabled(chat_id, False)


# =========================================================
# GLOBAL API
# =========================================================

def set_global_api_enabled(enabled):
    set_setting(
        "global_api_enabled",
        "1" if enabled else "0",
    )


def is_global_api_enabled():
    return get_setting(
        "global_api_enabled",
        "1",
    ) == "1"


# =========================================================
# ACCESS REQUESTS
# =========================================================

def create_access_request(
    chat_id,
    username,
    plan,
):
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
        INSERT INTO access_requests(
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
        ORDER BY id DESC
        LIMIT ?
    """, (int(limit),)).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def update_access_request(request_id, status):
    conn = get_connection()

    conn.execute("""
        UPDATE access_requests
        SET status = ?, processed_at = ?
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

def hash_key(raw_key):
    return hashlib.sha256(
        raw_key.encode("utf-8")
    ).hexdigest()


def create_api_key(
    chat_id,
    plan="custom",
    key_name="API KEY",
    daily_limit=1000,
    total_limit=None,
    start_at=None,
    expires_at=None,
    rate_limit=None,
):
    raw_key = (
        "KCE_"
        + secrets.token_urlsafe(32)
    )

    key_hash = hash_key(raw_key)

    now = now_iso()

    conn = get_connection()

    cur = conn.execute("""
        INSERT INTO api_keys(
            chat_id,
            key_hash,
            key_name,
            plan,
            daily_limit,
            today_requests,
            total_limit,
            total_requests,
            last_request_date,
            start_at,
            expires_at,
            rate_limit,
            rate_window_start,
            rate_window_count,
            last_used_at,
            status,
            created_at
        )
        VALUES (
            ?, ?, ?, ?, ?,
            0, ?, 0, ?,
            ?, ?, ?,
            NULL, 0, NULL,
            'active', ?
        )
    """, (
        int(chat_id),
        key_hash,
        key_name or "API KEY",
        plan,
        max(1, int(daily_limit)),
        (
            int(total_limit)
            if total_limit is not None
            else None
        ),
        datetime.now(timezone.utc).date().isoformat(),
        start_at,
        expires_at,
        (
            int(rate_limit)
            if rate_limit is not None
            else None
        ),
        now,
    ))

    key_id = cur.lastrowid

    conn.commit()
    conn.close()

    return raw_key, key_id


def get_api_key(raw_key):
    if not raw_key:
        return None

    conn = get_connection()

    row = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE key_hash = ?
    """, (
        hash_key(raw_key),
    )).fetchone()

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
            users.first_name
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
        AND status = 'active'
    """, (int(key_id),))

    changed = cur.rowcount

    conn.commit()
    conn.close()

    return changed > 0


def delete_key(key_id):
    conn = get_connection()

    cur = conn.execute("""
        DELETE FROM api_keys
        WHERE id = ?
    """, (int(key_id),))

    changed = cur.rowcount

    conn.execute("""
        DELETE FROM request_logs
        WHERE api_key_id = ?
    """, (int(key_id),))

    conn.commit()
    conn.close()

    return changed > 0


# =========================================================
# REQUEST CONSUMPTION
# =========================================================

def consume_api_request(raw_key):
    conn = get_connection()

    row = conn.execute("""
        SELECT
            api_keys.*,
            users.blocked,
            users.api_enabled
        FROM api_keys
        LEFT JOIN users
            ON users.chat_id = api_keys.chat_id
        WHERE api_keys.key_hash = ?
    """, (
        hash_key(raw_key),
    )).fetchone()

    if not row:
        conn.close()
        return False, "invalid_api_key", None

    key = dict(row)

    if key["status"] != "active":
        conn.close()
        return False, "invalid_api_key", key

    if key.get("blocked"):
        conn.close()
        return False, "user_blocked", key

    if key.get("api_enabled", 1) == 0:
        conn.close()
        return False, "api_access_disabled", key

    if not is_global_api_enabled():
        conn.close()
        return False, "maintenance_mode", key

    now = datetime.now(timezone.utc)

    if key.get("start_at"):
        try:
            start = datetime.fromisoformat(
                key["start_at"]
            )

            if now < start:
                conn.close()
                return False, "not_started", key

        except Exception:
            pass

    if key.get("expires_at"):
        try:
            expiry = datetime.fromisoformat(
                key["expires_at"]
            )

            if now >= expiry:
                conn.execute("""
                    UPDATE api_keys
                    SET status = 'expired'
                    WHERE id = ?
                """, (key["id"],))

                conn.commit()
                conn.close()

                return False, "expired", key

        except Exception:
            pass

    today = now.date().isoformat()

    if key.get("last_request_date") != today:
        key["today_requests"] = 0

        conn.execute("""
            UPDATE api_keys
            SET
                today_requests = 0,
                last_request_date = ?
            WHERE id = ?
        """, (
            today,
            key["id"],
        ))

    if key["today_requests"] >= key["daily_limit"]:
        conn.commit()
        conn.close()
        return False, "daily_limit", key

    if (
        key.get("total_limit") is not None
        and key["total_requests"] >= key["total_limit"]
    ):
        conn.commit()
        conn.close()
        return False, "total_limit", key

    rate_limit = key.get("rate_limit")

    if rate_limit:
        current_minute = now.replace(
            second=0,
            microsecond=0,
        ).isoformat()

        if key.get("rate_window_start") != current_minute:
            rate_count = 0
        else:
            rate_count = key.get(
                "rate_window_count",
                0,
            )

        if rate_count >= rate_limit:
            conn.commit()
            conn.close()
            return False, "rate_limit", key

        new_rate_count = rate_count + 1
        rate_window_start = current_minute

    else:
        new_rate_count = key.get(
            "rate_window_count",
            0,
        )
        rate_window_start = key.get(
            "rate_window_start"
        )

    new_today = key["today_requests"] + 1
    new_total = key["total_requests"] + 1
    last_used = now.isoformat()

    conn.execute("""
        UPDATE api_keys
        SET
            today_requests = ?,
            total_requests = ?,
            last_request_date = ?,
            rate_window_start = ?,
            rate_window_count = ?,
            last_used_at = ?
        WHERE id = ?
    """, (
        new_today,
        new_total,
        today,
        rate_window_start,
        new_rate_count,
        last_used,
        key["id"],
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


# =========================================================
# LOGS
# =========================================================

def log_request(
    api_key_id,
    chat_id,
    query,
    success,
    status_code,
    error="",
):
    conn = get_connection()

    conn.execute("""
        INSERT INTO request_logs(
            api_key_id,
            chat_id,
            query,
            success,
            status_code,
            error,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        api_key_id,
        chat_id,
        query or "",
        1 if success else 0,
        int(status_code),
        error or "",
        now_iso(),
    ))

    conn.commit()
    conn.close()


def get_recent_logs(limit=50):
    conn = get_connection()

    rows = conn.execute("""
        SELECT
            request_logs.*,
            api_keys.key_name
        FROM request_logs
        LEFT JOIN api_keys
            ON api_keys.id = request_logs.api_key_id
        ORDER BY request_logs.id DESC
        LIMIT ?
    """, (int(limit),)).fetchall()

    conn.close()

    return [dict(row) for row in rows]


# =========================================================
# STATISTICS
# =========================================================

def get_usage_stats():
    conn = get_connection()

    users = conn.execute(
        "SELECT COUNT(*) AS c FROM users"
    ).fetchone()["c"]

    blocked = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE blocked = 1"
    ).fetchone()["c"]

    api_enabled = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE api_enabled = 1"
    ).fetchone()["c"]

    keys = conn.execute(
        "SELECT COUNT(*) AS c FROM api_keys"
    ).fetchone()["c"]

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
        "keys": keys,
        "active_keys": active_keys,
        "revoked_keys": revoked_keys,
        "expired_keys": expired_keys,
        "requests": requests,
        "successful": successful,
        "failed": failed,
        "pending": pending,
        "total_usage": total_usage,
        "global_api_enabled": is_global_api_enabled(),
    }
