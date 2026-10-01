"""Small JSON-file stores for bookings and human-handoff requests.

Writes are serialized with an asyncio lock and done atomically (temp file +
rename), so a crash mid-write never leaves a corrupted file behind.
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonListStore:
    """Append-only list of records persisted to a JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    def _read(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            with self._path.open(encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def _write(self, records: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self._path)

    async def append(self, record: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex[:8].upper(),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **record,
        }
        async with self._lock:
            records = self._read()
            records.append(record)
            self._write(records)
        return record
