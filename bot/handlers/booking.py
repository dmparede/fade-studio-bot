"""Booking conversation: name -> service -> preferred day/time -> confirm."""

import logging
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .. import keyboards
from ..business import format_price, get_service, load_business_info
from .general import notify_admin, start, user_label

logger = logging.getLogger(__name__)

NAME, SERVICE, DATETIME, CONFIRM = range(4)
MAX_FIELD_LENGTH = 100


def _summary_html(draft: dict) -> str:
    return (
        f"👤 Name: <b>{escape(draft['name'])}</b>\n"
        f"✂️ Service: <b>{escape(draft['service_name'])}</b> ({format_price(draft['price'])})\n"
        f"🕒 Preferred time: <b>{escape(draft['preferred_time'])}</b>"
    )


async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data["booking"] = {}
    await update.effective_message.reply_text(
        "Let's get you booked in! 📅\n\nFirst, what name should we put the appointment under?\n"
        "(Send /cancel at any time to stop.)"
    )
    return NAME


async def got_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.effective_message.text.strip()
    if not name or len(name) > MAX_FIELD_LENGTH:
        await update.effective_message.reply_text("Please send a valid name (up to 100 characters).")
        return NAME

    context.user_data["booking"]["name"] = name
    await update.effective_message.reply_text(
        f"Nice to meet you, {name}! Which service would you like?",
        reply_markup=keyboards.services_picker(),
    )
    return SERVICE


async def got_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    service = get_service(query.data.removeprefix(keyboards.CB_SERVICE_PREFIX))
    if service is None:
        await query.message.reply_text(
            "That service isn't available anymore, please pick another one.",
            reply_markup=keyboards.services_picker(),
        )
        return SERVICE

    context.user_data["booking"].update(
        service_id=service["id"], service_name=service["name"], price=service["price"]
    )
    await query.edit_message_text(f"✂️ {service['name']} - {format_price(service['price'])}")

    hours = "\n".join(f"{day}: {h}" for day, h in load_business_info()["hours"].items())
    await query.message.reply_text(
        "Great choice! What day and time would suit you best?\n"
        "For example: \"Friday at 15:00\" or \"Saturday morning\".\n\n"
        f"Our opening hours:\n{hours}"
    )
    return DATETIME


async def service_not_picked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Please pick a service using the buttons below.", reply_markup=keyboards.services_picker()
    )
    return SERVICE


async def got_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    preferred_time = update.effective_message.text.strip()
    if not preferred_time or len(preferred_time) > MAX_FIELD_LENGTH:
        await update.effective_message.reply_text(
            "Please tell me a day and time (up to 100 characters)."
        )
        return DATETIME

    draft = context.user_data["booking"]
    draft["preferred_time"] = preferred_time
    await update.effective_message.reply_text(
        f"Here's your booking request:\n\n{_summary_html(draft)}\n\nShall I send it?",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.confirm_booking(),
    )
    return CONFIRM


async def confirm_not_tapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Please tap ✅ Confirm to send your request, or ✖ Cancel to stop.",
        reply_markup=keyboards.confirm_booking(),
    )
    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    draft = context.user_data.pop("booking", None)
    if not draft:
        await query.edit_message_text("This booking has expired. Send /book to start again.")
        return ConversationHandler.END

    user = update.effective_user
    booking = await context.bot_data["bookings"].append(
        {
            "telegram_user_id": user.id,
            "telegram_username": user.username,
            **draft,
            "status": "pending",
        }
    )
    logger.info("Booking %s saved for user %s", booking["id"], user.id)

    await query.edit_message_text(
        f"✅ <b>Booking request sent!</b> (ref. #{booking['id']})\n\n{_summary_html(draft)}\n\n"
        "The team will confirm your slot here shortly. See you soon! 💈",
        parse_mode=ParseMode.HTML,
    )
    await notify_admin(
        context,
        f"📅 <b>New booking request</b> (#{booking['id']})\n"
        f"From: {escape(user_label(user))} - <a href=\"tg://user?id={user.id}\">open chat</a>\n\n"
        f"{_summary_html(draft)}",
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("booking", None)
    text = "No problem, booking cancelled. Send /start whenever you need me."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text)
    else:
        await update.effective_message.reply_text(text)
    return ConversationHandler.END


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("booking", None)
    await start(update, context)
    return ConversationHandler.END


def build_booking_handler() -> ConversationHandler:
    text = filters.TEXT & ~filters.COMMAND
    cancel_button = CallbackQueryHandler(cancel, pattern=f"^{keyboards.CB_CANCEL}$")

    return ConversationHandler(
        entry_points=[
            CommandHandler("book", begin),
            CallbackQueryHandler(begin, pattern=f"^{keyboards.CB_BOOK}$"),
        ],
        states={
            NAME: [MessageHandler(text, got_name)],
            SERVICE: [
                CallbackQueryHandler(got_service, pattern=f"^{keyboards.CB_SERVICE_PREFIX}"),
                MessageHandler(text, service_not_picked),
            ],
            DATETIME: [MessageHandler(text, got_datetime)],
            CONFIRM: [
                CallbackQueryHandler(confirm, pattern=f"^{keyboards.CB_CONFIRM}$"),
                MessageHandler(text, confirm_not_tapped),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", restart),
            cancel_button,
        ],
        allow_reentry=True,
    )
