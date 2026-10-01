"""Access to business_info.json plus helpers to render it as text."""

import json
from functools import lru_cache
from html import escape
from typing import Any

from .config import BUSINESS_INFO_PATH


@lru_cache(maxsize=1)
def load_business_info() -> dict[str, Any]:
    with BUSINESS_INFO_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def get_service(service_id: str) -> dict[str, Any] | None:
    return next((s for s in load_business_info()["services"] if s["id"] == service_id), None)


def format_price(amount: float) -> str:
    currency = load_business_info().get("currency", "EUR")
    value = f"{amount:.2f}".rstrip("0").rstrip(".")
    return f"{value} {currency}"


def services_html() -> str:
    info = load_business_info()
    lines = [f"<b>💈 {escape(info['name'])} - Services & Prices</b>", ""]
    for s in info["services"]:
        lines.append(
            f"<b>{escape(s['name'])}</b> - {format_price(s['price'])} ({s['duration_min']} min)\n"
            f"<i>{escape(s['description'])}</i>"
        )
        lines.append("")
    lines.append("<b>🕒 Opening hours</b>")
    lines.extend(f"{day}: {hours}" for day, hours in info["hours"].items())
    lines.append("")
    lines.append(f"📍 {escape(info['address'])}")
    return "\n".join(lines)
