"""Content hash that approvals are bound to (decision D6).

Owner: M4.
"""

from __future__ import annotations

import hashlib


def compute_content_hash(subject: str, body: str) -> str:
    """SHA-256 over subject and body; any change to either invalidates an approval."""
    digest = hashlib.sha256(f"{subject}\n\x1e\n{body}".encode()).hexdigest()
    return f"sha256:{digest}"
