"""MockEmailService: writes outbox/*.eml + json. No network.

Owner: M4. Implements the "mock email service" half of FR-10. This module must never open a
network connection (no smtplib, no HTTP).
"""

from __future__ import annotations

import json
from email.message import EmailMessage
from pathlib import Path

from app.core.clock import utcnow_iso

#: Reserved non-routable domain (ASM A-07): guarantees no real person can be contacted.
ALLOWED_RECIPIENT_DOMAIN = "@example.test"
SENDER = "customer-care@example.test"


class MockDeliveryError(Exception):
    """Raised when a mock send is refused (e.g. non-synthetic recipient)."""


class MockEmailService:
    def __init__(self, outbox_dir: Path) -> None:
        self._outbox = Path(outbox_dir)

    def send(
        self, *, draft_id: str, recipient: str, subject: str, body: str, metadata: dict
    ) -> str:
        """Write `<draft_id>.eml` and `<draft_id>.json` to the outbox; return the .eml path."""
        if not recipient.lower().endswith(ALLOWED_RECIPIENT_DOMAIN):
            raise MockDeliveryError("Recipient is not on the reserved synthetic domain.")
        self._outbox.mkdir(parents=True, exist_ok=True)

        message = EmailMessage()
        message["From"] = SENDER
        message["To"] = recipient
        message["Subject"] = subject
        message["X-Draft-ID"] = draft_id
        message["X-Mock-Delivery"] = "true"
        message.set_content(body)

        eml_path = self._outbox / f"{draft_id}.eml"
        eml_path.write_bytes(bytes(message))
        record = {
            "draft_id": draft_id,
            "to": recipient,
            "subject": subject,
            "body": body,
            "written_at": utcnow_iso(),
            "mock": True,
            **metadata,
        }
        (self._outbox / f"{draft_id}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return eml_path.as_posix()
