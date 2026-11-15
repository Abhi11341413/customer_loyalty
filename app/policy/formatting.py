"""Deterministic display formatting for verified facts (money, dates, periods).

Owner: M2.

Locale-independent on purpose (no ``strftime("%b")``), so the same fact always renders
the same string and guardrails (M3) can match it exactly.
"""

from datetime import date

_MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS_LONG = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_CURRENCY_SYMBOLS = {"INR": "₹"}


def format_money(amount_minor: int, currency: str = "INR", *, drop_zero_paise: bool = False) -> str:
    """``59900, "INR"`` -> ``"₹599.00"``; with ``drop_zero_paise`` -> ``"₹599"``."""
    sign = "-" if amount_minor < 0 else ""
    major, minor = divmod(abs(amount_minor), 100)
    number = f"{major:,}" if drop_zero_paise and minor == 0 else f"{major:,}.{minor:02d}"
    symbol = _CURRENCY_SYMBOLS.get(currency)
    return f"{sign}{symbol}{number}" if symbol else f"{sign}{currency} {number}"


def format_date(d: date) -> str:
    """``date(2026, 11, 10)`` -> ``"10 Nov 2026"``."""
    return f"{d.day} {_MONTHS_SHORT[d.month - 1]} {d.year}"


def format_period(period: str) -> str:
    """``"2026-10"`` -> ``"October 2026"``."""
    year, month = period.split("-")
    return f"{_MONTHS_LONG[int(month) - 1]} {year}"
