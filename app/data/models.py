"""SQLAlchemy ORM tables T1-T18.

Owner: M1. Changes must be announced to the team (shared DB schema).
Conventions: dates as ISO TEXT (YYYY-MM-DD), timestamps as ISO-8601 UTC TEXT,
money as INTEGER minor units. These ORM models are never returned by the API —
Pydantic schemas in app/schemas/ are the contracts.
"""

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# T1
class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("email LIKE '%@example.test'", name="ck_email_synthetic_domain"),
        CheckConstraint("account_status IN ('ACTIVE','SUSPENDED','CLOSED')", name="ck_acct"),
        CheckConstraint("is_synthetic = 1", name="ck_is_synthetic"),
    )
    customer_id: Mapped[str] = mapped_column(Text, primary_key=True)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    customer_since: Mapped[str] = mapped_column(Text, nullable=False)
    account_status: Mapped[str] = mapped_column(Text, nullable=False)
    is_synthetic: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


# T2
class CustomerContactPreferences(Base):
    __tablename__ = "customer_contact_preferences"
    __table_args__ = (
        CheckConstraint("email_service_consent IN (0,1)", name="ck_svc"),
        CheckConstraint("email_marketing_consent IN (0,1)", name="ck_mkt"),
        CheckConstraint("email_opt_out IN (0,1)", name="ck_optout"),
        CheckConstraint("preferred_channel IN ('EMAIL','SMS','NONE')", name="ck_channel"),
    )
    customer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("customers.customer_id"), primary_key=True
    )
    email_service_consent: Mapped[int] = mapped_column(Integer, nullable=False)
    email_marketing_consent: Mapped[int] = mapped_column(Integer, nullable=False)
    email_opt_out: Mapped[int] = mapped_column(Integer, nullable=False)
    preferred_channel: Mapped[str | None] = mapped_column(Text)
    do_not_contact_until: Mapped[str | None] = mapped_column(Text)
    consent_updated_at: Mapped[str] = mapped_column(Text, nullable=False)


# T3
class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint(
            "plan_category IN ('PREPAID','POSTPAID','BROADBAND','RETAIL_MEMBERSHIP')",
            name="ck_plan_cat",
        ),
        CheckConstraint("monthly_price_minor >= 0", name="ck_price"),
    )
    plan_id: Mapped[str] = mapped_column(Text, primary_key=True)
    plan_name: Mapped[str] = mapped_column(Text, nullable=False)
    plan_category: Mapped[str] = mapped_column(Text, nullable=False)
    monthly_price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# T4
class CustomerPlan(Base):
    __tablename__ = "customer_plans"
    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_cp_dates"),
        CheckConstraint("status IN ('ACTIVE','ENDED','SUSPENDED')", name="ck_cp_status"),
    )
    customer_plan_id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(Text, ForeignKey("plans.plan_id"), nullable=False)
    start_date: Mapped[str] = mapped_column(Text, nullable=False)
    end_date: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)


# T5
class CustomerActivityMonthly(Base):
    __tablename__ = "customer_activity_monthly"
    __table_args__ = (
        CheckConstraint("active_days BETWEEN 0 AND 31", name="ck_active_days"),
        CheckConstraint("usage_events >= 0", name="ck_usage"),
    )
    customer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("customers.customer_id"), primary_key=True
    )
    month: Mapped[str] = mapped_column(Text, primary_key=True)
    active_days: Mapped[int] = mapped_column(Integer, nullable=False)
    usage_events: Mapped[int] = mapped_column(Integer, nullable=False)
    last_activity_date: Mapped[str | None] = mapped_column(Text)


# T6
class BillingRecordRow(Base):
    __tablename__ = "billing_records"
    __table_args__ = (
        UniqueConstraint("customer_id", "billing_period", name="uq_bill_period"),
        CheckConstraint("due_date IS NULL OR due_date >= issue_date", name="ck_bill_dates"),
        CheckConstraint("amount_due_minor > 0", name="ck_amount"),
        CheckConstraint(
            "status IN ('PAID','UNPAID','PARTIALLY_PAID','WAIVED')", name="ck_bill_status"
        ),
        CheckConstraint("dispute_status IN ('NONE','OPEN','RESOLVED')", name="ck_dispute"),
    )
    bill_id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    billing_period: Mapped[str] = mapped_column(Text, nullable=False)
    issue_date: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[str | None] = mapped_column(Text)
    amount_due_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="INR")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    dispute_status: Mapped[str] = mapped_column(Text, nullable=False, default="NONE")


# T7
class PaymentRow(Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount_paid_minor > 0", name="ck_paid"),)
    payment_id: Mapped[str] = mapped_column(Text, primary_key=True)
    bill_id: Mapped[str] = mapped_column(
        Text, ForeignKey("billing_records.bill_id"), nullable=False, index=True
    )
    paid_date: Mapped[str] = mapped_column(Text, nullable=False)
    amount_paid_minor: Mapped[int] = mapped_column(Integer, nullable=False)


# T9
class CampaignRow(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','APPROVED','ACTIVE','PAUSED','ENDED')", name="ck_cmp_status"
        ),
        CheckConstraint("end_date >= start_date", name="ck_cmp_dates"),
    )
    campaign_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[str] = mapped_column(Text, nullable=False)
    end_date: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(Text)


# T10
class CampaignOfferRow(Base):
    __tablename__ = "campaign_offers"
    __table_args__ = (
        CheckConstraint("offer_id LIKE 'OFF-%'", name="ck_offer_id"),
        CheckConstraint(
            "offer_type IN ('LOYALTY_REWARD','REENGAGEMENT','APPRECIATION_PERK')",
            name="ck_offer_type",
        ),
        CheckConstraint(
            "value_type IN ('PERCENT_DISCOUNT','FLAT_CREDIT_MINOR','BONUS_DATA_GB','POINTS')",
            name="ck_value_type",
        ),
        CheckConstraint("value > 0", name="ck_value"),
        CheckConstraint("channel IN ('EMAIL','SMS','ANY')", name="ck_offer_channel"),
        CheckConstraint("total_cap IS NULL OR total_redeemed <= total_cap", name="ck_offer_cap"),
    )
    offer_id: Mapped[str] = mapped_column(Text, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        Text, ForeignKey("campaigns.campaign_id"), nullable=False
    )
    offer_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    terms_summary: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[str] = mapped_column(Text, nullable=False)
    valid_to: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    eligible_segments: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    min_tenure_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requires_no_overdue: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_per_customer: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_cap: Mapped[int | None] = mapped_column(Integer)
    total_redeemed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# T11
class OfferPlanEligibility(Base):
    __tablename__ = "offer_plan_eligibility"
    offer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("campaign_offers.offer_id"), primary_key=True
    )
    plan_id: Mapped[str] = mapped_column(Text, ForeignKey("plans.plan_id"), primary_key=True)


# T12
class OfferRedemptionRow(Base):
    __tablename__ = "offer_redemptions"
    redemption_id: Mapped[str] = mapped_column(Text, primary_key=True)
    offer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("campaign_offers.offer_id"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    redeemed_at: Mapped[str] = mapped_column(Text, nullable=False)


# T13
class ClassificationResultRow(Base):
    __tablename__ = "classification_results"
    __table_args__ = (CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_conf"),)
    classification_id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    as_of_date: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    primary_segment: Mapped[str] = mapped_column(Text, nullable=False)
    reason_codes: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    features_snapshot: Mapped[str] = mapped_column(Text, nullable=False)  # JSON, no PII
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    shadow_model_label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


# T14
class DraftRow(Base):
    __tablename__ = "drafts"
    __table_args__ = (
        CheckConstraint(
            "validation_status IN ('PASS','WARN','BLOCK','ESCALATE')", name="ck_draft_val"
        ),
    )
    draft_id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    classification_id: Mapped[str] = mapped_column(
        Text, ForeignKey("classification_results.classification_id"), nullable=False
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[str] = mapped_column(Text, nullable=False)
    template_version: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    model_provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    offer_id: Mapped[str | None] = mapped_column(Text, ForeignKey("campaign_offers.offer_id"))
    bill_id: Mapped[str | None] = mapped_column(Text, ForeignKey("billing_records.bill_id"))
    reminder_stage: Mapped[int | None] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    facts_used: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    validation_status: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)  # state machine owned by M4
    policy_decisions: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    llm_latency_ms: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


# T8 (after drafts because of the draft_id FK)
class CommunicationHistoryRow(Base):
    __tablename__ = "communication_history"
    __table_args__ = (
        CheckConstraint("category IN ('SERVICE','MARKETING')", name="ck_comm_cat"),
        CheckConstraint(
            "reminder_stage IS NULL OR reminder_stage BETWEEN 1 AND 3", name="ck_comm_stage"
        ),
        CheckConstraint("source IN ('HISTORICAL_SEED','MOCK_DELIVERY')", name="ck_comm_src"),
    )
    comm_id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    sent_at: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    reminder_stage: Mapped[int | None] = mapped_column(Integer)
    related_bill_id: Mapped[str | None] = mapped_column(Text, ForeignKey("billing_records.bill_id"))
    offer_id: Mapped[str | None] = mapped_column(Text, ForeignKey("campaign_offers.offer_id"))
    draft_id: Mapped[str | None] = mapped_column(Text, ForeignKey("drafts.draft_id"))
    source: Mapped[str] = mapped_column(Text, nullable=False)


# T15
class ValidationFindingRow(Base):
    __tablename__ = "validation_findings"
    __table_args__ = (
        CheckConstraint("severity IN ('PASS','WARN','BLOCK','ESCALATE')", name="ck_sev"),
    )
    finding_id: Mapped[str] = mapped_column(Text, primary_key=True)
    draft_id: Mapped[str] = mapped_column(
        Text, ForeignKey("drafts.draft_id"), nullable=False, index=True
    )
    validation_run: Mapped[int] = mapped_column(Integer, nullable=False)
    check_id: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    mandatory: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    span: Mapped[str | None] = mapped_column(Text)


# T16
class ReviewerActionRow(Base):
    __tablename__ = "reviewer_actions"
    __table_args__ = (
        CheckConstraint("action IN ('EDIT','APPROVE','REJECT','ESCALATE')", name="ck_action"),
        CheckConstraint(
            "rejection_reason IS NULL OR rejection_reason IN "
            "('FACTUAL_ERROR','WRONG_TONE','WRONG_STRATEGY','POLICY','OTHER')",
            name="ck_reject_reason",
        ),
    )
    action_id: Mapped[str] = mapped_column(Text, primary_key=True)
    draft_id: Mapped[str] = mapped_column(
        Text, ForeignKey("drafts.draft_id"), nullable=False, index=True
    )
    reviewer_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    rubric: Mapped[str | None] = mapped_column(Text)  # JSON
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


# T17
class DeliveryRow(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('MOCK_SENT','BLOCKED','FAILED')", name="ck_delivery"),
    )
    delivery_id: Mapped[str] = mapped_column(Text, primary_key=True)
    draft_id: Mapped[str] = mapped_column(
        Text, ForeignKey("drafts.draft_id"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    block_reason: Mapped[str | None] = mapped_column(Text)
    outbox_path: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[str] = mapped_column(Text, nullable=False)


# T18 (append-only; enforced by the repository — no update/delete methods)
class AuditEventRow(Base):
    __tablename__ = "audit_events"
    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    ts: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    customer_ref: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    draft_id: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON, no PII
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
