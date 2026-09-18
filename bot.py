import os
import threading

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


# =========================================================
# KRUTIK CYBER EXPERT
# TELEGRAM BOT + FASTAPI
# =========================================================

APP_NAME = "KRUTIK CYBER EXPERT"

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    ""
).strip()

OWNER_CHAT_ID = os.getenv(
    "OWNER_CHAT_ID",
    ""
).strip()

PORT = int(
    os.getenv(
        "PORT",
        "10000",
    )
)


# =========================================================
# HELPERS
# =========================================================

def is_owner(user_id):
    if not OWNER_CHAT_ID:
        return False

    return str(user_id) == str(
        OWNER_CHAT_ID
    )


async def owner_only(
    update: Update,
):
    user = update.effective_user

    if not is_owner(user.id):
        if update.message:
            await update.message.reply_text(
                "❌ Owner only."
            )
        return False

    return True


def user_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔑 API Plans",
                callback_data="plans",
            ),
        ],
        [
            InlineKeyboardButton(
                "🚀 Request API Access",
                callback_data="request",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔐 My API Keys",
                callback_data="keys",
            ),
        ],
        [
            InlineKeyboardButton(
                "📊 My Usage",
                callback_data="usage",
            ),
        ],
        [
            InlineKeyboardButton(
                "📖 How to Use API",
                callback_data="howto",
            ),
        ],
        [
            InlineKeyboardButton(
                "📚 API Docs",
                callback_data="docs",
            ),
        ],
    ])


def admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📊 Dashboard",
                callback_data="admin_dashboard",
            ),
            InlineKeyboardButton(
                "📨 Pending Requests",
                callback_data="admin_pending",
            ),
        ],
        [
            InlineKeyboardButton(
                "👥 Users",
                callback_data="admin_users",
            ),
            InlineKeyboardButton(
                "🔑 API Keys",
                callback_data="admin_keys",
            ),
        ],
        [
            InlineKeyboardButton(
                "📈 API Usage",
                callback_data="admin_usage",
            ),
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
                "🔴 API OFF",
                callback_data="admin_apioff",
            ),
            InlineKeyboardButton(
                "🟢 API ON",
                callback_data="admin_apion",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔒 Revoke API",
                callback_data="admin_revoke",
            ),
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
                callback_data="docs",
            ),
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

    if (
        not is_owner(user.id)
        and database.is_user_blocked(user.id)
    ):
        await update.message.reply_text(
            "🚫 Your account is blocked."
        )
        return

    text = (
        "🔥 KRUTIK CYBER EXPERT\n\n"
        "Welcome to the API service.\n\n"
        "Choose an option below:"
    )

    await update.message.reply_text(
        text,
        reply_markup=user_menu_keyboard(),
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
        "👑 ADMIN PANEL\n\n"
        "Select an option:",
        reply_markup=admin_menu_keyboard(),
    )


# =========================================================
# USER CALLBACKS
# =========================================================

async def plans_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🔑 API PLANS\n\n"
        "🟢 BASIC\n"
        "• 1,000 requests/day\n"
        "• 30 days\n\n"
        "🔵 PRO\n"
        "• 10,000 requests/day\n"
        "• 30 days\n\n"
        "🟣 CUSTOM\n"
        "• 50,000 requests/day\n"
        "• 30 days\n\n"
        "Access is manually approved."
    )


async def request_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🟢 Basic",
                callback_data="request_basic",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔵 Pro",
                callback_data="request_pro",
            ),
        ],
        [
            InlineKeyboardButton(
                "🟣 Custom",
                callback_data="request_custom",
            ),
        ],
    ])

    await query.edit_message_text(
        "🚀 SELECT API PLAN",
        reply_markup=keyboard,
    )


async def submit_request_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    if database.is_user_blocked(user.id):
        await query.edit_message_text(
            "🚫 Your account is blocked."
        )
        return

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
            keyboard = InlineKeyboardMarkup([
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
            ])

            await context.bot.send_message(
                chat_id=int(
                    OWNER_CHAT_ID
                ),
                text=(
                    "🔔 NEW API ACCESS REQUEST\n\n"
                    f"Request ID: {request_id}\n"
                    f"User ID: {user.id}\n"
                    f"Username: @{user.username or 'none'}\n"
                    f"Plan: {plan.upper()}"
                ),
                reply_markup=keyboard,
            )

        except Exception as exc:
            print(
                "OWNER NOTIFICATION ERROR:",
                exc,
            )

    await query.edit_message_text(
        "✅ REQUEST SUBMITTED\n\n"
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

    keys = database.get_user_keys(
        user.id
    )

    if not keys:
        await query.edit_message_text(
            "🔐 You don't have any API keys yet."
        )
        return

    lines = [
        "🔐 YOUR API KEYS",
        "",
    ]

    for key in keys:
        lines.append(
            f"ID: {key['id']}\n"
            f"Plan: {key['plan'].upper()}\n"
            f"Status: {key['status']}\n"
            f"Requests: {key['total_requests']}\n"
            f"Expires: {key['expires_at']}\n"
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

    keys = database.get_user_keys(
        user.id
    )

    if not keys:
        await query.edit_message_text(
            "📊 No API usage found."
        )
        return

    key = keys[0]

    user_data = database.get_user(
        user.id
    )

    api_state = (
        "🟢 ON"
        if not user_data
        or user_data.get(
            "api_enabled",
            1,
        )
        else "🔴 OFF"
    )

    await query.edit_message_text(
        "📊 API USAGE\n\n"
        f"Plan: {key['plan'].upper()}\n"
        f"API: {api_state}\n"
        f"Status: {key['status']}\n"
        f"Today: {key['today_requests']}\n"
        f"Daily Limit: {key['daily_limit']}\n"
        f"Total: {key['total_requests']}\n"
        f"Expires: {key['expires_at']}"
    )


async def howto_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    base_url = (
        "https://krutik-cyber-expert-api.onrender.com"
    )

    await query.edit_message_text(
        "📖 HOW TO USE API\n\n"
        "1️⃣ Get your API key after approval.\n\n"
        "2️⃣ Search endpoint:\n"
        f"{base_url}/api/search\n\n"
        "3️⃣ Parameters:\n"
        "api_key = YOUR_API_KEY\n"
        "query = YOUR_SEARCH_VALUE\n"
        "limit = 20\n\n"
        "Example:\n"
        f"{base_url}/api/search?"
        "api_key=YOUR_KEY&"
        "query=TEST123&"
        "limit=20\n\n"
        "4️⃣ The response is JSON.\n\n"
        "🔐 Keep your API key private.\n\n"
        "📚 Full documentation:\n"
        f"{base_url}/docs"
    )


async def docs_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    url = (
        "https://krutik-cyber-expert-api.onrender.com/docs"
    )

    await query.edit_message_text(
        "📚 API DOCUMENTATION\n\n"
        f"{url}\n\n"
        "GET /api/search\n"
        "GET /api/status\n\n"
        "Search parameters:\n"
        "• api_key\n"
        "• query\n"
        "• limit"
    )


# =========================================================
# ADMIN CALLBACKS
# =========================================================

async def admin_callback_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    user = query.from_user

    if not is_owner(user.id):
        await query.answer(
            "Owner only.",
            show_alert=True,
        )
        return

    await query.answer()

    data = query.data

    # -----------------------------------------------------
    # Dashboard
    # -----------------------------------------------------

    if data == "admin_dashboard":
        stats = database.get_usage_stats()

        await query.edit_message_text(
            "📊 ADMIN DASHBOARD\n\n"
            f"👥 Users: {stats['users']}\n"
            f"🚫 Blocked: {stats['blocked']}\n"
            f"🟢 API ON: {stats['api_enabled']}\n"
            f"🔴 API OFF: {stats['api_disabled']}\n\n"
            f"🔑 Total Keys: {stats['keys']}\n"
            f"🟢 Active Keys: {stats['active_keys']}\n"
            f"🔒 Revoked: {stats['revoked_keys']}\n"
            f"⌛ Expired: {stats['expired_keys']}\n\n"
            f"📨 Pending: {stats['pending']}\n"
            f"📡 Requests: {stats['requests']}\n"
            f"✅ Successful: {stats['successful']}\n"
            f"❌ Failed: {stats['failed']}\n"
            f"📈 Total Usage: {stats['total_usage']}",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Admin Panel",
                        callback_data="admin_home",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # Pending
    # -----------------------------------------------------

    if data == "admin_pending":
        requests = database.get_pending_requests()

        if not requests:
            text = (
                "📨 PENDING REQUESTS\n\n"
                "✅ No pending requests."
            )

        else:
            text = "📨 PENDING REQUESTS\n\n"

            for req in requests[:15]:
                text += (
                    f"ID: {req['id']}\n"
                    f"User: {req['chat_id']}\n"
                    f"Plan: {req['plan'].upper()}\n"
                    f"@{req.get('username') or 'none'}\n\n"
                )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Admin Panel",
                        callback_data="admin_home",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # Users
    # -----------------------------------------------------

    if data == "admin_users":
        users = database.get_users(30)

        if not users:
            text = "👥 USERS\n\nNo users."
        else:
            text = "👥 USERS\n\n"

            for u in users:
                blocked = (
                    "🚫"
                    if u.get("blocked")
                    else "✅"
                )

                api_state = (
                    "🟢"
                    if u.get("api_enabled", 1)
                    else "🔴"
                )

                text += (
                    f"{blocked} {api_state} "
                    f"ID: {u['chat_id']}\n"
                    f"Username: "
                    f"@{u.get('username') or 'none'}\n"
                    f"Name: "
                    f"{u.get('first_name') or 'none'}\n\n"
                )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Admin Panel",
                        callback_data="admin_home",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # API Keys
    # -----------------------------------------------------

    if data == "admin_keys":
        keys = database.get_all_keys(50)

        if not keys:
            text = "🔑 API KEYS\n\nNo API keys."
        else:
            text = "🔑 API KEYS\n\n"

            for key in keys[:25]:
                text += (
                    f"ID: {key['id']}\n"
                    f"User: {key['chat_id']}\n"
                    f"Plan: {key['plan'].upper()}\n"
                    f"Status: {key['status']}\n"
                    f"Usage: {key['total_requests']}\n\n"
                )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Admin Panel",
                        callback_data="admin_home",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # Usage
    # -----------------------------------------------------

    if data == "admin_usage":
        stats = database.get_usage_stats()

        logs = database.get_recent_logs(10)

        text = (
            "📈 API USAGE\n\n"
            f"Total Requests: {stats['requests']}\n"
            f"Successful: {stats['successful']}\n"
            f"Failed: {stats['failed']}\n"
            f"Total Key Usage: {stats['total_usage']}\n\n"
            "🕘 RECENT REQUESTS\n\n"
        )

        for log in logs:
            text += (
                f"#{log['id']} "
                f"User: {log.get('chat_id')}\n"
                f"Query: {log.get('query', '')[:40]}\n"
                f"Code: {log['status_code']}\n\n"
            )

        await query.edit_message_text(
            text[:3900],
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Admin Panel",
                        callback_data="admin_home",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # Block
    # -----------------------------------------------------

    if data == "admin_block":
        await query.edit_message_text(
            "🚫 BLOCK USER\n\n"
            "Use:\n"
            "/block USER_ID",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Admin Panel",
                        callback_data="admin_home",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # Unblock
    # -----------------------------------------------------

    if data == "admin_unblock":
        await query.edit_message_text(
            "✅ UNBLOCK USER\n\n"
            "Use:\n"
            "/unblock USER_ID",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Admin Panel",
                        callback_data="admin_home",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # API OFF
    # -----------------------------------------------------

    if data == "admin_apioff":
        await query.edit_message_text(
            "🔴 API OFF\n\n"
            "Use:\n"
            "/apioff USER_ID",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Admin Panel",
                        callback_data="admin_home",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # API ON
    # -----------------------------------------------------

    if data == "admin_apion":
        await query.edit_message_text(
            "🟢 API ON\n\n"
            "Use:\n"
            "/apion USER_ID",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Admin Panel",
                        callback_data="admin_home",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # Revoke
    # -----------------------------------------------------

    if data == "admin_revoke":
        await query.edit_message_text(
            "🔒 REVOKE API\n\n"
            "Use:\n"
            "/revoke KEY_ID",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Admin Panel",
                        callback_data="admin_home",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # Delete
    # -----------------------------------------------------

    if data == "admin_delete":
        await query.edit_message_text(
            "🗑️ DELETE API\n\n"
            "Use:\n"
            "/deleteapi KEY_ID",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Admin Panel",
                        callback_data="admin_home",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # Create
    # -----------------------------------------------------

    if data == "admin_create":
        await query.edit_message_text(
            "➕ CREATE API KEY\n\n"
            "Use:\n"
            "/createapi USER_ID PLAN\n\n"
            "Plans:\n"
            "basic\n"
            "pro\n"
            "custom\n\n"
            "Example:\n"
            "/createapi 123456789 pro",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Admin Panel",
                        callback_data="admin_home",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # Home
    # -----------------------------------------------------

    if data == "admin_home":
        await query.edit_message_text(
            "👑 ADMIN PANEL\n\n"
            "Select an option:",
            reply_markup=admin_menu_keyboard(),
        )


# =========================================================
# APPROVE / REJECT
# =========================================================

async def owner_decision_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    user = query.from_user

    if not is_owner(user.id):
        await query.answer(
            "Owner only.",
            show_alert=True,
        )
        return

    await query.answer()

    data = query.data

    if data.startswith("approve_"):
        request_id = int(
            data.replace(
                "approve_",
                "",
            )
        )

        request = database.get_access_request(
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

        database.update_access_request(
            request_id,
            "approved",
        )

        database.save_user(
            request["chat_id"],
            request.get("username"),
            "",
        )

        raw_key, key_id = (
            database.create_api_key(
                request["chat_id"],
                request["plan"],
            )
        )

        try:
            await context.bot.send_message(
                chat_id=int(
                    request["chat_id"]
                ),
                text=(
                    "🎉 API ACCESS APPROVED\n\n"
                    f"Plan: {request['plan'].upper()}\n"
                    f"Key ID: {key_id}\n\n"
                    "🔑 YOUR API KEY:\n\n"
                    f"{raw_key}\n\n"
                    "⚠️ Keep this key private.\n\n"
                    "📖 How to use:\n"
                    "https://krutik-cyber-expert-api.onrender.com/docs"
                ),
            )
        except Exception as exc:
            print(
                "KEY SEND ERROR:",
                exc,
            )

        await query.edit_message_text(
            "✅ REQUEST APPROVED\n\n"
            f"Request ID: {request_id}\n"
            f"User: {request['chat_id']}\n"
            f"Plan: {request['plan'].upper()}\n"
            f"Key ID: {key_id}"
        )

    elif data.startswith("reject_"):
        request_id = int(
            data.replace(
                "reject_",
                "",
            )
        )

        request = database.get_access_request(
            request_id
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
                    "❌ API ACCESS REQUEST REJECTED\n\n"
                    "You can submit a new request later."
                ),
            )
        except Exception as exc:
            print(
                "REJECT SEND ERROR:",
                exc,
            )

        await query.edit_message_text(
            "❌ REQUEST REJECTED\n\n"
            f"Request ID: {request_id}"
        )


# =========================================================
# ADMIN COMMANDS
# =========================================================

async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update):
        return

    stats = database.get_usage_stats()

    await update.message.reply_text(
        "📊 ADMIN STATS\n\n"
        f"Users: {stats['users']}\n"
        f"Blocked: {stats['blocked']}\n"
        f"API ON: {stats['api_enabled']}\n"
        f"API OFF: {stats['api_disabled']}\n"
        f"Keys: {stats['keys']}\n"
        f"Active Keys: {stats['active_keys']}\n"
        f"Pending: {stats['pending']}\n"
        f"Requests: {stats['requests']}\n"
        f"Successful: {stats['successful']}\n"
        f"Failed: {stats['failed']}"
    )


async def pending_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update):
        return

    requests = database.get_pending_requests()

    if not requests:
        await update.message.reply_text(
            "✅ No pending requests."
        )
        return

    text = "📨 PENDING REQUESTS\n\n"

    for req in requests:
        text += (
            f"ID: {req['id']}\n"
            f"User: {req['chat_id']}\n"
            f"Plan: {req['plan'].upper()}\n"
            f"Status: {req['status']}\n\n"
        )

    await update.message.reply_text(
        text[:4000]
    )


async def block_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/block USER_ID"
        )
        return

    try:
        user_id = int(
            context.args[0]
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid USER_ID."
        )
        return

    database.block_user(user_id)

    await update.message.reply_text(
        f"🚫 User {user_id} blocked."
    )


async def unblock_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/unblock USER_ID"
        )
        return

    try:
        user_id = int(
            context.args[0]
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid USER_ID."
        )
        return

    database.unblock_user(user_id)

    await update.message.reply_text(
        f"✅ User {user_id} unblocked."
    )


async def apioff_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/apioff USER_ID"
        )
        return

    try:
        user_id = int(
            context.args[0]
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid USER_ID."
        )
        return

    if database.api_off(user_id):
        await update.message.reply_text(
            f"🔴 API OFF for {user_id}."
        )
    else:
        await update.message.reply_text(
            "❌ User not found."
        )


async def apion_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/apion USER_ID"
        )
        return

    try:
        user_id = int(
            context.args[0]
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid USER_ID."
        )
        return

    if database.api_on(user_id):
        await update.message.reply_text(
            f"🟢 API ON for {user_id}."
        )
    else:
        await update.message.reply_text(
            "❌ User not found."
        )


async def revoke_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/revoke KEY_ID"
        )
        return

    try:
        key_id = int(
            context.args[0]
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid KEY_ID."
        )
        return

    if database.revoke_key(key_id):
        await update.message.reply_text(
            f"🔒 API key {key_id} revoked."
        )
    else:
        await update.message.reply_text(
            "❌ API key not found."
        )


async def delete_api_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/deleteapi KEY_ID"
        )
        return

    try:
        key_id = int(
            context.args[0]
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid KEY_ID."
        )
        return

    key = database.get_key_by_id(
        key_id
    )

    if not key:
        await update.message.reply_text(
            "❌ API key not found."
        )
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🗑️ YES, DELETE",
                callback_data=(
                    f"confirm_delete_{key_id}"
                ),
            ),
            InlineKeyboardButton(
                "❌ CANCEL",
                callback_data="cancel_delete",
            ),
        ]
    ])

    await update.message.reply_text(
        "⚠️ DELETE API\n\n"
        f"Key ID: {key_id}\n"
        f"User: {key['chat_id']}\n"
        f"Plan: {key['plan'].upper()}\n"
        f"Status: {key['status']}\n\n"
        "Are you sure?",
        reply_markup=keyboard,
    )


async def create_api_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "/createapi USER_ID PLAN\n\n"
            "Example:\n"
            "/createapi 123456789 pro"
        )
        return

    try:
        user_id = int(
            context.args[0]
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid USER_ID."
        )
        return

    plan = context.args[1].lower()

    if plan not in (
        "basic",
        "pro",
        "custom",
    ):
        await update.message.reply_text(
            "❌ Plan must be basic, pro or custom."
        )
        return

    database.save_user(
        user_id,
        "",
        "",
    )

    raw_key, key_id = (
        database.create_api_key(
            user_id,
            plan,
        )
    )

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🔑 API KEY CREATED BY OWNER\n\n"
                f"Plan: {plan.upper()}\n"
                f"Key ID: {key_id}\n\n"
                f"{raw_key}\n\n"
                "⚠️ Keep this key private.\n\n"
                "📖 Docs:\n"
                "https://krutik-cyber-expert-api.onrender.com/docs"
            ),
        )
    except Exception:
        pass

    await update.message.reply_text(
        "✅ API KEY CREATED\n\n"
        f"User: {user_id}\n"
        f"Plan: {plan.upper()}\n"
        f"Key ID: {key_id}\n\n"
        f"API Key:\n{raw_key}"
    )


# =========================================================
# DELETE CONFIRMATION CALLBACK
# =========================================================

async def delete_confirmation_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    user = query.from_user

    if not is_owner(user.id):
        await query.answer(
            "Owner only.",
            show_alert=True,
        )
        return

    await query.answer()

    data = query.data

    if data == "cancel_delete":
        await query.edit_message_text(
            "❌ Delete cancelled."
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

        key = database.get_key_by_id(
            key_id
        )

        if not key:
            await query.edit_message_text(
                "❌ API key already deleted."
            )
            return

        deleted = database.delete_key(
            key_id
        )

        if deleted:
            await query.edit_message_text(
                "🗑️ API DELETED\n\n"
                f"Key ID: {key_id}\n"
                f"User: {key['chat_id']}\n"
                f"Plan: {key['plan'].upper()}"
            )
        else:
            await query.edit_message_text(
                "❌ Delete failed."
            )


# =========================================================
# API SERVER
# =========================================================

def run_api():
    print(
        f"🌐 FastAPI starting on port {PORT}"
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
    print("=" * 55)
    print(APP_NAME)
    print("Telegram Bot + FastAPI + Admin Panel")
    print("=" * 55)

    database.init_db()

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    if not OWNER_CHAT_ID:
        print(
            "⚠️ WARNING: OWNER_CHAT_ID is not configured."
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

    # Commands
    telegram_app.add_handler(
        CommandHandler(
            "start",
            start_command,
        )
    )

    telegram_app.add_handler(
        CommandHandler(
            "admin",
            admin_command,
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
        CommandHandler(
            "block",
            block_command,
        )
    )

    telegram_app.add_handler(
        CommandHandler(
            "unblock",
            unblock_command,
        )
    )

    telegram_app.add_handler(
        CommandHandler(
            "apioff",
            apioff_command,
        )
    )

    telegram_app.add_handler(
        CommandHandler(
            "apion",
            apion_command,
        )
    )

    telegram_app.add_handler(
        CommandHandler(
            "revoke",
            revoke_command,
        )
    )

    telegram_app.add_handler(
        CommandHandler(
            "deleteapi",
            delete_api_command,
        )
    )

    telegram_app.add_handler(
        CommandHandler(
            "createapi",
            create_api_command,
        )
    )

    # User callbacks
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
            pattern=(
                "^request_"
                "(basic|pro|custom)$"
            ),
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
            howto_callback,
            pattern="^howto$",
        )
    )

    telegram_app.add_handler(
        CallbackQueryHandler(
            docs_callback,
            pattern="^docs$",
        )
    )

    # Admin panel
    telegram_app.add_handler(
        CallbackQueryHandler(
            admin_callback_router,
            pattern="^admin_",
        )
    )

    # Approve / reject
    telegram_app.add_handler(
        CallbackQueryHandler(
            owner_decision_callback,
            pattern=(
                "^(approve|reject)_\\d+$"
            ),
        )
    )

    # Delete confirmation
    telegram_app.add_handler(
        CallbackQueryHandler(
            delete_confirmation_callback,
            pattern=(
                "^(confirm_delete_\\d+|"
                "cancel_delete)$"
            ),
        )
    )

    print(
        "🤖 Telegram bot starting..."
    )

    telegram_app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
