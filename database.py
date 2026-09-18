import os
import sqlite3
import hashlib
from datetime import datetime, timezone


DB_PATH = os.getenv("DB_PATH", "bot.db")


def utc_now():
    return datetime.now(timezone.utc)


def utc_iso():
    return utc_now().isoformat()


def today():
    return utc_now().date().isoformat()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.executescript(
        """
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
            today_requests INTEGER NOT NULL DEFAULT 0,
            total_requests INTEGER NOT NULL DEFAULT 0,
            usage_date TEXT NOT NULL,
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
        """
    )

    conn.commit()
    conn.close()


def save_user(user_id, username=None, first_name=None):
    conn = get_db()

    row = conn.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if row:
        conn.execute(
            """
            UPDATE users
            SET username = ?,
                first_name = ?,
                last_seen = ?
            WHERE user_id = ?
            """,
            (username, first_name, utc_iso(), user_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO users
            (user_id, username, first_name, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                username,
                first_name,
                utc_iso(),
                utc_iso(),
            ),
        )

    conn.commit()
    conn.close()


def create_access_request(user_id, plan):
    conn = get_db()

    pending = conn.execute(
        """
        SELECT id
        FROM access_requests
        WHERE user_id = ?
        AND status = 'pending'
        """,
        (user_id,),
    ).fetchone()

    if pending:
        conn.close()
        return False, pending["id"]

    cur = conn.execute(
        """
        INSERT INTO access_requests
        (user_id, plan, status, created_at, updated_at)
        VALUES (?, ?, 'pending', ?, ?)
        """,
        (
            user_id,
            plan,
            utc_iso(),
            utc_iso(),
        ),
    )

    request_id = cur.lastrowid

    conn.commit()
    conn.close()

    return True, request_id


def get_access_request(request_id):
    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM access_requests
        WHERE id = ?
        """,
        (request_id,),
    ).fetchone()

    conn.close()

    return row


def update_access_request(request_id, status):
    conn = get_db()

    conn.execute(
        """
        UPDATE access_requests
        SET status = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (status, utc_iso(), request_id),
    )

    conn.commit()
    conn.close()


def hash_key(api_key):
    return hashlib.sha256(
        api_key.encode("utf-8")
    ).hexdigest()


def create_api_key(
    user_id,
    api_key,
    plan,
    daily_limit,
    expires_at,
):
    conn = get_db()

    key_hash = hash_key(api_key)
    key_prefix = api_key[:12]

    cur = conn.execute(
        """
        INSERT INTO api_keys
        (
            user_id,
            key_hash,
            key_prefix,
            plan,
            daily_limit,
            today_requests,
            total_requests,
            usage_date,
            status,
            created_at,
            expires_at
        )
        VALUES (?, ?, ?, ?, ?, 0, 0, ?, 'active', ?, ?)
        """,
        (
            user_id,
            key_hash,
            key_prefix,
            plan,
            daily_limit,
            today(),
            utc_iso(),
            expires_at,
        ),
    )

    key_id = cur.lastrowid

    conn.commit()
    conn.close()

    return key_id


def get_api_key(api_key):
    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM api_keys
        WHERE key_hash = ?
        AND status = 'active'
        """,
        (hash_key(api_key),),
    ).fetchone()

    conn.close()

    return row


def consume_api_request(api_key):
    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM api_keys
        WHERE key_hash = ?
        AND status = 'active'
        """,
        (hash_key(api_key),),
    ).fetchone()

    if not row:
        conn.close()
        return False, "invalid_key", None

    current_date = today()

    if row["usage_date"] != current_date:
        conn.execute(
            """
            UPDATE api_keys
            SET today_requests = 0,
                usage_date = ?
            WHERE id = ?
            """,
            (current_date, row["id"]),
        )

        conn.commit()

        row = conn.execute(
            """
            SELECT *
            FROM api_keys
            WHERE id = ?
            """,
            (row["id"],),
        ).fetchone()

    if row["today_requests"] >= row["daily_limit"]:
        conn.close()
        return False, "daily_limit", row

    conn.execute(
        """
        UPDATE api_keys
        SET today_requests = today_requests + 1,
            total_requests = total_requests + 1
        WHERE id = ?
        """,
        (row["id"],),
    )

    conn.commit()

    updated = conn.execute(
        """
        SELECT *
        FROM api_keys
        WHERE id = ?
        """,
        (row["id"],),
    ).fetchone()

    conn.close()

    return True, "ok", updated


def get_user_keys(user_id):
    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM api_keys
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,),
    ).fetchall()

    conn.close()

    return rows


def get_pending_requests():
    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            ar.*,
            u.username,
            u.first_name
        FROM access_requests ar
        LEFT JOIN users u
            ON ar.user_id = u.user_id
        WHERE ar.status = 'pending'
        ORDER BY ar.id ASC
        """
    ).fetchall()

    conn.close()

    return rows


def revoke_key(key_id):
    conn = get_db()

    cur = conn.execute(
        """
        UPDATE api_keys
        SET status = 'revoked'
        WHERE id = ?
        """,
        (key_id,),
    )

    conn.commit()

    changed = cur.rowcount

    conn.close()

    return changed > 0


def get_stats():
    conn = get_db()

    users = conn.execute(
        "SELECT COUNT(*) AS c FROM users"
    ).fetchone()["c"]

    active_keys = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM api_keys
        WHERE status = 'active'
        """
    ).fetchone()["c"]

    total_requests = conn.execute(
        """
        SELECT COALESCE(SUM(total_requests), 0) AS c
        FROM api_keys
        """
    ).fetchone()["c"]

    pending = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM access_requests
        WHERE status = 'pending'
        """
    ).fetchone()["c"]

    conn.close()

    return {
        "users": users,
        "active_keys": active_keys,
        "total_requests": total_requests,
        "pending": pending,
    }


def log_request(
    api_key_id,
    query,
    success,
    status_code,
):
    conn = get_db()

    conn.execute(
        """
        INSERT INTO request_logs
        (api_key_id, query, success, status_code, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            api_key_id,
            str(query)[:500],
            1 if success else 0,
            status_code,
            utc_iso(),
        ),
    )

    conn.commit()
    conn.close()


init_db()
