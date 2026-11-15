"""Cleaning and data-quality flags. Never imputes: missing data stays missing.

Owner: M1.
"""

import logging
from datetime import date

from app.schemas.customer import ActivityMonth, CustomerProfile

log = logging.getLogger(__name__)


def clean_activity(rows: list[ActivityMonth], as_of: date) -> tuple[list[ActivityMonth], list[str]]:
    """Drop months after as_of, clip negative counts to 0, de-duplicate months.

    Returns (clean rows sorted by month, data-quality flags).
    """
    flags: list[str] = []
    by_month: dict[str, ActivityMonth] = {}
    as_of_month = as_of.strftime("%Y-%m")
    for r in rows:
        if r.month > as_of_month:
            continue
        if r.month in by_month:
            flags.append(f"DUPLICATE_ACTIVITY_MONTH:{r.month}")
            continue
        usage, days = r.usage_events, r.active_days
        if usage < 0 or days < 0:
            flags.append(f"NEGATIVE_ACTIVITY_CLIPPED:{r.month}")
            log.warning("negative activity clipped", extra={"month": r.month})
            usage, days = max(usage, 0), max(days, 0)
        last = (
            r.last_activity_date if r.last_activity_date and r.last_activity_date <= as_of else None
        )
        by_month[r.month] = ActivityMonth(
            month=r.month, active_days=days, usage_events=usage, last_activity_date=last
        )
    return [by_month[k] for k in sorted(by_month)], flags


def restrict_to_as_of(profile: CustomerProfile) -> CustomerProfile:
    """Second leakage guard: remove anything dated after profile.as_of_date."""
    as_of = profile.as_of_date
    bills = [b for b in profile.bills if b.issue_date <= as_of]
    bill_ids = {b.bill_id for b in bills}
    return profile.model_copy(
        update={
            "bills": bills,
            "payments": [
                p for p in profile.payments if p.paid_date <= as_of and p.bill_id in bill_ids
            ],
            "communications": [c for c in profile.communications if c.sent_at.date() <= as_of],
            "plans": [p for p in profile.plans if p.start_date <= as_of],
        }
    )
