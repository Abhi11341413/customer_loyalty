"""CustomerReader: everything ProfileAssembler needs, filtered to data dated <= as_of.

Owner: M1.
"""

from datetime import date
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data import models as m
from app.data.repositories import _convert as cv
from app.schemas.customer import (
    ActivityMonth,
    BillingRecord,
    CommunicationRecord,
    ContactPreferences,
    Payment,
    PlanSubscription,
)


class CustomerRow(Protocol):
    customer_id: str
    first_name: str
    email: str
    customer_since: str
    account_status: str
    is_synthetic: int


class CustomerReader(Protocol):
    def get_customer(self, customer_id: str) -> CustomerRow | None: ...
    def list_customers(self, customer_ids: list[str] | None = None) -> list[CustomerRow]: ...
    def preferences(self, customer_id: str) -> ContactPreferences | None: ...
    def plans(self, customer_id: str, as_of: date) -> list[PlanSubscription]: ...
    def activity(self, customer_id: str, as_of: date) -> list[ActivityMonth]: ...
    def bills(self, customer_id: str, as_of: date) -> list[BillingRecord]: ...
    def payments(self, bill_ids: list[str], as_of: date) -> list[Payment]: ...
    def communications(self, customer_id: str, as_of: date) -> list[CommunicationRecord]: ...


class SqlCustomerReader:
    """SQLite implementation. All date filters are the first leakage guard."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get_customer(self, customer_id: str) -> m.Customer | None:
        return self._s.get(m.Customer, customer_id)

    def list_customers(self, customer_ids: list[str] | None = None) -> list[m.Customer]:
        stmt = select(m.Customer).order_by(m.Customer.customer_id)
        if customer_ids is not None:
            stmt = stmt.where(m.Customer.customer_id.in_(customer_ids))
        return list(self._s.scalars(stmt))

    def preferences(self, customer_id: str) -> ContactPreferences | None:
        row = self._s.get(m.CustomerContactPreferences, customer_id)
        return cv.prefs(row) if row else None

    def plans(self, customer_id: str, as_of: date) -> list[PlanSubscription]:
        stmt = (
            select(m.CustomerPlan, m.Plan)
            .join(m.Plan, m.Plan.plan_id == m.CustomerPlan.plan_id)
            .where(m.CustomerPlan.customer_id == customer_id)
            .where(m.CustomerPlan.start_date <= as_of.isoformat())
            .order_by(m.CustomerPlan.start_date)
        )
        out = []
        for cp, plan in self._s.execute(stmt):
            ended = cp.end_date is not None and cp.end_date <= as_of.isoformat()
            out.append(
                PlanSubscription(
                    customer_plan_id=cp.customer_plan_id,
                    plan_id=cp.plan_id,
                    plan_name=plan.plan_name,
                    plan_category=plan.plan_category,
                    start_date=cv.d(cp.start_date),
                    end_date=cv.d(cp.end_date) if ended else None,
                    status="ENDED" if ended and cp.status == "ACTIVE" else cp.status,
                )
            )
        return out

    def activity(self, customer_id: str, as_of: date) -> list[ActivityMonth]:
        stmt = (
            select(m.CustomerActivityMonthly)
            .where(m.CustomerActivityMonthly.customer_id == customer_id)
            .where(m.CustomerActivityMonthly.month <= as_of.strftime("%Y-%m"))
            .order_by(m.CustomerActivityMonthly.month)
        )
        return [cv.activity(r) for r in self._s.scalars(stmt)]

    def bills(self, customer_id: str, as_of: date) -> list[BillingRecord]:
        stmt = (
            select(m.BillingRecordRow)
            .where(m.BillingRecordRow.customer_id == customer_id)
            .where(m.BillingRecordRow.issue_date <= as_of.isoformat())
            .order_by(m.BillingRecordRow.billing_period)
        )
        return [cv.bill(r) for r in self._s.scalars(stmt)]

    def payments(self, bill_ids: list[str], as_of: date) -> list[Payment]:
        if not bill_ids:
            return []
        stmt = (
            select(m.PaymentRow)
            .where(m.PaymentRow.bill_id.in_(bill_ids))
            .where(m.PaymentRow.paid_date <= as_of.isoformat())
            .order_by(m.PaymentRow.paid_date)
        )
        return [cv.payment(r) for r in self._s.scalars(stmt)]

    def communications(self, customer_id: str, as_of: date) -> list[CommunicationRecord]:
        # sent_at is an ISO timestamp; compare on the date prefix.
        stmt = (
            select(m.CommunicationHistoryRow)
            .where(m.CommunicationHistoryRow.customer_id == customer_id)
            .where(m.CommunicationHistoryRow.sent_at < (as_of.isoformat() + "T99"))
            .order_by(m.CommunicationHistoryRow.sent_at)
        )
        return [cv.comm(r) for r in self._s.scalars(stmt)]
