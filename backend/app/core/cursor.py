import base64
import json
from datetime import datetime
from uuid import UUID


def encode_cursor(timestamp: datetime, item_id: UUID) -> str:
    payload = json.dumps(
        {"timestamp": timestamp.isoformat(), "id": str(item_id)}, separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    padded = cursor + "=" * (-len(cursor) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
    return datetime.fromisoformat(payload["timestamp"]), UUID(payload["id"])
