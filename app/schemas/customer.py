"""CustomerProfile, CustomerFeatures.

Owner: SHARED (produced by M1). Drafted by M4 for CP0 from blueprint sections 4.4-4.6;
needs approval. Deliberately contains no protected characteristics or proxies (section 4.8).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import BillState, MessageCategory

CUSTOMER_ID_PATTERN = r"^C\d{4}$"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ContactPreferences(_Frozen):
    email_service_consent: bool
    email_marketing_consent: bool
    email_opt_out: bool
    preferred_channel: str | None = None
    do_not_contact_until: date | None = None


class CustomerPlan(_Frozen):
    plan_id: str
    plan_name: str
    plan_category: str
    start_date: date
    end_date: date | None = None
    status: str


class ActivityMonth(_Frozen):
    month: str  # YYYY-MM
    active_days: int = Field(ge=0, le=31)
    usage_events: int = Field(ge=0)
    last_activity_date: date | None = None


class BillingRecord(_Frozen):
    bill_id: str
    billing_period: str  # YYYY-MM
    issue_date: date
    due_date: date | None
    amount_due_minor: int = Field(gt=0)
    currency: str = "INR"
    status: str
    dispute_status: str = "NONE"


class Payment(_Frozen):
    payment_id: str
    bill_id: str
    paid_date: date
    amount_paid_minor: int = Field(gt=0)


class CommRecord(_Frozen):
    comm_id: str
    sent_at: datetime
    channel: str
    category: MessageCategory
    objective: str
    reminder_stage: int | None = None
    related_bill_id: str | None = None
    offer_id: str | None = None
    draft_id: str | None = None
    source: str


class CustomerProfile(_Frozen):
    """Permitted raw data for one customer as of a date (FR-01).

    `first_name` is for salutation only and `email` only for mock delivery; neither is a
    decision feature and `email` is never passed to the LLM.
    """

    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)
    as_of_date: date
    first_name: str
    email: str
    customer_since: date
    account_status: str
    preferences: ContactPreferences
    plans: list[CustomerPlan] = []
    activity: list[ActivityMonth] = []
    bills: list[BillingRecord] = []
    payments: list[Payment] = []
    communications: list[CommRecord] = []


class CustomerFeatures(_Frozen):
    """Engineered features (section 4.6). Computed only from data dated <= as_of_date."""

    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)
    as_of_date: date
    tenure_months: int
    active_plan_count: int
    active_plan_ids: list[str] = []
    months_observed: int
    active_months_last_6: int
    recent_activity_avg: float
    prior_activity_avg: float
    activity_trend_ratio: float | None = None
    activity_cv_6m: float | None = None
    days_since_last_activity: int | None = None
    bills_last_12m: int
    on_time_payment_rate_12m: float | None = None
    late_payments_last_6m: int
    current_bill_state: BillState
    days_overdue: int | None = None
    outstanding_minor: int | None = None
    missing_features: list[str] = []
