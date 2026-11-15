"""ContactPolicyGate (FR-07 pre-gen): consent, preferences, frequency, duplicates.

Owner: M2. Deterministic, no LLM import (CLAUDE.md §6.5).

If the gate refuses, no LLM call is made. M4's DeliveryGate calls the same function
again at send time (D5), so consent withdrawn after drafting still blocks delivery.
All reasons are collected (no short-circuit) so the reviewer sees the full picture.
"""

from collections.abc import Iterable
from datetime import date

from app.policy.config import ContactConfig
from app.policy.history import days_since, history_as_of, objective_group
from app.schemas.customer import CommunicationRecord, ContactPreferences
from app.schemas.enums import AccountStatus, MessageCategory
from app.schemas.policy import ContactDecision

CONTACT_PREFERENCES_MISSING = "CONTACT_PREFERENCES_MISSING"
CONTACT_EMAIL_OPT_OUT = "CONTACT_EMAIL_OPT_OUT"
CONTACT_ACCOUNT_CLOSED = "CONTACT_ACCOUNT_CLOSED"
CONTACT_SUPPRESSED_UNTIL = "CONTACT_SUPPRESSED_UNTIL"
CONTACT_CHANNEL_NONE = "CONTACT_CHANNEL_NONE"
CONTACT_NO_MARKETING_CONSENT = "CONTACT_NO_MARKETING_CONSENT"
CONTACT_NO_SERVICE_CONSENT = "CONTACT_NO_SERVICE_CONSENT"
CONTACT_FREQUENCY_CAP = "CONTACT_FREQUENCY_CAP"
CONTACT_MARKETING_TOO_RECENT = "CONTACT_MARKETING_TOO_RECENT"
CONTACT_DUPLICATE_OBJECTIVE = "CONTACT_DUPLICATE_OBJECTIVE"

_MISSING_CONSENT = {
    MessageCategory.MARKETING: CONTACT_NO_MARKETING_CONSENT,
    MessageCategory.SERVICE: CONTACT_NO_SERVICE_CONSENT,
}


def check_contact(
    prefs: ContactPreferences | None,
    account_status: AccountStatus,
    history: Iterable[CommunicationRecord],
    category: MessageCategory,
    objective: str | None,
    cfg: ContactConfig,
    as_of: date,
) -> ContactDecision:
    """May we email this customer, for this category/objective, as of ``as_of``?"""
    if prefs is None:  # never guess consent
        return ContactDecision(
            allowed=False, category=category, reasons=[CONTACT_PREFERENCES_MISSING]
        )

    reasons: list[str] = []
    blockers = set(cfg.global_blockers)

    if "email_opt_out" in blockers and prefs.email_opt_out:
        reasons.append(CONTACT_EMAIL_OPT_OUT)
    if "account_closed" in blockers and account_status is AccountStatus.CLOSED:
        reasons.append(CONTACT_ACCOUNT_CLOSED)
    if (
        "do_not_contact_until_active" in blockers
        and prefs.do_not_contact_until is not None
        and as_of < prefs.do_not_contact_until
    ):
        reasons.append(CONTACT_SUPPRESSED_UNTIL)
    if "preferred_channel_none" in blockers and prefs.preferred_channel == "NONE":
        reasons.append(CONTACT_CHANNEL_NONE)

    if not all(getattr(prefs, flag) for flag in cfg.required_flags(category)):
        reasons.append(_MISSING_CONSENT[category])

    past = history_as_of(history, as_of)
    last_30 = [h for h in past if days_since(h, as_of) < 30]
    if len(last_30) >= cfg.frequency_caps.total_max_per_30_days:
        reasons.append(CONTACT_FREQUENCY_CAP)
    if category is MessageCategory.MARKETING and any(
        h.category == MessageCategory.MARKETING
        and days_since(h, as_of) < cfg.frequency_caps.marketing_min_days_between
        for h in past
    ):
        reasons.append(CONTACT_MARKETING_TOO_RECENT)
    if objective is not None:
        group = objective_group(objective)
        if any(
            objective_group(h.objective) == group
            and days_since(h, as_of) < cfg.duplicate_window_days.same_objective
            for h in past
        ):
            reasons.append(CONTACT_DUPLICATE_OBJECTIVE)

    return ContactDecision(allowed=not reasons, category=category, reasons=reasons)
