"""Fairness guard: no protected characteristics or proxies in features or rules."""

import inspect
import re

from app.schemas.customer import CustomerFeatures
from app.segmentation import rules

PROHIBITED_FIELDS = {
    "first_name", "name", "email", "age", "dob", "date_of_birth", "gender", "sex", "ethnicity",
    "race", "religion", "disability", "marital_status", "nationality", "address", "postcode",
    "pin", "pincode", "city", "region", "state_of_residence", "language", "preferred_language",
    "device", "device_type", "device_model", "income", "spend", "amount_due_minor",
    "monthly_price_minor", "bill_amount",
}  # fmt: skip


def test_customer_features_has_no_prohibited_fields():
    assert set(CustomerFeatures.model_fields) & PROHIBITED_FIELDS == set()


def test_rules_reference_only_customer_features():
    """Every `f.<attr>` used in rules.py must be a CustomerFeatures field and not prohibited."""
    source = inspect.getsource(rules)
    used = set(re.findall(r"\bf\.([a-z0-9_]+)", source))
    assert used, "expected rules to read feature attributes"
    assert used <= set(CustomerFeatures.model_fields), used - set(CustomerFeatures.model_fields)
    assert used & PROHIBITED_FIELDS == set()
