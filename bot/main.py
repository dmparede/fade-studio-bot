"""Entry point: `python -m bot.main`."""

import logging
import warnings

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.warnings import PTBUserWarning

from . import keyboards
from .ai import SupportAI
from .config import BOOKINGS_PATH, HANDOFFS_PATH, load_settings
from .handlers import general
from .handlers.booking import build_booking_handler
from .storage import JsonListStore

# The booking flow mixes buttons and text replies on purpose; PTB warns about
# per-message tracking for that setup, which doesn't apply here.
warnings.filterwarnings("ignore", message=r".*per_message.*", category=PTBUserWarning)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand("start", "Main menu"),
    BotCommand("services", "Services, prices and opening hours"),
    BotCommand("book", "Request an appointment"),
    BotCommand("human", "Talk to a member of the team"),
    BotCommand("cancel", "Cancel the current booking"),
    BotCommand("help", "What I can do"),
]


async def post_init(app: Application) -> None:
    await app.bot_data["ai"].verify_model()
    await app.bot.set_my_commands(COMMANDS)


def build_application() -> Application:
    settings = load_settings()

    app = Application.builder().token(settings.telegram_token).post_init(post_init).build()
    app.bot_data.update(
        settings=settings,
        ai=SupportAI(settings.gemini_api_key, settings.gemini_model),
        bookings=JsonListStore(BOOKINGS_PATH),
        handoffs=JsonListStore(HANDOFFS_PATH),
    )

    # The booking conversation goes first so it captures replies mid-flow.
    app.add_handler(build_booking_handler())

    app.add_handler(CommandHandler("start", general.start))
    app.add_handler(CommandHandler("help", general.help_command))
    app.add_handler(CommandHandler("services", general.show_services))
    app.add_handler(CommandHandler("human", general.talk_to_human))
    app.add_handler(CallbackQueryHandler(general.show_services, pattern=f"^{keyboards.CB_SERVICES}$"))
    app.add_handler(CallbackQueryHandler(general.talk_to_human, pattern=f"^{keyboards.CB_HUMAN}$"))
    app.add_handler(CallbackQueryHandler(general.stale_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, general.ai_answer))

    app.add_error_handler(general.error_handler)
    return app


def main() -> None:
    app = build_application()
    logger.info("Fade Studio bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
