"""/start, menu buttons, AI free-text answers and human handoff."""

import logging
from html import escape

from telegram import Update, User
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from .. import keyboards
from ..business import load_business_info, services_html

logger = logging.getLogger(__name__)

HISTORY_TURNS = 6  # messages of chat history sent to the AI for context


def user_label(user: User) -> str:
    return f"{user.full_name} (@{user.username})" if user.username else user.full_name


async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Send an HTML message to the staff chat, if ADMIN_CHAT_ID is configured."""
    admin_chat_id = context.bot_data["settings"].admin_chat_id
    if admin_chat_id is None:
        return
    try:
        await context.bot.send_message(admin_chat_id, text, parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("Could not notify admin chat %s", admin_chat_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    info = load_business_info()
    name = escape(update.effective_user.first_name or "there")
    await update.effective_message.reply_text(
        f"Hey {name}, welcome to <b>{escape(info['name'])}</b> 💈\n"
        f"<i>{escape(info['tagline'])}</i>\n\n"
        "I can show you our services and prices, book an appointment, "
        "or answer questions about the shop. Just tap a button or type your question.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.main_menu(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "/start - main menu\n"
        "/services - services, prices and opening hours\n"
        "/book - request an appointment\n"
        "/human - talk to a member of the team\n"
        "/cancel - cancel the current booking\n\n"
        "You can also just type a question, like \"Are you open on Saturday?\"",
    )


async def show_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()
    await update.effective_message.reply_text(
        services_html(), parse_mode=ParseMode.HTML, reply_markup=keyboards.main_menu()
    )


async def talk_to_human(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()

    user = update.effective_user
    question = context.user_data.pop("unanswered_question", None)

    handoff = await context.bot_data["handoffs"].append(
        {
            "telegram_user_id": user.id,
            "telegram_username": user.username,
            "customer_name": user.full_name,
            "reason": "ai_could_not_answer" if question else "customer_request",
            "question": question,
            "status": "open",
        }
    )
    logger.info("Human handoff %s requested by %s", handoff["id"], user.id)

    admin_text = (
        f"🙋 <b>Human support requested</b> (#{handoff['id']})\n"
        f"From: {escape(user_label(user))} - <a href=\"tg://user?id={user.id}\">open chat</a>"
    )
    if question:
        admin_text += f"\nQuestion: {escape(question)}"
    await notify_admin(context, admin_text)

    phone = load_business_info().get("phone")
    await update.effective_message.reply_text(
        "Done! I've passed this on to the team, and someone will get back to you here soon.\n"
        + (f"If it's urgent, you can also call us at {phone}." if phone else "")
    )


async def ai_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = update.effective_message.text.strip()
    if not question:
        return

    await update.effective_chat.send_action(ChatAction.TYPING)

    history: list[dict[str, str]] = context.user_data.setdefault("history", [])
    reply = await context.bot_data["ai"].answer(question, history[-HISTORY_TURNS:])

    if reply.needs_human:
        logger.info("AI could not answer for user %s: %r", update.effective_user.id, question)
        context.user_data["unanswered_question"] = question
        if reply.failed:
            text = (
                "Sorry, I'm having trouble answering right now. Please try again in a minute, "
                "or I can forward your question to the team."
            )
        else:
            text = (
                "I'm not sure about that one, and I'd rather not give you wrong information. "
                "Do you want me to forward your question to the team?"
            )
        await update.effective_message.reply_text(text, reply_markup=keyboards.offer_human())
        return

    history.extend([{"role": "user", "text": question}, {"role": "model", "text": reply.text}])
    del history[:-HISTORY_TURNS]
    await update.effective_message.reply_text(reply.text)


async def stale_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Buttons from a finished or expired flow (e.g. tapping Confirm twice)."""
    await update.callback_query.answer("This button has expired. Send /start for the menu.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled error while processing update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Sorry, something went wrong on our side. Please try again in a moment."
        )
