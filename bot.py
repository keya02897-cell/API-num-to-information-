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


def back_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="home",
            )
        ]
    ])


# =========================================================
# USER MENU
# =========================================================

def user_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                database.get_setting(
                    "button_plans",
                    "🔑 API Plans",
                ),
                callback_data="plans",
            )
        ],
        [
            InlineKeyboardButton(
                database.get_setting(
                    "button_request",
                    "🚀 Request API Access",
                ),
                callback_data="request",
            )
        ],
        [
            InlineKeyboardButton(
                database.get_setting(
                    "button_keys",
                    "🔐 My API Keys",
                ),
                callback_data="keys",
            )
        ],
        [
            InlineKeyboardButton(
                database.get_setting(
                    "button_usage",
                    "📊 My Usage",
                ),
                callback_data="usage",
            )
        ],
        [
            InlineKeyboardButton(
                database.get_setting(
                    "button_howto",
                    "📖 How to Use API",
                ),
                callback_data="howto",
            )
        ],
        [
            InlineKeyboardButton(
                database.get_setting(
                    "button_docs",
                    "📚 API Docs",
                ),
                callback_data="docs",
            )
        ],
        [
            InlineKeyboardButton(
                database.get_setting(
                    "button_support",
                    "🆘 Support",
                ),
                callback_data="support",
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
                "📨 Requests",
                callback_data="admin_pending",
            )
        ],
        [
            InlineKeyboardButton(
                "👥 Users",
                callback_data="admin_users",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔑 API Keys",
                callback_data="admin_keys",
            ),
        ],
        [
            InlineKeyboardButton(
                "📈 Usage",
                callback_data="admin_usage",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎨 Customize Panel",
                callback_data="admin_customize",
            ),
        ],
        [
            InlineKeyboardButton(
                "⚙️ API Settings",
                callback_data="admin_settings",
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
                "📖 API Docs",
                callback_data="admin_docs",
            )
        ],
    ])


# =========================================================
# START
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
            "🚫 Access blocked."
        )
        return

    await update.message.reply_text(
        database.get_setting(
            "welcome_text",
            "Welcome!",
        ),
        reply_markup=user_menu(),
    )


# =========================================================
# ADMIN
# =========================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update):
        return

    await update.message.reply_text(
        f"👑 {APP_NAME}\n\n"
        "ADMIN PANEL",
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

    basic_daily = database.get_setting(
        "basic_daily",
        "1000",
    )

    basic_days = database.get_setting(
        "basic_days",
        "30",
    )

    pro_daily = database.get_setting(
        "pro_daily",
        "10000",
    )

    pro_days = database.get_setting(
        "pro_days",
        "30",
    )

    custom_daily = database.get_setting(
        "custom_daily",
        "50000",
    )

    custom_days = database.get_setting(
        "custom_days",
        "30",
    )

    text = (
        f"🔑 {APP_NAME}\n\n"
        "API PLANS\n\n"
        f"🟢 BASIC\n"
        f"• {basic_daily} requests/day\n"
        f"• {basic_days} days\n\n"
        f"🔵 PRO\n"
        f"• {pro_daily} requests/day\n"
        f"• {pro_days} days\n\n"
        f"🟣 CUSTOM\n"
        f"• {custom_daily} requests/day\n"
        f"• {custom_days} days\n\n"
        "Access requires owner approval."
    )

    await query.edit_message_text(
        text,
        reply_markup=back_markup(),
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
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="home",
            )
        ],
    ]

    await query.edit_message_text(
        "🚀 Select API plan:",
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
                    f"🔔 {APP_NAME}\n\n"
                    "NEW API REQUEST\n\n"
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
        f"✅ Request submitted.\n\n"
        f"Request ID: {request_id}\n"
        f"Plan: {plan.upper()}\n\n"
        "Please wait for owner approval.",
        reply_markup=back_markup(),
    )


async def keys_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    keys = database.get_user_keys(
        query.from_user.id
    )

    if not keys:
        await query.edit_message_text(
            "🔐 You don't have any API keys.",
            reply_markup=back_markup(),
        )
        return

    lines = [
        "🔐 YOUR API KEYS",
        "",
    ]

    for key in keys:
        lines.extend([
            f"🆔 ID: {key['id']}",
            f"📛 Name: {key['key_name']}",
            f"📦 Plan: {key['plan'].upper()}",
            f"📌 Status: {key['status']}",
            f"📊 Today: "
            f"{key['today_requests']}/"
            f"{key['daily_limit']}",
            f"📈 Total: "
            f"{key['total_requests']}/"
            f"{key['total_limit'] or '∞'}",
            f"⏱ Rate/min: "
            f"{key['rate_limit'] or '∞'}",
            f"⌛ Expiry: "
            f"{key['expires_at'] or 'Never'}",
            "",
        ])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=back_markup(),
    )


async def usage_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    keys = database.get_user_keys(
        query.from_user.id
    )

    if not keys:
        await query.edit_message_text(
            "📊 No API usage found.",
            reply_markup=back_markup(),
        )
        return

    lines = [
        "📊 MY API USAGE",
        "",
    ]

    for key in keys:
        daily_remaining = max(
            0,
            key["daily_limit"]
            - key["today_requests"],
        )

        total_remaining = (
            "∞"
            if key["total_limit"] is None
            else max(
                0,
                key["total_limit"]
                - key["total_requests"],
            )
        )

        lines.extend([
            f"🔑 {key['key_name']}",
            f"Today: "
            f"{key['today_requests']}/"
            f"{key['daily_limit']}",
            f"Remaining: {daily_remaining}",
            f"Total: "
            f"{key['total_requests']}/"
            f"{key['total_limit'] or '∞'}",
            f"Total Remaining: "
            f"{total_remaining}",
            "",
        ])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=back_markup(),
    )


async def howto_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    api_url = database.get_setting(
        "api_url"
    )

    text = database.get_setting(
        "howto_text"
    )

    text += (
        f"\n\nEndpoint:\n"
        f"{api_url}/api/search\n\n"
        "Example:\n"
        f"{api_url}/api/search?"
        "api_key=YOUR_KEY&"
        "query=TEST&limit=20\n\n"
        f"Docs:\n"
        f"{api_url}/docs"
    )

    await query.edit_message_text(
        text,
        reply_markup=back_markup(),
    )


async def docs_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    api_url = database.get_setting(
        "api_url"
    )

    text = database.get_setting(
        "docs_text"
    )

    text += (
        f"\n\n{api_url}/docs"
    )

    await query.edit_message_text(
        text,
        reply_markup=back_markup(),
    )


async def support_callback(
    update,
    context,
):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        database.get_setting(
            "support_text"
        ),
        reply_markup=back_markup(),
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

    if not is_owner(
        query.from_user.id
    ):
        await query.answer(
            "Owner only.",
            show_alert=True,
        )
        return

    data = query.data

    if data == "admin_dashboard":

        stats = database.get_usage_stats()

        status = (
            "🟢 ON"
            if stats["global_api_enabled"]
            else "🔴 OFF"
        )

        await query.edit_message_text(
            f"📊 {APP_NAME}\n\n"
            f"API: {status}\n\n"
            f"👥 Users: {stats['users']}\n"
            f"🚫 Blocked: {stats['blocked']}\n"
            f"🔑 Keys: {stats['keys']}\n"
            f"🟢 Active: {stats['active_keys']}\n"
            f"🔒 Revoked: {stats['revoked_keys']}\n"
            f"⌛ Expired: {stats['expired_keys']}\n"
            f"📈 Requests: {stats['requests']}\n"
            f"✅ Success: {stats['successful']}\n"
            f"❌ Failed: {stats['failed']}\n"
            f"📨 Pending: {stats['pending']}\n"
            f"📊 Total Usage: {stats['total_usage']}",
            reply_markup=admin_menu(),
        )
        return

    if data == "admin_pending":

        requests = database.get_pending_requests()

        if not requests:
            text = "📨 No pending requests."

        else:
            lines = [
                "📨 PENDING REQUESTS",
                "",
            ]

            for req in requests:
                lines.extend([
                    f"ID: {req['id']}",
                    f"User: {req['chat_id']}",
                    f"Plan: {req['plan'].upper()}",
                    "",
                ])

            text = "\n".join(lines)

        await query.edit_message_text(
            text,
            reply_markup=admin_menu(),
        )
        return

    if data == "admin_users":

        users = database.get_users(50)

        lines = [
            "👥 USERS",
            "",
        ]

        for user in users:
            lines.append(
                f"{'🚫' if user['blocked'] else '🟢'} "
                f"{user['chat_id']} "
                f"@{user['username'] or 'none'}"
            )

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=admin_menu(),
        )
        return

    if data == "admin_keys":

        keys = database.get_all_keys(50)

        lines = [
            "🔑 API KEYS",
            "",
        ]

        for key in keys:
            lines.extend([
                f"ID: {key['id']}",
                f"User: {key['chat_id']}",
                f"Name: {key['key_name']}",
                f"Plan: {key['plan'].upper()}",
                f"Status: {key['status']}",
                "",
            ])

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=admin_menu(),
        )
        return

    if data == "admin_usage":

        logs = database.get_recent_logs(30)

        lines = [
            "📈 RECENT API USAGE",
            "",
        ]

        for log in logs:
            icon = (
                "✅"
                if log["success"]
                else "❌"
            )

            lines.append(
                f"{icon} "
                f"User:{log['chat_id']} "
                f"HTTP:{log['status_code']} "
                f"Query:{log['query'][:30]}"
            )

        await query.edit_message_text(
            "\n".join(lines) or "No requests.",
            reply_markup=admin_menu(),
        )
        return

    if data == "admin_customize":

        await query.edit_message_text(
            "🎨 CUSTOMIZE USER PANEL\n\n"
            "Commands:\n\n"
            "/setwelcome TEXT\n"
            "/setsupport TEXT\n"
            "/sethowto TEXT\n"
            "/setdocs TEXT\n"
            "/setapiurl URL\n\n"
            "Button names:\n"
            "/setbutton plans TEXT\n"
            "/setbutton request TEXT\n"
            "/setbutton keys TEXT\n"
            "/setbutton usage TEXT\n"
            "/setbutton howto TEXT\n"
            "/setbutton docs TEXT\n"
            "/setbutton support TEXT\n\n"
            "Plans:\n"
            "/setplan basic DAILY DAYS\n"
            "/setplan pro DAILY DAYS\n"
            "/setplan custom DAILY DAYS",
            reply_markup=admin_menu(),
        )
        return

    if data == "admin_settings":

        files = os.listdir(
            os.getenv("DATA_DIR", "data")
        ) if os.path.exists(
            os.getenv("DATA_DIR", "data")
        ) else []

        json_count = len([
            x for x in files
            if x.lower().endswith(".json")
        ])

        await query.edit_message_text(
            f"⚙️ API SETTINGS\n\n"
            f"API: "
            f"{'🟢 ON' if database.is_global_api_enabled() else '🔴 OFF'}\n"
            f"JSON datasets: {json_count}\n"
            f"API URL:\n"
            f"{database.get_setting('api_url')}",
            reply_markup=admin_menu(),
        )
        return

    if data == "admin_apion":

        database.set_global_api_enabled(True)

        await query.edit_message_text(
            "🟢 Global API enabled.",
            reply_markup=admin_menu(),
        )
        return

    if data == "admin_apioff":

        database.set_global_api_enabled(False)

        await query.edit_message_text(
            "🔴 Global API disabled.",
            reply_markup=admin_menu(),
        )
        return

    if data == "admin_docs":

        api_url = database.get_setting(
            "api_url"
        )

        await query.edit_message_text(
            f"📖 API DOCS\n\n"
            f"{api_url}/docs\n\n"
            f"{api_url}/health\n\n"
            f"{api_url}/api/stats",
            reply_markup=admin_menu(),
        )
        return

    if data == "home":

        await query.edit_message_text(
            database.get_setting(
                "welcome_text"
            ),
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
        return

    data = query.data

    request_id = int(
        data.split("_")[-1]
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
            "⚠️ Already processed."
        )
        return

    if data.startswith("approve_"):

        plan = request["plan"]

        daily = int(
            database.get_setting(
                f"{plan}_daily",
                "50000",
            )
        )

        days = int(
            database.get_setting(
                f"{plan}_days",
                "30",
            )
        )

        expires = None

        if days > 0:
            expires = (
                datetime.now(
                    timezone.utc
                )
                + timedelta(days=days)
            ).isoformat()

        raw_key, key_id = (
            database.create_api_key(
                request["chat_id"],
                plan=plan,
                key_name=(
                    f"{plan.upper()} API"
                ),
                daily_limit=daily,
                total_limit=None,
                expires_at=expires,
                rate_limit=None,
            )
        )

        database.update_access_request(
            request_id,
            "approved",
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
                    "🔑 API KEY:\n\n"
                    f"{raw_key}\n\n"
                    "⚠️ Save this key now.\n\n"
                    f"📚 Docs:\n"
                    f"{database.get_setting('api_url')}/docs"
                ),
            )
        except Exception as exc:
            print(
                "KEY SEND ERROR:",
                exc,
            )

        await query.edit_message_text(
            f"✅ Request approved.\n\n"
            f"Request ID: {request_id}\n"
            f"Key ID: {key_id}"
        )

    else:

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
            f"❌ Request rejected.\n\n"
            f"Request ID: {request_id}"
        )


# =========================================================
# OWNER CUSTOMIZATION COMMANDS
# =========================================================

async def setwelcome_command(update, context):
    if not await owner_only(update):
        return

    text = " ".join(context.args).strip()

    if not text:
        await update.message.reply_text(
            "Usage:\n/setwelcome YOUR TEXT"
        )
        return

    database.set_setting(
        "welcome_text",
        text,
    )

    await update.message.reply_text(
        "✅ Welcome text updated."
    )


async def setsupport_command(update, context):
    if not await owner_only(update):
        return

    text = " ".join(context.args).strip()

    if not text:
        await update.message.reply_text(
            "Usage:\n/setsupport YOUR TEXT"
        )
        return

    database.set_setting(
        "support_text",
        text,
    )

    await update.message.reply_text(
        "✅ Support text updated."
    )


async def sethowto_command(update, context):
    if not await owner_only(update):
        return

    text = " ".join(context.args).strip()

    if not text:
        await update.message.reply_text(
            "Usage:\n/sethowto YOUR TEXT"
        )
        return

    database.set_setting(
        "howto_text",
        text,
    )

    await update.message.reply_text(
        "✅ How-to text updated."
    )


async def setdocs_command(update, context):
    if not await owner_only(update):
        return

    text = " ".join(context.args).strip()

    if not text:
        await update.message.reply_text(
            "Usage:\n/setdocs YOUR TEXT"
        )
        return

    database.set_setting(
        "docs_text",
        text,
    )

    await update.message.reply_text(
        "✅ Documentation text updated."
    )


async def setapiurl_command(update, context):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/setapiurl https://example.com"
        )
        return

    url = context.args[0].rstrip("/")

    database.set_setting(
        "api_url",
        url,
    )

    await update.message.reply_text(
        f"✅ API URL updated:\n{url}"
    )


async def setbutton_command(update, context):
    if not await owner_only(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "/setbutton plans TEXT\n"
            "/setbutton request TEXT\n"
            "/setbutton keys TEXT\n"
            "/setbutton usage TEXT\n"
            "/setbutton howto TEXT\n"
            "/setbutton docs TEXT\n"
            "/setbutton support TEXT"
        )
        return

    button = context.args[0].lower()

    allowed = {
        "plans",
        "request",
        "keys",
        "usage",
        "howto",
        "docs",
        "support",
    }

    if button not in allowed:
        await update.message.reply_text(
            "❌ Invalid button."
        )
        return

    text = " ".join(
        context.args[1:]
    ).strip()

    database.set_setting(
        f"button_{button}",
        text,
    )

    await update.message.reply_text(
        "✅ Button name updated."
    )


async def setplan_command(update, context):
    if not await owner_only(update):
        return

    if len(context.args) != 3:
        await update.message.reply_text(
            "Usage:\n"
            "/setplan basic DAILY DAYS\n\n"
            "Example:\n"
            "/setplan basic 5000 60"
        )
        return

    plan = context.args[0].lower()

    if plan not in {
        "basic",
        "pro",
        "custom",
    }:
        await update.message.reply_text(
            "❌ Plan must be basic, pro or custom."
        )
        return

    try:
        daily = int(context.args[1])
        days = int(context.args[2])

        if daily < 1:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid numbers."
        )
        return

    database.set_setting(
        f"{plan}_daily",
        str(daily),
    )

    database.set_setting(
        f"{plan}_days",
        str(days),
    )

    await update.message.reply_text(
        f"✅ {plan.upper()} updated.\n"
        f"Daily: {daily}\n"
        f"Days: {days}"
    )


# =========================================================
# BLOCK / UNBLOCK
# =========================================================

async def block_command(update, context):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/block USER_ID"
        )
        return

    user_id = int(context.args[0])

    database.block_user(user_id)

    await update.message.reply_text(
        f"🚫 User {user_id} blocked."
    )


async def unblock_command(update, context):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/unblock USER_ID"
        )
        return

    user_id = int(context.args[0])

    database.unblock_user(user_id)

    await update.message.reply_text(
        f"✅ User {user_id} unblocked."
    )


# =========================================================
# API ON/OFF
# =========================================================

async def apion_command(update, context):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/apion USER_ID"
        )
        return

    user_id = int(context.args[0])

    database.api_on(user_id)

    await update.message.reply_text(
        f"🟢 API enabled for {user_id}."
    )


async def apioff_command(update, context):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/apioff USER_ID"
        )
        return

    user_id = int(context.args[0])

    database.api_off(user_id)

    await update.message.reply_text(
        f"🔴 API disabled for {user_id}."
    )


# =========================================================
# GLOBAL
# =========================================================

async def globalon_command(update, context):
    if not await owner_only(update):
        return

    database.set_global_api_enabled(True)

    await update.message.reply_text(
        "🟢 Global API ON."
    )


async def globaloff_command(update, context):
    if not await owner_only(update):
        return

    database.set_global_api_enabled(False)

    await update.message.reply_text(
        "🔴 Global API OFF."
    )


# =========================================================
# CREATE API KEY
# =========================================================

async def createapi_command(update, context):
    if not await owner_only(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "/createapi USER_ID PLAN"
        )
        return

    user_id = int(
        context.args[0]
    )

    plan = context.args[1].lower()

    daily = int(
        database.get_setting(
            f"{plan}_daily",
            "50000",
        )
    )

    days = int(
        database.get_setting(
            f"{plan}_days",
            "30",
        )
    )

    expires = None

    if days > 0:
        expires = (
            datetime.now(
                timezone.utc
            )
            + timedelta(days=days)
        ).isoformat()

    raw_key, key_id = (
        database.create_api_key(
            user_id,
            plan=plan,
            key_name=f"{plan.upper()} API",
            daily_limit=daily,
            expires_at=expires,
        )
    )

    await update.message.reply_text(
        f"🔑 API KEY CREATED\n\n"
        f"User: {user_id}\n"
        f"Key ID: {key_id}\n"
        f"Plan: {plan.upper()}\n"
        f"Daily: {daily}\n"
        f"Days: {days}\n\n"
        f"🔐 KEY:\n{raw_key}"
    )


# =========================================================
# REVOKE / DELETE
# =========================================================

async def revoke_command(update, context):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/revoke KEY_ID"
        )
        return

    key_id = int(context.args[0])

    if database.revoke_key(key_id):
        await update.message.reply_text(
            "🔒 API key revoked."
        )
    else:
        await update.message.reply_text(
            "❌ Key not found/already revoked."
        )


async def deleteapi_command(update, context):
    if not await owner_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/deleteapi KEY_ID"
        )
        return

    key_id = int(context.args[0])

    if database.delete_key(key_id):
        await update.message.reply_text(
            "🗑️ API key deleted."
        )
    else:
        await update.message.reply_text(
            "❌ Key not found."
        )


# =========================================================
# STATS
# =========================================================

async def stats_command(update, context):
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
# API SERVER
# =========================================================

def run_api():
    print(
        f"{APP_NAME} API starting on port {PORT}"
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

    commands = {
        "start": start_command,
        "admin": admin_command,
        "stats": stats_command,
        "block": block_command,
        "unblock": unblock_command,
        "apion": apion_command,
        "apioff": apioff_command,
        "globalon": globalon_command,
        "globaloff": globaloff_command,
        "createapi": createapi_command,
        "revoke": revoke_command,
        "deleteapi": deleteapi_command,

        "setwelcome": setwelcome_command,
        "setsupport": setsupport_command,
        "sethowto": sethowto_command,
        "setdocs": setdocs_command,
        "setapiurl": setapiurl_command,
        "setbutton": setbutton_command,
        "setplan": setplan_command,
    }

    for name, handler in commands.items():
        application.add_handler(
            CommandHandler(
                name,
                handler,
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
            pattern="^request_(basic|pro|custom)$",
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

    application.add_handler(
        CallbackQueryHandler(
            support_callback,
            pattern="^support$",
        )
    )

    # Admin

    application.add_handler(
        CallbackQueryHandler(
            admin_callback,
            pattern="^(admin_|home$)",
        )
    )

    # Approve/reject

    application.add_handler(
        CallbackQueryHandler(
            owner_decision,
            pattern="^(approve|reject)_\\d+$",
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
