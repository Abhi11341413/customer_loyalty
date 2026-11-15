"""Read/write interfaces over the SQLite database.

Owner: M1. Repositories return Pydantic schemas (app/schemas/), never ORM rows.
- customer_repo: CustomerReader (profile data, as-of filtered)
- billing_repo: BillingReader (for M2's BillingPolicyEngine)
- offer_repo: OfferReader (for M2's OfferEligibilityEngine)
- classification_repo: ClassificationWriter
DraftRepo / AuditRepo are left to M4 (tables already exist in app/data/models.py).
"""

from app.data.repositories.billing_repo import BillingReader, SqlBillingReader
from app.data.repositories.classification_repo import SqlClassificationWriter
from app.data.repositories.customer_repo import CustomerReader, SqlCustomerReader
from app.data.repositories.offer_repo import OfferReader, SqlOfferReader

__all__ = [
    "BillingReader",
    "CustomerReader",
    "OfferReader",
    "SqlBillingReader",
    "SqlClassificationWriter",
    "SqlCustomerReader",
    "SqlOfferReader",
]
