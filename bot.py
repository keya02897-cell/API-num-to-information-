import os
import secrets
import asyncio

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
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


BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "",
).strip()

OWNER_CHAT_ID = int(
    os.getenv(
        "OWNER_CHAT_ID",
        "0",
    )
)

PORT = int(
    os.getenv(
        "PORT",
        "10000",
    )
)


APP_NAME = "KRUTIK CYBER EXPERT"


PLANS = {
    "basic": {
        "name": "Basic",
        "daily_limit": 1000,
        "days": 30,
    },
    "pro": {
        "name": "Pro",
        "daily_limit": 10000,
        "days": 30,
    },
    "custom": {
        "name": "Custom",
        "daily_limit": 50000,
        "days": 30,
    },
}


web_app = FastAPI(
    title=f"{APP_NAME} Bot Service"
)


@web_app.get("/")
async def web_root():
    return {
        "service": APP_NAME,
        "status": "online",
        "telegram_bot": "running",
        "api": "running",
    }


@web_app.get("/health")
async def web_health():
    return {
        "status": "ok"
    }


def is_owner(user_id):
    return user_id == OWNER_CHAT_ID


def make_api_key():
    return (
        "KCE_"
        + secrets.token_urlsafe(32)
    )


def main_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📋 API Plans",
                    callback_data="plans",
                )
            ],
            [
                InlineKeyboardButton(
                    "🛒 Request API Access",
                    callback_data="request",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔑 My API Keys",
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
    )


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    database.save_user(
        user.id,
        user.username,
        user.first_name,
    )

    await update.message.reply_text(
        f"🤖 *{APP_NAME}*\n\n"
        "Welcome to the API access panel.\n\n"
        "Use the buttons below.",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def plans(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    text = (
        "📋 *API PLANS*\n\n"
        "🟢 *Basic*\n"
        "• 1,000 requests/day\n"
        "• 30 days\n\n"
        "🔵 *Pro*\n"
        "• 10,000 requests/day\n"
        "• 30 days\n\n"
        "🟣 *Custom*\n"
        "• 50,000 requests/day\n"
        "• Owner approval\n"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🛒 Request Access",
                        callback_data="request",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home",
                    )
                ],
            ]
        ),
    )


async def request_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    keyboard = InlineKeyboardMarkup(
        [
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
    )

    await query.edit_message_text(
        "🛒 *Choose your plan:*",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def submit_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    plan_key: str,
):
    query = update.callback_query
    user = update.effective_user

    database.save_user(
        user.id,
        user.username,
        user.first_name,
    )

    plan = PLANS.get(plan_key)

    if not plan:
        await query.edit_message_text(
            "❌ Invalid plan."
        )
        return

    created, request_id = (
        database.create_access_request(
            user.id,
            plan_key,
        )
    )

    if not created:
        await query.edit_message_text(
            "⚠️ You already have a pending request."
        )
        return

    owner_text = (
        "🔔 *NEW API REQUEST*\n\n"
        f"Request ID: `{request_id}`\n"
        f"User ID: `{user.id}`\n"
        f"Username: @{user.username or 'none'}\n"
        f"Name: {user.first_name or 'Unknown'}\n"
        f"Plan: `{plan['name']}`\n"
        f"Daily Limit: `{plan['daily_limit']}`"
    )

    owner_buttons = InlineKeyboardMarkup(
        [
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
    )

    try:
        await context.bot.send_message(
            OWNER_CHAT_ID,
            owner_text,
            parse_mode="Markdown",
            reply_markup=owner_buttons,
        )
    except Exception as exc:
        print(
            "OWNER MESSAGE ERROR:",
            exc,
        )

    await query.edit_message_text(
        "✅ *Request submitted!*\n\n"
        f"Request ID: `{request_id}`\n"
        f"Plan: `{plan['name']}`\n\n"
        "Wait for owner approval.",
        parse_mode="Markdown",
    )


async def show_keys(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    user = update.effective_user

    rows = database.get_user_keys(
        user.id
    )

    if not rows:
        await query.edit_message_text(
            "🔑 You don't have any API keys.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🛒 Request Access",
                            callback_data="request",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🔙 Back",
                            callback_data="home",
                        )
                    ],
                ]
            ),
        )
        return

    text = "🔑 *MY API KEYS*\n\n"

    for row in rows:
        text += (
            f"ID: `{row['id']}`\n"
            f"Key: `{row['key_prefix']}...`\n"
            f"Plan: `{row['plan']}`\n"
            f"Status: `{row['status']}`\n"
            f"Today: "
            f"`{row['today_requests']}/"
            f"{row['daily_limit']}`\n"
            f"Total: `{row['total_requests']}`\n\n"
        )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home",
                    )
                ]
            ]
        ),
    )


async def show_usage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    user = update.effective_user

    rows = database.get_user_keys(
        user.id
    )

    if not rows:
        text = "📊 No API usage."
    else:
        text = "📊 *MY USAGE*\n\n"

        for row in rows:
            text += (
                f"🔑 Key #{row['id']}\n"
                f"Today: "
                f"{row['today_requests']} / "
                f"{row['daily_limit']}\n"
                f"Total: "
                f"{row['total_requests']}\n\n"
            )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home",
                    )
                ]
            ]
        ),
    )


async def docs(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    text = (
        "📖 *API DOCUMENTATION*\n\n"
        "*Health:*\n"
        "`GET /health`\n\n"
        "*Search:*\n"
        "`GET /api/search`\n\n"
        "*Parameters:*\n"
        "`api_key`\n"
        "`query`\n"
        "`limit` optional\n\n"
        "*Example:*\n"
        "`/api/search?"
        "api_key=YOUR_KEY&"
        "query=Demo`\n\n"
        "*Key status:*\n"
        "`GET /api/status?api_key=YOUR_KEY`"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home",
                    )
                ]
            ]
        ),
    )


async def approve(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request_id: int,
):
    query = update.callback_query
    admin = update.effective_user

    if not is_owner(admin.id):
        await query.answer(
            "Owner only.",
            show_alert=True,
        )
        return

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

    plan = PLANS.get(
        request["plan"]
    )

    if not plan:
        await query.edit_message_text(
            "❌ Invalid plan."
        )
        return

    api_key = make_api_key()

    expires = (
        datetime.now(timezone.utc)
        + timedelta(days=plan["days"])
    )

    database.create_api_key(
        user_id=request["user_id"],
        api_key=api_key,
        plan=request["plan"],
        daily_limit=plan["daily_limit"],
        expires_at=expires.isoformat(),
    )

    database.update_access_request(
        request_id,
        "approved",
    )

    try:
        await context.bot.send_message(
            request["user_id"],
            "🎉 *API ACCESS APPROVED*\n\n"
            f"Plan: `{plan['name']}`\n"
            f"Daily Limit: `{plan['daily_limit']}`\n"
            f"Valid: `{plan['days']} days`\n\n"
            "🔑 *YOUR API KEY:*\n"
            f"`{api_key}`\n\n"
            "⚠️ Keep this key private.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        print(
            "USER MESSAGE ERROR:",
            exc,
        )

    await query.edit_message_text(
        "✅ *REQUEST APPROVED*\n\n"
        f"Request: `{request_id}`\n"
        f"User: `{request['user_id']}`\n"
        f"Plan: `{plan['name']}`",
        parse_mode="Markdown",
    )


async def reject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request_id: int,
):
    query = update.callback_query
    admin = update.effective_user

    if not is_owner(admin.id):
        await query.answer(
            "Owner only.",
            show_alert=True,
        )
        return

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
            request["user_id"],
            "❌ *API REQUEST REJECTED*\n\n"
            f"Request ID: `{request_id}`",
            parse_mode="Markdown",
        )
    except Exception as exc:
        print(
            "USER MESSAGE ERROR:",
            exc,
        )

    await query.edit_message_text(
        f"❌ Request `{request_id}` rejected.",
        parse_mode="Markdown",
    )


async def stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if not is_owner(user.id):
        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    data = database.get_stats()

    await update.message.reply_text(
        "📊 *ADMIN STATS*\n\n"
        f"👥 Users: `{data['users']}`\n"
        f"🔑 Active Keys: `{data['active_keys']}`\n"
        f"📡 Requests: `{data['total_requests']}`\n"
        f"⏳ Pending: `{data['pending']}`",
        parse_mode="Markdown",
    )


async def pending(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if not is_owner(user.id):
        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    rows = database.get_pending_requests()

    if not rows:
        await update.message.reply_text(
            "✅ No pending requests."
        )
        return

    for row in rows:

        text = (
            "⏳ *PENDING REQUEST*\n\n"
            f"ID: `{row['id']}`\n"
            f"User ID: `{row['user_id']}`\n"
            f"Username: "
            f"@{row['username'] or 'none'}\n"
            f"Plan: `{row['plan']}`"
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Approve",
                        callback_data=(
                            f"approve_{row['id']}"
                        ),
                    ),
                    InlineKeyboardButton(
                        "❌ Reject",
                        callback_data=(
                            f"reject_{row['id']}"
                        ),
                    ),
                ]
            ]
        )

        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    await query.answer()

    data = query.data

    if data == "home":

        await query.edit_message_text(
            f"🤖 *{APP_NAME}*\n\n"
            "API access management.",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )

    elif data == "plans":
        await plans(update, context)

    elif data == "request":
        await request_menu(
            update,
            context,
        )

    elif data == "keys":
        await show_keys(
            update,
            context,
        )

    elif data == "usage":
        await show_usage(
            update,
            context,
        )

    elif data == "docs":
        await docs(
            update,
            context,
        )

    elif data.startswith("request_"):

        plan_key = data.replace(
            "request_",
            "",
            1,
        )

        await submit_request(
            update,
            context,
            plan_key,
        )

    elif data.startswith("approve_"):

        request_id = int(
            data.replace(
                "approve_",
                "",
                1,
            )
        )

        await approve(
            update,
            context,
            request_id,
        )

    elif data.startswith("reject_"):

        request_id = int(
            data.replace(
                "reject_",
                "",
                1,
            )
        )

        await reject(
            update,
            context,
            request_id,
        )


async def run_web_server():
    config = uvicorn.Config(
        web_app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )

    server = uvicorn.Server(config)

    await server.serve()


async def run_bot():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing."
        )

    if not OWNER_CHAT_ID:
        raise RuntimeError(
            "OWNER_CHAT_ID is missing."
        )

    database.init_db()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "stats",
            stats,
        )
    )

    application.add_handler(
        CommandHandler(
            "pending",
            pending,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    await application.initialize()

    await application.start()

    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES
    )

    print(
        f"{APP_NAME} Telegram bot started."
    )

    try:
        await asyncio.Event().wait()

    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


async def main():
    await asyncio.gather(
        run_web_server(),
        run_bot(),
    )


if __name__ == "__main__":
    asyncio.run(main())
