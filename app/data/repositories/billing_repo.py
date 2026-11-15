"""BillingReader: read-only billing access for M2's BillingPolicyEngine.

Owner: M1 (implementation) — interface agreed with M2.
"""

from datetime import date
from typing import Protocol

from sqlalchemy.orm import Session

from app.data.repositories.customer_repo import SqlCustomerReader
from app.schemas.customer import BillingRecord, CommunicationRecord, Payment


class BillingReader(Protocol):
    def bills_for(self, customer_id: str, as_of: date) -> list[BillingRecord]: ...
    def payments_for(self, bill_ids: list[str], as_of: date) -> list[Payment]: ...
    def reminders_for(self, customer_id: str, as_of: date) -> list[CommunicationRecord]: ...


class SqlBillingReader:
    def __init__(self, session: Session) -> None:
        self._c = SqlCustomerReader(session)

    def bills_for(self, customer_id: str, as_of: date) -> list[BillingRecord]:
        return self._c.bills(customer_id, as_of)

    def payments_for(self, bill_ids: list[str], as_of: date) -> list[Payment]:
        return self._c.payments(bill_ids, as_of)

    def reminders_for(self, customer_id: str, as_of: date) -> list[CommunicationRecord]:
        return [
            c
            for c in self._c.communications(customer_id, as_of)
            if c.objective.startswith("BILLING_REMINDER")
        ]
