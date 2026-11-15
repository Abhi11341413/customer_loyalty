"""Extractors normalise equivalent facts and find the defect types from §14.4."""

from decimal import Decimal

import pytest

from app.guardrails import extractors as ex


@pytest.mark.parametrize(
    "text,amount",
    [
        ("₹599.00", "599"),
        ("₹ 599", "599"),
        ("Rs. 1,499.50", "1499.5"),
        ("INR 749", "749"),
        ("599 rupees", "599"),
        ("$20", "20"),
    ],
)
def test_money_normalises(text, amount):
    [s] = ex.find_money(f"Pay {text} today")
    assert s.value == Decimal(amount).normalize()


def test_money_ignores_plain_numbers_and_words():
    assert ex.find_money("Your 2 plans and hours of fun, yours truly") == []


@pytest.mark.parametrize(
    "text,expected",
    [
        ("10 Nov 2026", ex.DateValue(2026, 11, 10)),
        ("10th of November, 2026", ex.DateValue(2026, 11, 10)),
        ("November 10", ex.DateValue(None, 11, 10)),
        ("Nov. 10th, 2026", ex.DateValue(2026, 11, 10)),
        ("October 2026", ex.DateValue(2026, 10, None)),
        ("2026-11-10", ex.DateValue(2026, 11, 10)),
        ("10/11/2026", ex.DateValue(2026, 11, 10)),
    ],
)
def test_absolute_dates(text, expected):
    [s] = ex.find_dates(f"due on {text}.")
    assert s.value == expected


@pytest.mark.parametrize(
    "text",
    [
        "within 24 hours",
        "in 3 days",
        "by tomorrow",
        "before Friday",
        "next Monday",
        "end of the week",
        "48 hours",
    ],  # fmt: skip
)
def test_relative_deadlines(text):
    spans = ex.find_dates(f"Please pay {text} thanks")
    assert spans and spans[0].value[0] == "REL"


def test_today_alone_is_not_a_deadline():
    assert ex.find_dates("We would love to hear from you today.") == []


def test_date_matching_rules():
    d = ex.DateValue(2026, 11, 10)
    assert ex.DateValue(None, 11, 10).matches(d)
    assert not ex.DateValue(2025, 11, 10).matches(d)
    assert not ex.DateValue(2026, 11, None).matches(d)


@pytest.mark.parametrize(
    "text,value",
    [
        ("20% off", (Decimal(20), "percent")),
        ("20 percent", (Decimal(20), "percent")),
        ("5 GB", (Decimal(5), "gb")),
        ("500 points", (Decimal(500), "points")),
        ("26 days", (Decimal(26), "day")),
        ("10 years", (Decimal(10), "year")),
    ],
)
def test_unit_numbers(text, value):
    [s] = ex.find_unit_numbers(f"get {text} now")
    assert s.value == value


@pytest.mark.parametrize(
    "text,category",
    [
        ("mail ravi.c0005@example.test now", "EMAIL"),
        ("call +91 98765 43210", "PHONE"),
        ("card 4111 1111 1111 1111", "CARD_NUMBER"),
        ("id 1234 5678 9012", "GOV_ID"),
        ("PAN ABCDE1234F", "GOV_ID"),
        ("account C0005", "INTERNAL_ID"),
        ("plan PL-POST-499", "INTERNAL_ID"),
    ],
)
def test_pii_categories(text, category):
    assert [s.value for s in ex.find_pii(text)] == [category]


def test_pii_ignores_amounts_and_dates():
    assert ex.find_pii("₹1,499.00 due on 2026-11-10 or 10/11/2026") == []


def test_offer_ids_and_phrases():
    assert [s.value for s in ex.find_offer_ids("use off-loy-200 or OFF-RE-5GB.")] == [
        "OFF-LOY-200",
        "OFF-RE-5GB",
    ]
    spans = ex.find_phrases("Legal   Action follows; illegal actions do not", ["legal action"])
    assert [s.text for s in spans] == ["Legal   Action"]
