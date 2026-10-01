"""Loads settings from the environment (.env) and exposes project paths."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

BUSINESS_INFO_PATH = DATA_DIR / "business_info.json"
BOOKINGS_PATH = DATA_DIR / "bookings.json"
HANDOFFS_PATH = DATA_DIR / "handoffs.json"

load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    gemini_api_key: str
    gemini_model: str
    admin_chat_id: int | None


def load_settings() -> Settings:
    telegram_token = os.getenv("TELEGRAM_TOKEN", "").strip()
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()

    missing = [
        name
        for name, value in (("TELEGRAM_TOKEN", telegram_token), ("GEMINI_API_KEY", gemini_api_key))
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in."
        )

    admin_chat_id = os.getenv("ADMIN_CHAT_ID", "").strip()

    return Settings(
        telegram_token=telegram_token,
        gemini_api_key=gemini_api_key,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip(),
        admin_chat_id=int(admin_chat_id) if admin_chat_id else None,
    )
