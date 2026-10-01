"""Inline keyboards and their callback-data constants."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .business import format_price, load_business_info

CB_SERVICES = "menu:services"
CB_BOOK = "menu:book"
CB_HUMAN = "menu:human"
CB_SERVICE_PREFIX = "book:service:"
CB_CONFIRM = "book:confirm"
CB_CANCEL = "book:cancel"


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💈 Services & Prices", callback_data=CB_SERVICES)],
            [InlineKeyboardButton("📅 Book appointment", callback_data=CB_BOOK)],
            [InlineKeyboardButton("🙋 Talk to a human", callback_data=CB_HUMAN)],
        ]
    )


def services_picker() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{s['name']} - {format_price(s['price'])}",
                callback_data=f"{CB_SERVICE_PREFIX}{s['id']}",
            )
        ]
        for s in load_business_info()["services"]
    ]
    rows.append([InlineKeyboardButton("✖ Cancel", callback_data=CB_CANCEL)])
    return InlineKeyboardMarkup(rows)


def confirm_booking() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=CB_CONFIRM),
                InlineKeyboardButton("✖ Cancel", callback_data=CB_CANCEL),
            ]
        ]
    )


def offer_human() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🙋 Talk to a human", callback_data=CB_HUMAN)]]
    )
