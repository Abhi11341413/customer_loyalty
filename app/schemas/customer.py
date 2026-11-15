"""Customer data contracts: raw profile (input layer) and engineered features.

Owner: SHARED (produced by M1). Changes need approval from all affected owners.
Money is always integer minor units (paise). Dates are `datetime.date`.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import AccountStatus, BillConflictType, BillState

CUSTOMER_ID_PATTERN = r"^C\d{4}$"


class PlanSubscription(BaseModel):
    customer_plan_id: str
    plan_id: str
    plan_name: str
    plan_category: str
    start_date: date
    end_date: date | None = None
    status: str


class ActivityMonth(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    active_days: int
    usage_events: int
    last_activity_date: date | None = None


class Payment(BaseModel):
    payment_id: str
    bill_id: str
    paid_date: date
    amount_paid_minor: int


class BillingRecord(BaseModel):
    bill_id: str
    billing_period: str
    issue_date: date
    due_date: date | None = None
    amount_due_minor: int
    currency: str = "INR"
    status: str
    dispute_status: str = "NONE"


class CommunicationRecord(BaseModel):
    """Metadata only — never message bodies."""

    comm_id: str
    sent_at: datetime
    channel: str
    category: str
    objective: str
    reminder_stage: int | None = None
    related_bill_id: str | None = None
    offer_id: str | None = None
    draft_id: str | None = None
    source: str


class ContactPreferences(BaseModel):
    email_service_consent: bool
    email_marketing_consent: bool
    email_opt_out: bool
    preferred_channel: str | None = None
    do_not_contact_until: date | None = None
    consent_updated_at: datetime


class CustomerProfile(BaseModel):
    """Minimal permitted customer context as of a date (FR-01).

    `email` is here only for mock delivery. It must never reach the LLM or the audit log.
    """

    model_config = ConfigDict(frozen=True)

    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)
    as_of_date: date
    first_name: str
    email: str
    customer_since: date
    account_status: AccountStatus
    contact_preferences: ContactPreferences | None = None
    plans: list[PlanSubscription] = []
    activity: list[ActivityMonth] = []
    bills: list[BillingRecord] = []
    payments: list[Payment] = []
    communications: list[CommunicationRecord] = []


class CustomerProfileView(BaseModel):
    """API view of a profile: no email address."""

    customer_id: str
    as_of_date: date
    first_name: str
    customer_since: date
    account_status: AccountStatus
    contact_preferences: ContactPreferences | None = None
    plans: list[PlanSubscription] = []
    activity: list[ActivityMonth] = []
    bills: list[BillingRecord] = []
    payments: list[Payment] = []
    communications: list[CommunicationRecord] = []

    @classmethod
    def from_profile(cls, profile: CustomerProfile) -> "CustomerProfileView":
        return cls(**profile.model_dump(exclude={"email"}))


class CustomerFeatures(BaseModel):
    """Engineered features, computed only from data dated <= as_of_date.

    Must never contain names, emails, raw spend, location, demographic or device fields
    (enforced by tests/unit/features/test_no_protected_features.py).
    """

    model_config = ConfigDict(frozen=True)

    customer_id: str
    as_of_date: date
    account_status: AccountStatus
    tenure_months: int
    active_plan_count: int
    active_plan_ids: list[str]
    months_observed: int
    active_months_last_6: int
    recent_activity_avg: float | None
    prior_activity_avg: float | None
    activity_trend_ratio: float | None
    activity_cv_6m: float | None
    days_since_last_activity: int | None
    bills_last_12m: int
    on_time_bills_last_12m: int
    on_time_payment_rate_12m: float | None
    late_payments_last_6m: int
    current_bill_state: BillState
    current_bill_id: str | None = None
    bill_conflict_type: BillConflictType | None = None
    days_overdue: int | None = None
    outstanding_minor: int | None = None
    missing_features: list[str] = []
    data_quality_flags: list[str] = []


class CustomerSummary(BaseModel):
    customer_id: str
    first_name: str
    archetype_hint: str | None = None


class CustomerProfileResponse(BaseModel):
    profile: CustomerProfileView
    features: CustomerFeatures
