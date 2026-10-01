"""Gemini-powered answers, grounded strictly in business_info.json."""

import json
import logging
from dataclasses import dataclass

from google import genai
from google.genai import errors, types

from .business import load_business_info

logger = logging.getLogger(__name__)

# The model replies with exactly this token when the answer is not in the
# business info, so the bot can offer a human instead of guessing.
HANDOFF_TOKEN = "[[HANDOFF]]"

# Transient errors (rate limits, overload) are retried with backoff by the SDK.
RETRY_OPTIONS = types.HttpRetryOptions(
    attempts=3, initial_delay=1.0, max_delay=8.0, http_status_codes=[429, 500, 502, 503, 504]
)
REQUEST_TIMEOUT_MS = 30_000

SYSTEM_PROMPT_TEMPLATE = """You are the friendly customer support assistant for {name}, a barbershop.

Answer ONLY using the business information below. It is your single source of truth.

Rules:
- Never invent or guess prices, services, hours, staff names, availability, promotions or policies.
- If the answer is not clearly covered by the business information, or the customer needs something
  only a person can do (complaints, refunds, checking a specific slot, changing an existing booking),
  reply with exactly {token} and nothing else.
- If the customer wants to book, tell them to tap "Book appointment" or send /book.
- Reply in the same language the customer writes in.
- Keep answers short (1-4 sentences), warm and professional. Plain text only, no Markdown.

Business information (JSON):
{business_info}
"""


@dataclass
class AIReply:
    text: str
    needs_human: bool
    failed: bool = False  # True when Gemini errored, as opposed to "I don't know"


class SupportAI:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS, retry_options=RETRY_OPTIONS),
        )
        self._model = model
        info = load_business_info()
        self._config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT_TEMPLATE.format(
                name=info["name"],
                token=HANDOFF_TOKEN,
                business_info=json.dumps(info, indent=2, ensure_ascii=False),
            ),
            # No max_output_tokens: on thinking models the reasoning counts
            # against it and can leave the reply empty. Length is set by the prompt.
            temperature=0.2,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    async def verify_model(self) -> None:
        """Send one tiny request at startup so a bad key or model name fails fast.

        Transient errors (rate limit, overload) only log a warning.
        """
        try:
            await self._client.aio.models.generate_content(
                model=self._model,
                contents="Reply with OK.",
                config=types.GenerateContentConfig(
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                ),
            )
        except errors.ClientError as exc:
            if exc.code == 429:
                logger.warning("Gemini is rate-limited right now; continuing startup.")
                return
            raise RuntimeError(
                f"Gemini model '{self._model}' can't be used with this API key: {exc.message} "
                "Check GEMINI_API_KEY and GEMINI_MODEL in .env."
            ) from exc
        except Exception:
            logger.warning("Could not reach Gemini at startup; continuing.", exc_info=True)

    async def answer(self, question: str, history: list[dict[str, str]] | None = None) -> AIReply:
        """Answer a customer question. `history` is a list of {"role", "text"} turns."""
        contents = [
            types.Content(role=turn["role"], parts=[types.Part(text=turn["text"])])
            for turn in (history or [])
        ]
        contents.append(types.Content(role="user", parts=[types.Part(text=question)]))

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model, contents=contents, config=self._config
            )
            text = (response.text or "").strip()
        except Exception:
            logger.exception("Gemini request failed")
            return AIReply(text="", needs_human=True, failed=True)

        if not text or HANDOFF_TOKEN in text:
            return AIReply(text="", needs_human=True)
        return AIReply(text=text, needs_human=False)
