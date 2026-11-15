"""ORM row -> Pydantic schema converters (internal to the repositories package)."""

from datetime import date, datetime

from app.data import models as m
from app.schemas.customer import (
    ActivityMonth,
    BillingRecord,
    CommunicationRecord,
    ContactPreferences,
    Payment,
)


def d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def bill(row: m.BillingRecordRow) -> BillingRecord:
    return BillingRecord(
        bill_id=row.bill_id,
        billing_period=row.billing_period,
        issue_date=d(row.issue_date),
        due_date=d(row.due_date),
        amount_due_minor=row.amount_due_minor,
        currency=row.currency,
        status=row.status,
        dispute_status=row.dispute_status,
    )


def payment(row: m.PaymentRow) -> Payment:
    return Payment(
        payment_id=row.payment_id,
        bill_id=row.bill_id,
        paid_date=d(row.paid_date),
        amount_paid_minor=row.amount_paid_minor,
    )


def activity(row: m.CustomerActivityMonthly) -> ActivityMonth:
    return ActivityMonth(
        month=row.month,
        active_days=row.active_days,
        usage_events=row.usage_events,
        last_activity_date=d(row.last_activity_date),
    )


def comm(row: m.CommunicationHistoryRow) -> CommunicationRecord:
    return CommunicationRecord(
        comm_id=row.comm_id,
        sent_at=ts(row.sent_at),
        channel=row.channel,
        category=row.category,
        objective=row.objective,
        reminder_stage=row.reminder_stage,
        related_bill_id=row.related_bill_id,
        offer_id=row.offer_id,
        draft_id=row.draft_id,
        source=row.source,
    )


def prefs(row: m.CustomerContactPreferences) -> ContactPreferences:
    return ContactPreferences(
        email_service_consent=bool(row.email_service_consent),
        email_marketing_consent=bool(row.email_marketing_consent),
        email_opt_out=bool(row.email_opt_out),
        preferred_channel=row.preferred_channel,
        do_not_contact_until=d(row.do_not_contact_until),
        consent_updated_at=ts(row.consent_updated_at),
    )
