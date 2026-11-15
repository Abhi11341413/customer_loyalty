"""ProfileAssembler (FR-01): fetch only permitted fields for one customer as of a date.

Owner: M1. Never reads protected/proxy attributes (none exist in the schema) and never reads
data dated after as_of_date.
"""

from datetime import date

from app.data.repositories.customer_repo import CustomerReader
from app.schemas.customer import CustomerProfile
from app.schemas.enums import AccountStatus


class CustomerNotFoundError(LookupError):
    def __init__(self, customer_id: str) -> None:
        super().__init__(f"Customer {customer_id} not found")
        self.customer_id = customer_id


class NonSyntheticDataError(RuntimeError):
    """Raised if a row is not marked synthetic. The app must never process real data."""


class ProfileAssembler:
    def __init__(self, reader: CustomerReader) -> None:
        self._r = reader

    def assemble(self, customer_id: str, as_of: date) -> CustomerProfile:
        cust = self._r.get_customer(customer_id)
        if cust is None:
            raise CustomerNotFoundError(customer_id)
        if cust.is_synthetic != 1:
            raise NonSyntheticDataError(customer_id)
        bills = self._r.bills(customer_id, as_of)
        return CustomerProfile(
            customer_id=cust.customer_id,
            as_of_date=as_of,
            first_name=cust.first_name,
            email=cust.email,
            customer_since=date.fromisoformat(cust.customer_since),
            account_status=AccountStatus(cust.account_status),
            contact_preferences=self._r.preferences(customer_id),
            plans=self._r.plans(customer_id, as_of),
            activity=self._r.activity(customer_id, as_of),
            bills=bills,
            payments=self._r.payments([b.bill_id for b in bills], as_of),
            communications=self._r.communications(customer_id, as_of),
        )
