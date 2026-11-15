"""Small builders for policy tests. Defaults follow the demo data in CLAUDE.md §4.4/§16."""

from datetime import UTC, date, datetime, time, timedelta

from app.schemas.campaign import Campaign, CampaignOffer, OfferRedemption
from app.schemas.customer import BillingRecord, CommunicationRecord, ContactPreferences, Payment
from app.schemas.enums import AccountStatus, BillState, MessageCategory, Segment
from app.schemas.policy import OfferCustomerContext

AS_OF = date(2026, 11, 15)


def days_ago(n: int) -> date:
    return AS_OF - timedelta(days=n)


def at(d: date) -> datetime:
    return datetime.combine(d, time(9, 0), tzinfo=UTC)


def bill(**kw) -> BillingRecord:
    data = dict(
        bill_id="B-C0005-2026-10",
        billing_period="2026-10",
        issue_date=date(2026, 10, 27),
        due_date=date(2026, 11, 10),
        amount_due_minor=59900,
        status="UNPAID",
    )
    data.update(kw)
    return BillingRecord(**data)


def overdue_bill(days: int, **kw) -> BillingRecord:
    return bill(due_date=days_ago(days), issue_date=days_ago(days + 14), **kw)


def payment(
    amount: int, *, bill_id: str = "B-C0005-2026-10", paid: date | None = None, pid: str = "P-1"
) -> Payment:
    return Payment(
        payment_id=pid, bill_id=bill_id, paid_date=paid or days_ago(1), amount_paid_minor=amount
    )


_comm_seq = iter(range(1, 10_000))


def comm(
    n_days_ago: int,
    *,
    objective: str = "BILLING_REMINDER",
    category: MessageCategory = MessageCategory.SERVICE,
    stage: int | None = None,
    bill_id: str | None = "B-C0005-2026-10",
    offer_id: str | None = None,
) -> CommunicationRecord:
    return CommunicationRecord(
        comm_id=f"CM-{next(_comm_seq)}",
        channel="EMAIL",
        source="HISTORICAL_SEED",
        sent_at=at(days_ago(n_days_ago)),
        category=category,
        objective=objective,
        reminder_stage=stage,
        related_bill_id=bill_id,
        offer_id=offer_id,
    )


def marketing(
    n_days_ago: int, objective: str = "APPRECIATION", offer_id: str | None = None
) -> CommunicationRecord:
    return comm(
        n_days_ago,
        objective=objective,
        category=MessageCategory.MARKETING,
        bill_id=None,
        offer_id=offer_id,
    )


def prefs(**kw) -> ContactPreferences:
    data = dict(
        email_service_consent=True,
        email_marketing_consent=True,
        email_opt_out=False,
        preferred_channel="EMAIL",
        consent_updated_at=at(days_ago(60)),
    )
    data.update(kw)
    return ContactPreferences(**data)


def campaign(**kw) -> Campaign:
    data = dict(
        campaign_id="CMP-LOY-Q4",
        name="Loyalty Q4",
        status="ACTIVE",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 12, 31),
    )
    data.update(kw)
    return Campaign(**data)


def offer(**kw) -> CampaignOffer:
    data = dict(
        offer_id="OFF-LOY-200",
        campaign_id="CMP-LOY-Q4",
        offer_type="LOYALTY_REWARD",
        title="Loyalty credit",
        value_type="FLAT_CREDIT_MINOR",
        value=20000,
        terms_summary="One-time ₹200 bill credit, applied on next bill.",
        valid_from=date(2026, 11, 1),
        valid_to=date(2026, 12, 31),
        channel="EMAIL",
        eligible_segments=[Segment.LOYALTY_CANDIDATE],
        min_tenure_months=12,
        requires_no_overdue=True,
        max_per_customer=1,
        total_cap=500,
        total_redeemed=37,
    )
    data.update(kw)
    return CampaignOffer(**data)


def redemption(offer_id: str = "OFF-LOY-200", customer_id: str = "C0002") -> OfferRedemption:
    return OfferRedemption(
        redemption_id="R-1",
        offer_id=offer_id,
        customer_id=customer_id,
        redeemed_at=at(days_ago(100)),
    )


def loyal_customer(**kw) -> OfferCustomerContext:
    data = dict(
        customer_id="C0002",
        segments=frozenset({Segment.CONSISTENT, Segment.LOYALTY_CANDIDATE}),
        tenure_months=31,
        active_plan_ids=frozenset({"PL-POST-499"}),
        account_status=AccountStatus.ACTIVE,
        bill_state=BillState.PAID,
    )
    data.update(kw)
    return OfferCustomerContext(**data)
