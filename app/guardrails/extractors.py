"""Regex extractors + normalisation for factual tokens in draft text (§9.2).

Owner: M3.

Each extractor returns ``Span``s with a normalised ``value`` so that the same fact
written differently ("₹599", "Rs. 599.00", "599 rupees") compares equal. The same
extractors run over the verified values from ``LLMInput`` to build the allow-list.

Known limitation (documented in the evaluation report): spelled-out numbers and vague
time phrases ("twenty percent", "a couple of weeks") are not extracted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# --------------------------------------------------------------------------- core


@dataclass(frozen=True)
class Span:
    text: str
    start: int
    end: int
    value: object  # normalised value; comparison key


def _non_overlapping(spans: list[Span]) -> list[Span]:
    """Drop spans contained in a longer span (keeps the most specific long match)."""
    spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
    out: list[Span] = []
    for s in spans:
        if out and s.start < out[-1].end:
            if (s.end - s.start) > (out[-1].end - out[-1].start):
                out[-1] = s
            continue
        out.append(s)
    return out


def phrase_pattern(term: str) -> re.Pattern[str]:
    """Case-insensitive whole-phrase matcher; any whitespace run matches a space."""
    parts = [re.escape(p) for p in term.split()]
    body = r"\s+".join(parts)
    left = r"(?<![\w])" if term[:1].isalnum() else ""
    right = r"(?![\w])" if term[-1:].isalnum() else ""
    return re.compile(left + body + right, re.IGNORECASE)


def find_phrases(text: str, terms: Iterable[str]) -> list[Span]:
    spans = []
    for term in terms:
        for m in phrase_pattern(term).finditer(text):
            spans.append(Span(m.group(0), m.start(), m.end(), term.lower()))
    return _non_overlapping(spans)


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "")).normalize()
    except InvalidOperation:
        return None


# --------------------------------------------------------------------------- money

_NUM = r"\d[\d,]*(?:\.\d+)?"
_MONEY_RE = re.compile(
    rf"(?:₹|\brs\.?|\binr|\$|\busd)\s*(?P<a>{_NUM})"
    rf"|(?P<b>{_NUM})\s*(?:rupees?|inr|rs\.?)(?![a-z])",
    re.IGNORECASE,
)


def find_money(text: str) -> list[Span]:
    spans = []
    for m in _MONEY_RE.finditer(text):
        amount = _to_decimal(m.group("a") or m.group("b"))
        if amount is not None:
            spans.append(Span(m.group(0).strip(), m.start(), m.end(), amount))
    return _non_overlapping(spans)


# --------------------------------------------------------------------------- dates

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4,
    "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8,
    "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}  # fmt: skip
_MON = r"(?P<mon>" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?"
_ORD = r"(?:st|nd|rd|th)?"
_YEAR = r"(?P<year>(?:19|20)\d{2})"

_DATE_PATTERNS: list[re.Pattern[str]] = [
    # 10 Nov 2026 / 10th of November, 2026 / 10 Nov
    re.compile(rf"\b(?P<day>\d{{1,2}}){_ORD}\s+(?:of\s+)?{_MON}(?:,?\s+{_YEAR})?\b", re.I),
    # Nov 10, 2026 / November 10th
    re.compile(rf"\b{_MON}\s+(?P<day>\d{{1,2}}){_ORD}(?:,?\s+{_YEAR})?\b", re.I),
    # October 2026
    re.compile(rf"\b{_MON}\s+{_YEAR}\b", re.I),
    # 2026-11-10
    re.compile(r"\b(?P<year>\d{4})-(?P<m>\d{2})-(?P<day>\d{2})\b"),
    # 10/11/2026, 10-11-26, 10.11.2026 (day-first, Indian convention)
    re.compile(r"\b(?P<day>\d{1,2})[/.\-](?P<m>\d{1,2})[/.\-](?P<year>\d{2,4})\b"),
]
_WEEKDAYS = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
_RELATIVE_RE = re.compile(
    r"\b(?:"
    r"within\s+(?:the\s+next\s+)?\d+\s*(?:hours?|hrs?|days?|weeks?|minutes?|mins?)"
    r"|in\s+(?:the\s+next\s+)?\d+\s*(?:hours?|hrs?|days?|weeks?|minutes?)"
    r"|(?:by|before|until)\s+(?:today|tonight|tomorrow|end\s+of\s+(?:the\s+)?(?:day|week|month)|"
    + _WEEKDAYS
    + r")"
    r"|end\s+of\s+(?:the\s+)?(?:day|week|month)"
    r"|next\s+(?:" + _WEEKDAYS + r"|week|month)"
    r"|this\s+(?:" + _WEEKDAYS + r"|week|weekend|month)"
    r"|tonight|tomorrow"
    r"|\d+\s*(?:hours?|hrs?)\b"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DateValue:
    year: int | None
    month: int
    day: int | None

    def matches(self, other: DateValue) -> bool:
        if self.month != other.month or self.day != other.day:
            return False
        return self.year is None or other.year is None or self.year == other.year


def _norm_year(y: str | None) -> int | None:
    if not y:
        return None
    n = int(y)
    return n + 2000 if n < 100 else n


def find_dates(text: str) -> list[Span]:
    """Absolute dates (value=DateValue) and relative expressions (value=('REL', text))."""
    spans: list[Span] = []
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(text):
            g = m.groupdict()
            month = _MONTHS[g["mon"].lower()] if g.get("mon") else int(g["m"])
            day = int(g["day"]) if g.get("day") else None
            if not 1 <= month <= 12 or (day is not None and not 1 <= day <= 31):
                continue
            spans.append(
                Span(
                    m.group(0), m.start(), m.end(), DateValue(_norm_year(g.get("year")), month, day)
                )
            )
    for m in _RELATIVE_RE.finditer(text):
        spans.append(
            Span(m.group(0), m.start(), m.end(), ("REL", " ".join(m.group(0).lower().split())))
        )
    return _non_overlapping(spans)


# --------------------------------------------------------------------------- numbers with units

_UNIT_CANON = {
    "%": "percent", "percent": "percent", "per cent": "percent",
    "gb": "gb", "mb": "mb", "tb": "tb",
    "points": "points", "point": "points", "pts": "points",
    "day": "day", "days": "day", "hour": "hour", "hours": "hour", "hr": "hour", "hrs": "hour",
    "week": "week", "weeks": "week", "month": "month", "months": "month",
    "year": "year", "years": "year", "minute": "minute", "minutes": "minute",
    "x": "times", "times": "times",
}  # fmt: skip
_UNIT_RE = re.compile(
    rf"(?P<n>{_NUM})\s*(?P<u>%|per\s+cent|percent|gb|mb|tb|points?|pts|days?|hours?|hrs?"
    r"|weeks?|months?|years?|minutes?|times|x)(?![a-z])",
    re.IGNORECASE,
)


def find_unit_numbers(text: str) -> list[Span]:
    """Numbers with a unit: 20%, 5 GB, 500 points, 24 hours, 10 years (value=(Decimal, unit))."""
    spans = []
    for m in _UNIT_RE.finditer(text):
        n = _to_decimal(m.group("n"))
        unit = _UNIT_CANON.get(" ".join(m.group("u").lower().split()))
        if n is not None and unit:
            spans.append(Span(m.group(0), m.start(), m.end(), (n, unit)))
    return _non_overlapping(spans)


def bare_number(value: str) -> Decimal | None:
    """A verified slot value that is just a number (e.g. days_overdue "26")."""
    v = value.strip()
    return _to_decimal(v) if re.fullmatch(_NUM, v) else None


# --------------------------------------------------------------------------- offer ids

OFFER_ID_RE = re.compile(r"\bOFF-[A-Z0-9][A-Z0-9-]*[A-Z0-9]\b", re.IGNORECASE)


def find_offer_ids(text: str) -> list[Span]:
    return [
        Span(m.group(0), m.start(), m.end(), m.group(0).upper()) for m in OFFER_ID_RE.finditer(text)
    ]


# --------------------------------------------------------------------------- PII / internal ids

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_DIGIT_RUN_RE = re.compile(r"\+?\d[\d\s\-]{8,24}\d")
_GOV_ID_RE = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")  # Aadhaar-like 4-4-4
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")  # PAN-like
_INTERNAL_ID_RE = re.compile(
    r"\b(?:C\d{4}|B-C\d{4}-\d{4}-\d{2}|PL-[A-Z0-9-]+|CP-[A-Z0-9-]+|CMP-[A-Z0-9-]+)\b"
)


def find_pii(text: str) -> list[Span]:
    """value = category: EMAIL, PHONE, CARD_NUMBER, GOV_ID, INTERNAL_ID."""
    spans: list[Span] = []
    spans += [Span(m.group(0), m.start(), m.end(), "EMAIL") for m in _EMAIL_RE.finditer(text)]
    spans += [Span(m.group(0), m.start(), m.end(), "GOV_ID") for m in _GOV_ID_RE.finditer(text)]
    spans += [Span(m.group(0), m.start(), m.end(), "GOV_ID") for m in _PAN_RE.finditer(text)]
    for m in _DIGIT_RUN_RE.finditer(text):
        digits = sum(c.isdigit() for c in m.group(0))
        if 13 <= digits <= 19:
            spans.append(Span(m.group(0), m.start(), m.end(), "CARD_NUMBER"))
        elif 10 <= digits <= 12:
            spans.append(Span(m.group(0), m.start(), m.end(), "PHONE"))
    spans += [
        Span(m.group(0), m.start(), m.end(), "INTERNAL_ID") for m in _INTERNAL_ID_RE.finditer(text)
    ]
    return _non_overlapping(spans)


_SALUTATION_RE = re.compile(r"^\s*(?:hi|hello|dear|hey)\s+(?P<name>[A-Z][\w'-]*)", re.IGNORECASE)


def salutation_name(text: str) -> Span | None:
    m = _SALUTATION_RE.search(text)
    if not m:
        return None
    return Span(m.group("name"), m.start("name"), m.end("name"), m.group("name"))


def normalize_ws(text: str) -> str:
    return " ".join(text.split()).lower()
