import os
import threading
from datetime import datetime, timezone, timedelta

import uvicorn

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

import database
from api import app as fastapi_app


APP_NAME = "KRUTIK CYBER EXPERT API"

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "",
).strip()

OWNER_CHAT_ID = os.getenv(
    "OWNER_CHAT_ID",
    "",
).strip()

PORT = int(
    os.getenv(
        "PORT",
        "10000",
    )
)

API_URL = (
    "https://krutik-cyber-expert-api.onrender.com"
)


# =========================================================
# HELPERS
# =========================================================

def is_owner(user_id):
    return (
        OWNER_CHAT_ID
        and str(user_id)
        == str(OWNER_CHAT_ID)
    )


async def owner_only(update):
    user = update.effective_user

    if not is_owner(user.id):
        if update.message:
            await update.message.reply_text(
                "❌ Owner only."
            )
        return False

    return True


def back_button():
    return [
        InlineKeyboardButton(
            "🔙 Back",
            callback_data="home",
        )
    ]


# =========================================================
# USER MENU
# =========================================================

def user_menu():
    return InlineKeyboardMarkup([
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
                "📖 How to Use API",
                callback_data="howto",
            )
        ],
        [
            InlineKeyboardButton(
                "📚 API Docs",
                callback_data="docs",
            )
        ],
    ])


# =========================================================
# ADMIN MENU
# =========================================================

def admin_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📊 Dashboard",
                callback_data="admin_dashboard",
            )
        ],
        [
            InlineKeyboardButton(
                "📨 Pending Requests",
                callback_data="admin_pending",
            )
        ],
        [
            InlineKeyboardButton(
                "👥 Users",
                callback_data="admin_users",
            )
        ],
        [
            InlineKeyboardButton(
                "🔑 API Keys",
                callback_data="admin_keys",
            )
        ],
        [
            InlineKeyboardButton(
                "📈 API Usage",
                callback_data="admin_usage",
            )
        ],
        [
            InlineKeyboardButton(
                "🚫 Block User",
                callback_data="admin_block",
            ),
            InlineKeyboardButton(
                "✅ Unblock User",
                callback_data="admin_unblock",
            ),
        ],
        [
            InlineKeyboardButton(
                "🟢 API ON",
                callback_data="admin_apion",
            ),
            InlineKeyboardButton(
                "🔴 API OFF",
                callback_data="admin_apioff",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔒 Revoke API",
                callback_data="admin_revoke",
            ),
        ],
        [
            InlineKeyboardButton(
                "🗑️ Delete API",
                callback_data="admin_delete",
            ),
        ],
        [
            InlineKeyboardButton(
                "➕ Create API Key",
                callback_data="admin_create",
            ),
        ],
        [
            InlineKeyboardButton(
                "📖 API Docs",
                callback_data="admin_docs",
            )
        ],
    ])


# =========================================================
# /START
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    database.save_user(
        user.id,
        user.username,
        user.first_name,
    )

    if database.is_user_blocked(
        user.id
    ):
        await update.message.reply_text(
            f"🚫 {APP_NAME}\n\n"
            "Your access has been blocked."
        )
        return

    text = (
        f"🔥 {APP_NAME}\n\n"
        "Welcome!\n\n"
        "Choose an option below:"
    )

    await update.message.reply_text(
        text,
        reply_markup=user_menu(),
    )


# =========================================================
# /ADMIN
# =========================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update):
        return

    await update.message.reply_text(
        f"👑 {APP_NAME}\n"
        "ADMIN PANEL\n\n"
        "Choose an option:",
        reply_markup=admin_menu(),
    )


# =========================================================
# USER CALLBACKS
# =========================================================

async def plans_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        f"🔑 {APP_NAME}\n"
        "API PLANS\n\n"
        "🟢 BASIC\n"
        "• 1,000 requests/day\n"
        "• 30 days\n\n"
        "🔵 PRO\n"
        "• 10,000 requests/day\n"
        "• 30 days\n\n"
        "🟣 CUSTOM\n"
        "• Custom limits\n"
        "• Custom expiry\n"
        "• Custom rate limit\n\n"
        "Access requires owner approval.",
        reply_markup=InlineKeyboardMarkup([
            back_button()
        ]),
    )


async def request_callback(
    update,
    context,
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
        back_button(),
    ]

    await query.edit_message_text(
        f"🚀 {APP_NAME}\n\n"
        "Select API plan:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def submit_request_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    plan = query.data.replace(
        "request_",
        "",
    )

    request_id = (
        database.create_access_request(
            user.id,
            user.username,
            plan,
        )
    )

    if OWNER_CHAT_ID:
        try:
            keyboard = [[
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
            ]]

            await context.bot.send_message(
                chat_id=int(OWNER_CHAT_ID),
                text=(
                    f"🔔 {APP_NAME}\n"
                    "NEW ACCESS REQUEST\n\n"
                    f"Request ID: {request_id}\n"
                    f"User ID: {user.id}\n"
                    f"Username: "
                    f"@{user.username or 'none'}\n"
                    f"Plan: {plan.upper()}"
                ),
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                ),
            )

        except Exception as exc:
            print(
                "OWNER NOTIFICATION ERROR:",
                exc,
            )

    await query.edit_message_text(
        f"✅ {APP_NAME}\n\n"
        "Request submitted.\n\n"
        f"Request ID: {request_id}\n"
        f"Plan: {plan.upper()}\n\n"
        "Please wait for owner approval.",
        reply_markup=InlineKeyboardMarkup([
            back_button()
        ]),
    )


async def keys_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    keys = database.get_user_keys(
        user.id
    )

    if not keys:
        await query.edit_message_text(
            f"🔐 {APP_NAME}\n\n"
            "You don't have any API keys.",
            reply_markup=InlineKeyboardMarkup([
                back_button()
            ]),
        )
        return

    lines = [
        f"🔐 {APP_NAME}",
        "YOUR API KEYS",
        "",
    ]

    for key in keys:
        lines.extend([
            f"🆔 ID: {key['id']}",
            f"📛 Name: {key['key_name']}",
            f"📦 Plan: {key['plan'].upper()}",
            f"📌 Status: {key['status']}",
            "",
            f"Daily: "
            f"{key['today_requests']}/"
            f"{key['daily_limit']}",
            f"Total: "
            f"{key['total_requests']}/"
            f"{key['total_limit'] or '∞'}",
            f"Rate/min: "
            f"{key['rate_limit'] or '∞'}",
            f"Start: "
            f"{key['start_at'] or 'Now'}",
            f"Expiry: "
            f"{key['expires_at'] or 'Never'}",
            f"Last used: "
            f"{key['last_used_at'] or 'Never'}",
            "",
        ])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            back_button()
        ]),
    )


async def usage_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    keys = database.get_user_keys(
        user.id
    )

    if not keys:
        await query.edit_message_text(
            f"📊 {APP_NAME}\n\n"
            "No API usage found.",
            reply_markup=InlineKeyboardMarkup([
                back_button()
            ]),
        )
        return

    lines = [
        f"📊 {APP_NAME}",
        "MY USAGE",
        "",
    ]

    for key in keys:
        daily_remaining = max(
            0,
            key["daily_limit"]
            - key["today_requests"],
        )

        if key["total_limit"] is None:
            total_remaining = "∞"
        else:
            total_remaining = max(
                0,
                key["total_limit"]
                - key["total_requests"],
            )

        lines.extend([
            f"🔑 {key['key_name']}",
            f"Today: "
            f"{key['today_requests']}/"
            f"{key['daily_limit']}",
            f"Daily Remaining: "
            f"{daily_remaining}",
            f"Total: "
            f"{key['total_requests']}/"
            f"{key['total_limit'] or '∞'}",
            f"Total Remaining: "
            f"{total_remaining}",
            f"Last Used: "
            f"{key['last_used_at'] or 'Never'}",
            "",
        ])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            back_button()
        ]),
    )


async def howto_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        f"📖 {APP_NAME}\n"
        "HOW TO USE API\n\n"

        "1️⃣ Copy your API key.\n\n"

        "2️⃣ Search endpoint:\n"
        f"GET {API_URL}/api/search\n\n"

        "3️⃣ Parameters:\n"
        "api_key = YOUR_API_KEY\n"
        "query = YOUR_SEARCH_VALUE\n"
        "limit = 20\n\n"

        "Example:\n"
        f"{API_URL}/api/search?"
        "api_key=YOUR_KEY&"
        "query=TEST&limit=20\n\n"

        "4️⃣ Response is JSON.\n\n"

        "🔐 Keep your API key private.\n\n"

        f"📚 Docs:\n"
        f"{API_URL}/docs",
        reply_markup=InlineKeyboardMarkup([
            back_button()
        ]),
    )


async def docs_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        f"📚 {APP_NAME}\n\n"
        f"{API_URL}/docs\n\n"
        "Endpoints:\n"
        "GET /\n"
        "GET /health\n"
        "GET /api/search\n"
        "GET /api/status\n"
        "GET /api/stats",
        reply_markup=InlineKeyboardMarkup([
            back_button()
        ]),
    )


# =========================================================
# ADMIN CALLBACK
# =========================================================

async def admin_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    if not is_owner(query.from_user.id):
        await query.answer(
            "Owner only.",
            show_alert=True,
        )
        return

    data = query.data

    # -----------------------------------------------------
    # DASHBOARD
    # -----------------------------------------------------

    if data == "admin_dashboard":
        stats = database.get_usage_stats()

        status = (
            "🟢 ONLINE"
            if stats["global_api_enabled"]
            else "🔴 OFF"
        )

        text = (
            f"📊 {APP_NAME}\n"
            "DASHBOARD\n\n"
            f"API: {status}\n\n"
            f"👥 Users: {stats['users']}\n"
            f"🚫 Blocked: {stats['blocked']}\n"
            f"🟢 API Enabled: "
            f"{stats['api_enabled']}\n\n"
            f"🔑 Keys: {stats['keys']}\n"
            f"🟢 Active: "
            f"{stats['active_keys']}\n"
            f"🔒 Revoked: "
            f"{stats['revoked_keys']}\n"
            f"⌛ Expired: "
            f"{stats['expired_keys']}\n\n"
            f"📈 Requests: "
            f"{stats['requests']}\n"
            f"✅ Success: "
            f"{stats['successful']}\n"
            f"❌ Failed: "
            f"{stats['failed']}\n"
            f"📨 Pending: "
            f"{stats['pending']}\n"
            f"📊 Total Usage: "
            f"{stats['total_usage']}"
        )

        await query.edit_message_text(
            text,
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # PENDING
    # -----------------------------------------------------

    if data == "admin_pending":
        requests = (
            database.get_pending_requests()
        )

        if not requests:
            text = (
                f"📨 {APP_NAME}\n\n"
                "No pending requests."
            )

        else:
            lines = [
                f"📨 {APP_NAME}",
                "PENDING REQUESTS",
                "",
            ]

            for req in requests:
                lines.extend([
                    f"ID: {req['id']}",
                    f"User: {req['chat_id']}",
                    f"Username: "
                    f"@{req.get('username') or 'none'}",
                    f"Plan: "
                    f"{req['plan'].upper()}",
                    f"Status: {req['status']}",
                    "",
                ])

            text = "\n".join(lines)

        await query.edit_message_text(
            text,
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # USERS
    # -----------------------------------------------------

    if data == "admin_users":
        users = database.get_users(
            50
        )

        lines = [
            f"👥 {APP_NAME}",
            "USERS",
            "",
        ]

        if not users:
            lines.append(
                "No users."
            )

        for user in users:
            blocked = (
                "🚫"
                if user["blocked"]
                else "🟢"
            )

            api = (
                "🟢"
                if user.get("api_enabled", 1)
                else "🔴"
            )

            lines.append(
                f"{blocked} {api} "
                f"{user['chat_id']} "
                f"@{user['username'] or 'none'}"
            )

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # KEYS
    # -----------------------------------------------------

    if data == "admin_keys":
        keys = database.get_all_keys(
            50
        )

        lines = [
            f"🔑 {APP_NAME}",
            "API KEYS",
            "",
        ]

        if not keys:
            lines.append(
                "No API keys."
            )

        for key in keys:
            lines.extend([
                f"ID: {key['id']}",
                f"User: {key['chat_id']}",
                f"Name: {key['key_name']}",
                f"Plan: {key['plan'].upper()}",
                f"Status: {key['status']}",
                f"Daily: "
                f"{key['today_requests']}/"
                f"{key['daily_limit']}",
                f"Total: "
                f"{key['total_requests']}/"
                f"{key['total_limit'] or '∞'}",
                f"Last: "
                f"{key['last_used_at'] or 'Never'}",
                "",
            ])

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # USAGE
    # -----------------------------------------------------

    if data == "admin_usage":
        logs = database.get_recent_logs(
            30
        )

        lines = [
            f"📈 {APP_NAME}",
            "RECENT API USAGE",
            "",
        ]

        if not logs:
            lines.append(
                "No requests."
            )

        for log in logs:
            icon = (
                "✅"
                if log["success"]
                else "❌"
            )

            lines.append(
                f"{icon} "
                f"Key:{log['api_key_id']} "
                f"User:{log['chat_id']} "
                f"HTTP:{log['status_code']}"
            )

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # BLOCK
    # -----------------------------------------------------

    if data == "admin_block":
        await query.edit_message_text(
            f"🚫 {APP_NAME}\n\n"
            "Use command:\n\n"
            "/block USER_ID",
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # UNBLOCK
    # -----------------------------------------------------

    if data == "admin_unblock":
        await query.edit_message_text(
            f"✅ {APP_NAME}\n\n"
            "Use command:\n\n"
            "/unblock USER_ID",
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # API ON
    # -----------------------------------------------------

    if data == "admin_apion":
        await query.edit_message_text(
            f"🟢 {APP_NAME}\n\n"
            "Use:\n"
            "/apion USER_ID\n\n"
            "Global ON:\n"
            "/globalon",
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # API OFF
    # -----------------------------------------------------

    if data == "admin_apioff":
        await query.edit_message_text(
            f"🔴 {APP_NAME}\n\n"
            "Use:\n"
            "/apioff USER_ID\n\n"
            "Global OFF:\n"
            "/globaloff",
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # REVOKE
    # -----------------------------------------------------

    if data == "admin_revoke":
        await query.edit_message_text(
            f"🔒 {APP_NAME}\n\n"
            "Use:\n"
            "/revoke KEY_ID\n\n"
            "A confirmation will be shown.",
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # DELETE
    # -----------------------------------------------------

    if data == "admin_delete":
        await query.edit_message_text(
            f"🗑️ {APP_NAME}\n\n"
            "Use:\n"
            "/deleteapi KEY_ID\n\n"
            "A confirmation will be shown.",
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # CREATE
    # -----------------------------------------------------

    if data == "admin_create":
        await query.edit_message_text(
            f"➕ {APP_NAME}\n\n"
            "Create API key:\n\n"
            "/createapi USER_ID PLAN\n\n"
            "Example:\n"
            "/createapi 123456789 custom\n\n"
            "Advanced custom:\n"
            "/createapi2 USER_ID "
            "NAME DAILY TOTAL DAYS RATE",
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # DOCS
    # -----------------------------------------------------

    if data == "admin_docs":
        await query.edit_message_text(
            f"📖 {APP_NAME}\n\n"
            f"{API_URL}/docs\n\n"
            f"{API_URL}/health\n\n"
            f"{API_URL}/api/stats",
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # HOME
    # -----------------------------------------------------

    if data == "home":
        await query.edit_message_text(
            f"🔥 {APP_NAME}\n\n"
            "Choose an option:",
            reply_markup=user_menu(),
        )
        return


# =========================================================
# APPROVE / REJECT
# =========================================================

async def owner_decision(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    if not is_owner(
        query.from_user.id
    ):
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

        request = (
            database.get_access_request(
                request_id
            )
        )

        if not request:
            await query.edit_message_text(
                "❌ Request not found."
            )
            return

        if request["status"] != "pending":
            await query.edit_message_text(
                "⚠️ Already processed."
            )
            return

        database.update_access_request(
            request_id,
            "approved",
        )

        plan = request["plan"]

        limits = {
            "basic": 1000,
            "pro": 10000,
            "custom": 50000,
        }

        daily = limits.get(
            plan,
            50000,
        )

        raw_key, key_id = (
            database.create_api_key(
                request["chat_id"],
                plan=plan,
                key_name=(
                    f"{plan.upper()} API"
                ),
                daily_limit=daily,
                total_limit=None,
                start_at=None,
                expires_at=(
                    (
                        datetime.now(
                            timezone.utc
                        )
                        + timedelta(days=30)
                    ).isoformat()
                ),
                rate_limit=None,
            )
        )

        try:
            await context.bot.send_message(
                chat_id=int(
                    request["chat_id"]
                ),
                text=(
                    f"🎉 {APP_NAME}\n\n"
                    "API ACCESS APPROVED\n\n"
                    f"Plan: {plan.upper()}\n"
                    f"Key ID: {key_id}\n\n"
                    "🔑 Your API Key:\n\n"
                    f"{raw_key}\n\n"
                    "⚠️ This key is shown only now.\n"
                    "Keep it private.\n\n"
                    f"📚 Docs:\n"
                    f"{API_URL}/docs"
                ),
            )
        except Exception as exc:
            print(
                "KEY SEND ERROR:",
                exc,
            )

        await query.edit_message_text(
            f"✅ {APP_NAME}\n\n"
            "Request approved.\n\n"
            f"Request ID: {request_id}\n"
            f"Key ID: {key_id}"
        )

    elif data.startswith("reject_"):
        request_id = int(
            data.replace(
                "reject_",
                "",
            )
        )

        request = (
            database.get_access_request(
                request_id
            )
        )

        if not request:
            await query.edit_message_text(
                "❌ Request not found."
            )
            return

        database.update_access_request(
            request_id,
            "rejected",
        )

        try:
            await context.bot.send_message(
                chat_id=int(
                    request["chat_id"]
                ),
                text=(
                    f"❌ {APP_NAME}\n\n"
                    "Your API access request "
                    "was rejected."
                ),
            )
        except Exception as exc:
            print(
                "REJECT SEND ERROR:",
                exc,
            )

        await query.edit_message_text(
            f"❌ {APP_NAME}\n\n"
            "Request rejected.\n\n"
            f"Request ID: {request_id}"
        )


# =========================================================
# BLOCK / UNBLOCK
# =========================================================

async def block_command(
    update,
    context,
):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/block USER_ID"
        )
        return

    user_id = int(
        context.args[0]
    )

    database.block_user(
        user_id
    )

    await update.message.reply_text(
        f"🚫 {APP_NAME}\n\n"
        f"User {user_id} blocked."
    )


async def unblock_command(
    update,
    context,
):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/unblock USER_ID"
        )
        return

    user_id = int(
        context.args[0]
    )

    database.unblock_user(
        user_id
    )

    await update.message.reply_text(
        f"✅ {APP_NAME}\n\n"
        f"User {user_id} unblocked."
    )


# =========================================================
# USER API ON/OFF
# =========================================================

async def apion_command(
    update,
    context,
):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/apion USER_ID"
        )
        return

    user_id = int(
        context.args[0]
    )

    database.api_on(
        user_id
    )

    await update.message.reply_text(
        f"🟢 {APP_NAME}\n\n"
        f"API enabled for {user_id}."
    )


async def apioff_command(
    update,
    context,
):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/apioff USER_ID"
        )
        return

    user_id = int(
        context.args[0]
    )

    database.api_off(
        user_id
    )

    await update.message.reply_text(
        f"🔴 {APP_NAME}\n\n"
        f"API disabled for {user_id}."
    )


# =========================================================
# GLOBAL ON/OFF
# =========================================================

async def globalon_command(
    update,
    context,
):
    if not await owner_only(update):
        return

    database.set_global_api_enabled(
        True
    )

    await update.message.reply_text(
        f"🟢 {APP_NAME}\n\n"
        "Global API is ON."
    )


async def globaloff_command(
    update,
    context,
):
    if not await owner_only(update):
        return

    database.set_global_api_enabled(
        False
    )

    await update.message.reply_text(
        f"🔴 {APP_NAME}\n\n"
        "Global API is OFF.\n"
        "Maintenance mode enabled."
    )


# =========================================================
# CREATE SIMPLE KEY
# =========================================================

async def createapi_command(
    update,
    context,
):
    if not await owner_only(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "/createapi USER_ID PLAN\n\n"
            "Plans:\n"
            "basic\n"
            "pro\n"
            "custom"
        )
        return

    user_id = int(
        context.args[0]
    )

    plan = context.args[1].lower()

    limits = {
        "basic": 1000,
        "pro": 10000,
        "custom": 50000,
    }

    daily = limits.get(
        plan,
        50000,
    )

    expires = (
        datetime.now(timezone.utc)
        + timedelta(days=30)
    ).isoformat()

    raw_key, key_id = (
        database.create_api_key(
            user_id,
            plan=plan,
            key_name=(
                f"{plan.upper()} API"
            ),
            daily_limit=daily,
            expires_at=expires,
        )
    )

    await update.message.reply_text(
        f"🔑 {APP_NAME}\n\n"
        "API KEY CREATED\n\n"
        f"User: {user_id}\n"
        f"Key ID: {key_id}\n"
        f"Plan: {plan.upper()}\n"
        f"Daily: {daily}\n"
        "Expiry: 30 days\n\n"
        "🔐 RAW KEY:\n\n"
        f"{raw_key}\n\n"
        "⚠️ Save it now."
    )


# =========================================================
# CREATE CUSTOM KEY
# =========================================================

async def createapi2_command(
    update,
    context,
):
    if not await owner_only(update):
        return

    if len(context.args) < 6:
        await update.message.reply_text(
            "Usage:\n\n"
            "/createapi2 "
            "USER_ID NAME DAILY TOTAL DAYS RATE\n\n"
            "Example:\n"
            "/createapi2 "
            "123456789 TEST 500 10000 30 10\n\n"
            "TOTAL = 0 means unlimited\n"
            "DAYS = 0 means no expiry\n"
            "RATE = 0 means unlimited"
        )
        return

    try:
        user_id = int(
            context.args[0]
        )

        name = context.args[1]

        daily = int(
            context.args[2]
        )

        total = int(
            context.args[3]
        )

        days = int(
            context.args[4]
        )

        rate = int(
            context.args[5]
        )

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid values."
        )
        return

    if total <= 0:
        total = None

    if rate <= 0:
        rate = None

    if days <= 0:
        expires = None
    else:
        expires = (
            datetime.now(timezone.utc)
            + timedelta(days=days)
        ).isoformat()

    raw_key, key_id = (
        database.create_api_key(
            user_id,
            plan="custom",
            key_name=name,
            daily_limit=daily,
            total_limit=total,
            expires_at=expires,
            rate_limit=rate,
        )
    )

    await update.message.reply_text(
        f"🔑 {APP_NAME}\n\n"
        "CUSTOM API KEY CREATED\n\n"
        f"User: {user_id}\n"
        f"Key ID: {key_id}\n"
        f"Name: {name}\n"
        f"Daily: {daily}\n"
        f"Total: {total or '∞'}\n"
        f"Rate/min: {rate or '∞'}\n"
        f"Expiry: "
        f"{expires or 'Never'}\n\n"
        "🔐 RAW KEY:\n\n"
        f"{raw_key}\n\n"
        "⚠️ Save this key now."
    )


# =========================================================
# REVOKE
# =========================================================

async def revoke_command(
    update,
    context,
):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/revoke KEY_ID"
        )
        return

    key_id = int(
        context.args[0]
    )

    key = database.get_key_by_id(
        key_id
    )

    if not key:
        await update.message.reply_text(
            "❌ Key not found."
        )
        return

    keyboard = [[
        InlineKeyboardButton(
            "🔒 YES, REVOKE",
            callback_data=(
                f"confirm_revoke_{key_id}"
            ),
        ),
        InlineKeyboardButton(
            "❌ CANCEL",
            callback_data=(
                "cancel_action"
            ),
        ),
    ]]

    await update.message.reply_text(
        f"⚠️ {APP_NAME}\n\n"
        "REVOKE API KEY\n\n"
        f"Key ID: {key_id}\n"
        f"User: {key['chat_id']}\n"
        f"Name: {key['key_name']}\n"
        f"Plan: {key['plan'].upper()}\n\n"
        "Are you sure?",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================================================
# DELETE
# =========================================================

async def deleteapi_command(
    update,
    context,
):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/deleteapi KEY_ID"
        )
        return

    key_id = int(
        context.args[0]
    )

    key = database.get_key_by_id(
        key_id
    )

    if not key:
        await update.message.reply_text(
            "❌ Key not found."
        )
        return

    keyboard = [[
        InlineKeyboardButton(
            "🗑️ YES, DELETE",
            callback_data=(
                f"confirm_delete_{key_id}"
            ),
        ),
        InlineKeyboardButton(
            "❌ CANCEL",
            callback_data=(
                "cancel_action"
            ),
        ),
    ]]

    await update.message.reply_text(
        f"⚠️ {APP_NAME}\n\n"
        "DELETE API KEY\n\n"
        f"Key ID: {key_id}\n"
        f"User: {key['chat_id']}\n"
        f"Name: {key['key_name']}\n"
        f"Plan: {key['plan'].upper()}\n\n"
        "⚠️ This permanently deletes "
        "the key record and its logs.\n\n"
        "Are you sure?",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================================================
# CONFIRM ACTIONS
# =========================================================

async def action_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    if not is_owner(
        query.from_user.id
    ):
        await query.answer(
            "Owner only.",
            show_alert=True,
        )
        return

    data = query.data

    if data.startswith(
        "confirm_revoke_"
    ):
        key_id = int(
            data.replace(
                "confirm_revoke_",
                "",
            )
        )

        success = database.revoke_key(
            key_id
        )

        await query.edit_message_text(
            (
                f"🔒 {APP_NAME}\n\n"
                "API key revoked."
                if success
                else
                f"❌ {APP_NAME}\n\n"
                "Key not found or already revoked."
            )
        )
        return

    if data.startswith(
        "confirm_delete_"
    ):
        key_id = int(
            data.replace(
                "confirm_delete_",
                "",
            )
        )

        success = database.delete_key(
            key_id
        )

        await query.edit_message_text(
            (
                f"🗑️ {APP_NAME}\n\n"
                "API key permanently deleted."
                if success
                else
                f"❌ {APP_NAME}\n\n"
                "Key not found."
            )
        )
        return

    if data == "cancel_action":
        await query.edit_message_text(
            f"❌ {APP_NAME}\n\n"
            "Action cancelled."
        )


# =========================================================
# /STATS
# =========================================================

async def stats_command(
    update,
    context,
):
    if not await owner_only(update):
        return

    stats = database.get_usage_stats()

    await update.message.reply_text(
        f"📊 {APP_NAME}\n\n"
        f"Users: {stats['users']}\n"
        f"Keys: {stats['keys']}\n"
        f"Active: {stats['active_keys']}\n"
        f"Requests: {stats['requests']}\n"
        f"Success: {stats['successful']}\n"
        f"Failed: {stats['failed']}\n"
        f"Pending: {stats['pending']}\n"
        f"Global API: "
        f"{'ON' if stats['global_api_enabled'] else 'OFF'}"
    )


# =========================================================
# /PENDING
# =========================================================

async def pending_command(
    update,
    context,
):
    if not await owner_only(update):
        return

    requests = (
        database.get_pending_requests()
    )

    if not requests:
        await update.message.reply_text(
            f"📨 {APP_NAME}\n\n"
            "No pending requests."
        )
        return

    lines = [
        f"📨 {APP_NAME}",
        "",
    ]

    for request in requests:
        lines.extend([
            f"ID: {request['id']}",
            f"User: {request['chat_id']}",
            f"Plan: {request['plan'].upper()}",
            f"Status: {request['status']}",
            "",
        ])

    await update.message.reply_text(
        "\n".join(lines)
    )


# =========================================================
# API SERVER
# =========================================================

def run_api():
    print(
        f"{APP_NAME} API starting "
        f"on port {PORT}"
    )

    uvicorn.run(
        fastapi_app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )


# =========================================================
# MAIN
# =========================================================

def main():
    print("=" * 60)
    print(APP_NAME)
    print("=" * 60)

    database.init_db()

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    if not OWNER_CHAT_ID:
        print(
            "WARNING: OWNER_CHAT_ID "
            "is not configured."
        )

    api_thread = threading.Thread(
        target=run_api,
        daemon=True,
    )

    api_thread.start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler(
            "start",
            start_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "stats",
            stats_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "pending",
            pending_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "block",
            block_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "unblock",
            unblock_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "apion",
            apion_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "apioff",
            apioff_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "globalon",
            globalon_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "globaloff",
            globaloff_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "createapi",
            createapi_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "createapi2",
            createapi2_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "revoke",
            revoke_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "deleteapi",
            deleteapi_command,
        )
    )

    # User callbacks
    application.add_handler(
        CallbackQueryHandler(
            plans_callback,
            pattern="^plans$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            request_callback,
            pattern="^request$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            submit_request_callback,
            pattern=(
                "^request_"
                "(basic|pro|custom)$"
            ),
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            keys_callback,
            pattern="^keys$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            usage_callback,
            pattern="^usage$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            howto_callback,
            pattern="^howto$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            docs_callback,
            pattern="^docs$",
        )
    )

    # Admin
    application.add_handler(
        CallbackQueryHandler(
            admin_callback,
            pattern="^admin_",
        )
    )

    # Approve / reject
    application.add_handler(
        CallbackQueryHandler(
            owner_decision,
            pattern=(
                "^(approve|reject)_\\d+$"
            ),
        )
    )

    # Confirm revoke/delete
    application.add_handler(
        CallbackQueryHandler(
            action_callback,
            pattern=(
                "^(confirm_revoke|"
                "confirm_delete)_\\d+$|"
                "^cancel_action$"
            ),
        )
    )

    # Home
    application.add_handler(
        CallbackQueryHandler(
            admin_callback,
            pattern="^home$",
        )
    )

    print(
        "Telegram bot starting..."
    )

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
