import os
import json
import secrets
import hashlib
import sqlite3
import asyncio
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)


# =========================================================
# KRUTIK CYBER EXPERT
# API + TELEGRAM BOT
# =========================================================

APP_NAME = "KRUTIK CYBER EXPERT API"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID", "").strip()

PORT = int(os.getenv("PORT", "10000"))

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))

DB_PATH = os.getenv("DB_PATH", "bot.db")


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title="KRUTIK CYBER EXPERT Bot Service",
    version="1.0.0",
    description="Authorized synthetic-data API",
)


# =========================================================
# DATABASE
# =========================================================

def db_connection():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = db_connection()

    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS access_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            username TEXT,
            plan TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            processed_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            key_hash TEXT UNIQUE NOT NULL,
            plan TEXT NOT NULL,
            daily_limit INTEGER NOT NULL,
            today_requests INTEGER NOT NULL DEFAULT 0,
            total_requests INTEGER NOT NULL DEFAULT 0,
            usage_date TEXT NOT NULL,
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
            success INTEGER,
            status_code INTEGER,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()

    conn.close()


# =========================================================
# USERS
# =========================================================

def save_user(
    user_id,
    username,
    first_name,
):

    conn = db_connection()

    conn.execute("""
        INSERT INTO users (
            user_id,
            username,
            first_name,
            created_at
        )
        VALUES (?, ?, ?, ?)

        ON CONFLICT(user_id)
        DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
    """, (
        str(user_id),
        username or "",
        first_name or "",
        datetime.now(timezone.utc).isoformat(),
    ))

    conn.commit()
    conn.close()


# =========================================================
# API KEY
# =========================================================

def hash_key(raw_key):

    return hashlib.sha256(
        raw_key.encode("utf-8")
    ).hexdigest()


def create_api_key(
    user_id,
    plan,
):

    plans = {
        "basic": {
            "daily_limit": 1000,
        },
        "pro": {
            "daily_limit": 10000,
        },
        "custom": {
            "daily_limit": 50000,
        },
    }

    if plan not in plans:
        plan = "basic"

    daily_limit = plans[plan]["daily_limit"]

    raw_key = (
        "KCE_"
        + secrets.token_urlsafe(32)
    )

    key_hash = hash_key(raw_key)

    now = datetime.now(timezone.utc)

    expires_at = (
        now + timedelta(days=30)
    ).isoformat()

    conn = db_connection()

    # Revoke previous active keys
    conn.execute("""
        UPDATE api_keys
        SET status = 'revoked'
        WHERE user_id = ?
        AND status = 'active'
    """, (
        str(user_id),
    ))

    conn.execute("""
        INSERT INTO api_keys (
            user_id,
            key_hash,
            plan,
            daily_limit,
            today_requests,
            total_requests,
            usage_date,
            status,
            expires_at,
            created_at
        )
        VALUES (?, ?, ?, ?, 0, 0, ?, 'active', ?, ?)
    """, (
        str(user_id),
        key_hash,
        plan,
        daily_limit,
        now.date().isoformat(),
        expires_at,
        now.isoformat(),
    ))

    conn.commit()
    conn.close()

    return raw_key


def get_api_key(raw_key):

    key_hash = hash_key(raw_key)

    conn = db_connection()

    row = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE key_hash = ?
        LIMIT 1
    """, (
        key_hash,
    )).fetchone()

    conn.close()

    if not row:
        return None

    return dict(row)


def consume_api_request(raw_key):

    key_hash = hash_key(raw_key)

    conn = db_connection()

    row = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE key_hash = ?
        LIMIT 1
    """, (
        key_hash,
    )).fetchone()

    if not row:
        conn.close()
        return False, "invalid_api_key", None

    key = dict(row)

    if key["status"] != "active":
        conn.close()
        return False, "invalid_api_key", None

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
            """, (
                key["id"],
            ))

            conn.commit()
            conn.close()

            return False, "expired", None

    except Exception:
        pass

    today = now.date().isoformat()

    today_requests = key["today_requests"]

    if key["usage_date"] != today:
        today_requests = 0

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
            usage_date = ?
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
    """, (
        key["id"],
    )).fetchone()

    conn.close()

    return True, "ok", dict(updated)


def log_request(
    api_key_id,
    query,
    success,
    status_code,
):

    conn = db_connection()

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
        datetime.now(timezone.utc).isoformat(),
    ))

    conn.commit()
    conn.close()


def create_access_request(
    user_id,
    username,
    plan,
):

    conn = db_connection()

    cur = conn.cursor()

    cur.execute("""
        SELECT id
        FROM access_requests
        WHERE user_id = ?
        AND status = 'pending'
        LIMIT 1
    """, (
        str(user_id),
    ))

    existing = cur.fetchone()

    if existing:
        conn.close()
        return existing["id"]

    cur.execute("""
        INSERT INTO access_requests (
            user_id,
            username,
            plan,
            status,
            created_at
        )
        VALUES (?, ?, ?, 'pending', ?)
    """, (
        str(user_id),
        username or "",
        plan,
        datetime.now(timezone.utc).isoformat(),
    ))

    request_id = cur.lastrowid

    conn.commit()
    conn.close()

    return request_id


def get_access_request(request_id):

    conn = db_connection()

    row = conn.execute("""
        SELECT *
        FROM access_requests
        WHERE id = ?
    """, (
        request_id,
    )).fetchone()

    conn.close()

    if not row:
        return None

    return dict(row)


def update_access_request(
    request_id,
    status,
):

    conn = db_connection()

    conn.execute("""
        UPDATE access_requests
        SET
            status = ?,
            processed_at = ?
        WHERE id = ?
    """, (
        status,
        datetime.now(timezone.utc).isoformat(),
        request_id,
    ))

    conn.commit()
    conn.close()


def get_pending_requests():

    conn = db_connection()

    rows = conn.execute("""
        SELECT *
        FROM access_requests
        WHERE status = 'pending'
        ORDER BY id ASC
    """).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def get_user_keys(user_id):

    conn = db_connection()

    rows = conn.execute("""
        SELECT *
        FROM api_keys
        WHERE user_id = ?
        ORDER BY id DESC
    """, (
        str(user_id),
    )).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def get_stats():

    conn = db_connection()

    users = conn.execute(
        "SELECT COUNT(*) AS c FROM users"
    ).fetchone()["c"]

    keys = conn.execute(
        "SELECT COUNT(*) AS c FROM api_keys"
    ).fetchone()["c"]

    active_keys = conn.execute("""
        SELECT COUNT(*)
        FROM api_keys
        WHERE status = 'active'
    """).fetchone()[0]

    requests = conn.execute("""
        SELECT COUNT(*)
        FROM request_logs
    """).fetchone()[0]

    conn.close()

    return {
        "users": users,
        "keys": keys,
        "active_keys": active_keys,
        "api_requests": requests,
    }


# =========================================================
# DATA LOADER
# =========================================================

def load_records():

    records = []

    if not DATA_DIR.exists():
        return records

    for file_path in sorted(
        DATA_DIR.glob("*.json")
    ):

        try:

            with open(
                file_path,
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(file)

            if isinstance(data, list):

                for item in data:

                    if isinstance(item, dict):
                        records.append(item)

            elif isinstance(data, dict):

                data_list = data.get("data")

                if isinstance(data_list, list):

                    for item in data_list:

                        if isinstance(item, dict):
                            records.append(item)

        except Exception as exc:

            print(
                f"JSON LOAD ERROR: "
                f"{file_path}: {exc}"
            )

    return records


def search_records(
    search_value,
    limit,
):

    search_value = (
        search_value
        .strip()
        .lower()
    )

    if not search_value:
        return []

    records = load_records()

    results = []

    fields = [
        "id",
        "mobile",
        "name",
        "pincode",
        "city",
        "address",
    ]

    for record in records:

        for field in fields:

            value = record.get(field)

            if value is None:
                continue

            if search_value in str(
                value
            ).lower():

                results.append(record)
                break

        if len(results) >= limit:
            break

    return results


# =========================================================
# FASTAPI ROUTES
# =========================================================

@app.get("/")
async def root():

    return {
        "service": APP_NAME,
        "status": "online",
        "version": "1.0.0",
        "docs": "/docs",
        "search_endpoint": "/api/search",
        "status_endpoint": "/api/status",
    }


@app.get("/health")
async def health():

    return {
        "status": "ok",
        "service": APP_NAME,
        "database": "sqlite",
        "data_directory": str(DATA_DIR),
        "time": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@app.get("/api/search")
async def api_search(
    api_key: str = Query(...),
    query: str = Query(
        ...,
        min_length=1,
        max_length=100,
    ),
    limit: int = Query(
        20,
        ge=1,
        le=50,
    ),
):

    key = get_api_key(api_key)

    if not key:

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "invalid_api_key",
            },
        )

    allowed, reason, updated_key = (
        consume_api_request(api_key)
    )

    if not allowed:

        if reason == "daily_limit":

            log_request(
                key["id"],
                query,
                False,
                429,
            )

            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": "daily_limit_reached",
                    "daily_limit": key[
                        "daily_limit"
                    ],
                },
            )

        if reason == "expired":

            log_request(
                key["id"],
                query,
                False,
                403,
            )

            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "api_key_expired",
                },
            )

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "invalid_api_key",
            },
        )

    results = search_records(
        query,
        limit,
    )

    log_request(
        updated_key["id"],
        query,
        True,
        200,
    )

    return {
        "success": True,
        "query": query,
        "count": len(results),
        "usage": {
            "today": updated_key[
                "today_requests"
            ],
            "daily_limit": updated_key[
                "daily_limit"
            ],
            "total": updated_key[
                "total_requests"
            ],
        },
        "results": results,
    }


@app.get("/api/status")
async def api_status(
    api_key: str = Query(...),
):

    key = get_api_key(api_key)

    if not key:

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "invalid_api_key",
            },
        )

    return {
        "success": True,
        "plan": key["plan"],
        "status": key["status"],
        "today_requests": key[
            "today_requests"
        ],
        "daily_limit": key[
            "daily_limit"
        ],
        "total_requests": key[
            "total_requests"
        ],
        "expires_at": key[
            "expires_at"
        ],
    }


@app.get("/api/stats")
async def api_stats():

    return {
        "service": APP_NAME,
        "status": "online",
    }


# =========================================================
# TELEGRAM BOT
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    save_user(
        user.id,
        user.username,
        user.first_name,
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔑 API Plans",
                callback_data="plans",
            )
        ],
        [
            InlineKeyboardButton(
                "🚀 Request API Access",
                callback_data="request",
            )
        ],
        [
            InlineKeyboardButton(
                "🔐 My API Keys",
                callback_data="keys",
            )
        ],
        [
            InlineKeyboardButton(
                "📊 My Usage",
                callback_data="usage",
            )
        ],
        [
            InlineKeyboardButton(
                "📖 API Docs",
                callback_data="docs",
            )
        ],
    ]

    await update.message.reply_text(
        "🔥 KRUTIK CYBER EXPERT\n\n"
        "Welcome to the API service.\n\n"
        "Choose an option below:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def plans_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(
        "🔑 API PLANS\n\n"
        "🟢 Basic\n"
        "• 1,000 requests/day\n"
        "• 30 days\n\n"
        "🔵 Pro\n"
        "• 10,000 requests/day\n"
        "• 30 days\n\n"
        "🟣 Custom\n"
        "• 50,000 requests/day\n"
        "• 30 days\n\n"
        "Access is manually approved by the owner."
    )


async def request_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🟢 Basic",
                callback_data="request_basic",
            )
        ],
        [
            InlineKeyboardButton(
                "🔵 Pro",
                callback_data="request_pro",
            )
        ],
        [
            InlineKeyboardButton(
                "🟣 Custom",
                callback_data="request_custom",
            )
        ],
    ]

    await query.edit_message_text(
        "Select your API plan:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def submit_request_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    user = query.from_user

    plan = query.data.replace(
        "request_",
        "",
    )

    request_id = create_access_request(
        user.id,
        user.username,
        plan,
    )

    if OWNER_CHAT_ID:

        try:

            owner_keyboard = [
                [
                    InlineKeyboardButton(
                        "✅ Approve",
                        callback_data=(
                            f"approve_{request_id}"
                        ),
                    ),
                    InlineKeyboardButton(
                        "❌ Reject",
                        callback_data=(
                            f"reject_{request_id}"
                        ),
                    ),
                ]
            ]

            await context.bot.send_message(
                chat_id=int(OWNER_CHAT_ID),
                text=(
                    "🔔 NEW API ACCESS REQUEST\n\n"
                    f"Request ID: {request_id}\n"
                    f"User ID: {user.id}\n"
                    f"Username: @{user.username or 'none'}\n"
                    f"Plan: {plan.upper()}"
                ),
                reply_markup=InlineKeyboardMarkup(
                    owner_keyboard
                ),
            )

        except Exception as exc:

            print(
                "OWNER NOTIFICATION ERROR:",
                exc,
            )

    await query.edit_message_text(
        "✅ Request submitted.\n\n"
        f"Plan: {plan.upper()}\n"
        f"Request ID: {request_id}\n\n"
        "Please wait for owner approval."
    )


async def keys_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    user = query.from_user

    keys = get_user_keys(user.id)

    if not keys:

        await query.edit_message_text(
            "🔐 You don't have any API keys yet."
        )

        return

    lines = [
        "🔐 YOUR API KEYS\n"
    ]

    for key in keys:

        lines.append(
            f"Plan: {key['plan'].upper()}\n"
            f"Status: {key['status']}\n"
            f"Expires: {key['expires_at']}\n"
            f"Requests: {key['total_requests']}\n"
        )

    await query.edit_message_text(
        "\n".join(lines)
    )


async def usage_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    user = query.from_user

    keys = get_user_keys(user.id)

    if not keys:

        await query.edit_message_text(
            "📊 No API usage found."
        )

        return

    key = keys[0]

    await query.edit_message_text(
        "📊 API USAGE\n\n"
        f"Plan: {key['plan'].upper()}\n"
        f"Today: {key['today_requests']}\n"
        f"Daily Limit: {key['daily_limit']}\n"
        f"Total: {key['total_requests']}\n"
        f"Status: {key['status']}\n"
        f"Expires: {key['expires_at']}"
    )


async def docs_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    docs_url = (
        f"https://krutik-cyber-expert-api.onrender.com/docs"
    )

    await query.edit_message_text(
        "📖 API DOCUMENTATION\n\n"
        f"{docs_url}\n\n"
        "Search endpoint:\n"
        "GET /api/search\n\n"
        "Parameters:\n"
        "api_key\n"
        "query\n"
        "limit"
    )


async def owner_decision_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    user = query.from_user

    if not OWNER_CHAT_ID:
        return

    if str(user.id) != str(OWNER_CHAT_ID):

        await query.answer(
            "Owner only.",
            show_alert=True,
        )

        return

    data = query.data

    if data.startswith("approve_"):

        request_id = int(
            data.replace(
                "approve_",
                "",
            )
        )

        request = get_access_request(
            request_id
        )

        if not request:

            await query.edit_message_text(
                "❌ Request not found."
            )

            return

        if request["status"] != "pending":

            await query.edit_message_text(
                "⚠️ Request already processed."
            )

            return

        update_access_request(
            request_id,
            "approved",
        )

        raw_key = create_api_key(
            request["user_id"],
            request["plan"],
        )

        try:

            await context.bot.send_message(
                chat_id=int(
                    request["user_id"]
                ),
                text=(
                    "🎉 API ACCESS APPROVED\n\n"
                    f"Plan: {request['plan'].upper()}\n\n"
                    "🔑 Your API key:\n\n"
                    f"{raw_key}\n\n"
                    "⚠️ Keep this key private.\n\n"
                    "API Docs:\n"
                    "https://krutik-cyber-expert-api.onrender.com/docs"
                ),
            )

        except Exception as exc:

            print(
                "USER KEY SEND ERROR:",
                exc,
            )

        await query.edit_message_text(
            "✅ REQUEST APPROVED\n\n"
            f"Request ID: {request_id}\n"
            f"Plan: {request['plan'].upper()}"
        )

    elif data.startswith("reject_"):

        request_id = int(
            data.replace(
                "reject_",
                "",
            )
        )

        request = get_access_request(
            request_id
        )

        if not request:

            await query.edit_message_text(
                "❌ Request not found."
            )

            return

        update_access_request(
            request_id,
            "rejected",
        )

        try:

            await context.bot.send_message(
                chat_id=int(
                    request["user_id"]
                ),
                text=(
                    "❌ API ACCESS REQUEST REJECTED\n\n"
                    "You can submit a new request later."
                ),
            )

        except Exception as exc:

            print(
                "REJECT MESSAGE ERROR:",
                exc,
            )

        await query.edit_message_text(
            "❌ REQUEST REJECTED\n\n"
            f"Request ID: {request_id}"
        )


async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    if not OWNER_CHAT_ID:
        return

    if str(user.id) != str(OWNER_CHAT_ID):

        await update.message.reply_text(
            "❌ Owner only."
        )

        return

    stats = get_stats()

    await update.message.reply_text(
        "📊 KRUTIK CYBER EXPERT STATS\n\n"
        f"Users: {stats['users']}\n"
        f"API Keys: {stats['keys']}\n"
        f"Active Keys: {stats['active_keys']}\n"
        f"API Requests: {stats['api_requests']}"
    )


async def pending_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    if not OWNER_CHAT_ID:
        return

    if str(user.id) != str(OWNER_CHAT_ID):

        await update.message.reply_text(
            "❌ Owner only."
        )

        return

    requests = get_pending_requests()

    if not requests:

        await update.message.reply_text(
            "✅ No pending requests."
        )

        return

    lines = [
        "🔔 PENDING REQUESTS\n"
    ]

    for request in requests:

        lines.append(
            f"ID: {request['id']}\n"
            f"User: {request['user_id']}\n"
            f"Plan: {request['plan']}\n"
            f"Status: {request['status']}\n"
        )

    await update.message.reply_text(
        "\n".join(lines)
    )


# =========================================================
# FASTAPI SERVER THREAD
# =========================================================

def run_api():

    print(
        f"Starting FastAPI on port {PORT}"
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 50)
    print(APP_NAME)
    print("=" * 50)

    init_db()

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    if not OWNER_CHAT_ID:

        print(
            "WARNING: OWNER_CHAT_ID is not configured."
        )

    api_thread = threading.Thread(
        target=run_api,
        daemon=True,
    )

    api_thread.start()

    telegram_app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    telegram_app.add_handler(
        CommandHandler(
            "start",
            start_command,
        )
    )

    telegram_app.add_handler(
        CommandHandler(
            "stats",
            stats_command,
        )
    )

    telegram_app.add_handler(
        CommandHandler(
            "pending",
            pending_command,
        )
    )

    telegram_app.add_handler(
        CallbackQueryHandler(
            plans_callback,
            pattern="^plans$",
        )
    )

    telegram_app.add_handler(
        CallbackQueryHandler(
            request_callback,
            pattern="^request$",
        )
    )

    telegram_app.add_handler(
        CallbackQueryHandler(
            submit_request_callback,
            pattern="^request_(basic|pro|custom)$",
        )
    )

    telegram_app.add_handler(
        CallbackQueryHandler(
            keys_callback,
            pattern="^keys$",
        )
    )

    telegram_app.add_handler(
        CallbackQueryHandler(
            usage_callback,
            pattern="^usage$",
        )
    )

    telegram_app.add_handler(
        CallbackQueryHandler(
            docs_callback,
            pattern="^docs$",
        )
    )

    telegram_app.add_handler(
        CallbackQueryHandler(
            owner_decision_callback,
            pattern="^(approve|reject)_\d+$",
        )
    )

    print(
        "Telegram bot starting..."
    )

    telegram_app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
