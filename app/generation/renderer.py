"""SlotRenderer: replace {{slots}} with verified values, append disclaimers (§8.3, §8.5).

Owner: M3.

- Only values from ``LLMInput`` are ever substituted (allowed_slots + the eligible offer).
- An unknown slot is NOT silently dropped: the token stays in the text and is listed in
  ``RenderedDraft.unknown_slots`` -> the UNKNOWN_SLOT guardrail BLOCKs the draft.
- Disclaimer text comes verbatim from disclaimers.yaml for the keys the *strategy*
  requires (``LLMInput.required_disclaimers``) — not the keys the LLM claims to cover.
"""

from __future__ import annotations

import hashlib

from app.generation.clients.template_only import verified_slot_values
from app.generation.content import SLOT_RE, DisclaimerStore
from app.schemas.generation import LLMInput, RawDraft, RenderedDraft

#: Separates the message body from the appended disclaimer block.
DISCLAIMER_SEPARATOR = "\n\n--\n"


def compute_content_hash(subject: str, body: str) -> str:
    """Hash the reviewer approves (D6). M4's ReviewService/DeliveryGate must use this."""
    digest = hashlib.sha256(f"{subject}\n{body}".encode()).hexdigest()
    return f"sha256:{digest}"


def split_disclaimers(body: str) -> tuple[str, str]:
    """(main text, disclaimer block). Block is "" if the separator was removed."""
    if DISCLAIMER_SEPARATOR in body:
        main, block = body.split(DISCLAIMER_SEPARATOR, 1)
        return main, block
    return body, ""


class SlotRenderer:
    def __init__(self, disclaimers: DisclaimerStore) -> None:
        self._disclaimers = disclaimers

    def render(self, raw: RawDraft, llm_input: LLMInput) -> RenderedDraft:
        values = verified_slot_values(llm_input)
        used: dict[str, str] = {}
        unknown: list[str] = []

        def fill(text: str) -> str:
            def _sub(m) -> str:
                name = m.group(1)
                if name in values:
                    used[name] = values[name]
                    return values[name]
                if name not in unknown:
                    unknown.append(name)
                return m.group(0)

            return SLOT_RE.sub(_sub, text)

        subject = " ".join(fill(raw.subject).split())  # subjects are single-line
        body = fill(raw.body).strip()

        keys = [k for k in llm_input.required_disclaimers]
        if keys:
            block = "\n".join(fill(self._disclaimers.text(k)) for k in keys)
            body = f"{body}{DISCLAIMER_SEPARATOR}{block}"

        return RenderedDraft(
            subject=subject,
            body=body,
            raw=raw,
            facts_used=used,
            unknown_slots=unknown,
            disclaimer_keys_appended=keys,
            content_hash=compute_content_hash(subject, body),
        )


def apply_edit(draft: RenderedDraft, subject: str, body: str) -> RenderedDraft:
    """Reviewer edit (FR-08): new text + new hash; must be re-validated by the caller.

    Edited text is plain text. Any ``{{slot}}`` a reviewer types is NOT filled and will
    be flagged by UNKNOWN_SLOT (reviewers must write final values, which are then
    checked against verified facts like any other text).
    """
    subject = " ".join(subject.split())
    body = body.strip()
    leftover = sorted(set(SLOT_RE.findall(subject)) | set(SLOT_RE.findall(body)))
    return draft.model_copy(
        update={
            "subject": subject,
            "body": body,
            "unknown_slots": leftover,
            "content_hash": compute_content_hash(subject, body),
            "edited": True,
        }
    )
