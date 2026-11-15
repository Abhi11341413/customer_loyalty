"""FeatureBuilder: CustomerProfile -> CustomerFeatures (pure, deterministic, no I/O).

Owner: M1. Uses only data dated <= as_of_date. Makes no decisions.
Missing values are reported in `missing_features`, never imputed.
"""

import statistics
from datetime import date

from pydantic import BaseModel

from app.features.billing_state import current_bill
from app.features.preprocess import clean_activity, restrict_to_as_of
from app.schemas.customer import CustomerFeatures, CustomerProfile
from app.schemas.enums import BillState


class FeatureSettings(BaseModel):
    min_active_days: int = 3
    grace_days: int = 0
    bill_lookback_months: int = 3


def _month_key(d: date, offset: int) -> str:
    idx = d.year * 12 + d.month - 1 + offset
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def _shift_months(d: date, months: int) -> date:
    idx = d.year * 12 + d.month - 1 + months
    y, m = idx // 12, idx % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def tenure_months(since: date, as_of: date) -> int:
    n = (as_of.year - since.year) * 12 + (as_of.month - since.month)
    return max(n - 1 if as_of.day < since.day else n, 0)


def _mean(xs: list[int]) -> float | None:
    return round(statistics.mean(xs), 4) if xs else None


class FeatureBuilder:
    def __init__(self, settings: FeatureSettings | None = None) -> None:
        self.settings = settings or FeatureSettings()

    def build(self, profile: CustomerProfile) -> CustomerFeatures:
        p = restrict_to_as_of(profile)
        as_of = p.as_of_date
        missing: list[str] = []
        activity, flags = clean_activity(p.activity, as_of)
        by_month = {a.month: a for a in activity}

        # --- engagement: the 6 full months before as_of's month (k=1 is the latest)
        last6 = [by_month.get(_month_key(as_of, -k)) for k in range(1, 7)]
        recent = [a.usage_events for a in last6[:3] if a]
        prior = [a.usage_events for a in last6[3:] if a]
        observed = [a for a in last6 if a]
        recent_avg, prior_avg = _mean(recent), _mean(prior)
        trend = round(recent_avg / prior_avg, 4) if recent_avg is not None and prior_avg else None
        usages = [a.usage_events for a in observed]
        cv = None
        if usages and statistics.mean(usages) > 0:
            cv = round(statistics.pstdev(usages) / statistics.mean(usages), 4)
        last_dates = [a.last_activity_date for a in activity if a.last_activity_date]
        days_since = (as_of - max(last_dates)).days if last_dates else None

        # --- payments
        paid_by_bill: dict[str, list] = {}
        for pay in p.payments:
            paid_by_bill.setdefault(pay.bill_id, []).append(pay)
        lo12, lo6 = _shift_months(as_of, -12), _shift_months(as_of, -6)
        bills_12 = on_time_12 = late_6 = 0
        for b in p.bills:
            if b.due_date is None:
                flags.append(f"BILL_MISSING_DUE_DATE:{b.bill_id}")
                continue
            if b.status == "WAIVED" or not (lo12 < b.due_date <= as_of):
                continue
            bills_12 += 1
            pays = paid_by_bill.get(b.bill_id, [])
            if sum(x.amount_paid_minor for x in pays if x.paid_date <= b.due_date) >= (
                b.amount_due_minor
            ):
                on_time_12 += 1
            elif b.due_date > lo6 and sum(x.amount_paid_minor for x in pays) >= b.amount_due_minor:
                late_6 += 1  # settled, but after the due date
        rate = round(on_time_12 / bills_12, 4) if bills_12 else None

        # --- current bill
        cur = current_bill(
            p.bills, p.payments, as_of, self.settings.grace_days, self.settings.bill_lookback_months
        )
        state = cur.state if cur else BillState.NO_BILL

        for name, value in (
            ("recent_activity_avg", recent_avg),
            ("prior_activity_avg", prior_avg),
            ("activity_trend_ratio", trend),
            ("activity_cv_6m", cv),
            ("days_since_last_activity", days_since),
            ("on_time_payment_rate_12m", rate),
        ):
            if value is None:
                missing.append(name)

        active_plans = [pl for pl in p.plans if pl.status == "ACTIVE"]
        return CustomerFeatures(
            customer_id=p.customer_id,
            as_of_date=as_of,
            account_status=p.account_status,
            tenure_months=tenure_months(p.customer_since, as_of),
            active_plan_count=len(active_plans),
            active_plan_ids=sorted(pl.plan_id for pl in active_plans),
            months_observed=len(observed),
            active_months_last_6=sum(
                1 for a in observed if a.active_days >= self.settings.min_active_days
            ),
            recent_activity_avg=recent_avg,
            prior_activity_avg=prior_avg,
            activity_trend_ratio=trend,
            activity_cv_6m=cv,
            days_since_last_activity=days_since,
            bills_last_12m=bills_12,
            on_time_bills_last_12m=on_time_12,
            on_time_payment_rate_12m=rate,
            late_payments_last_6m=late_6,
            current_bill_state=state,
            current_bill_id=cur.bill.bill_id if cur else None,
            bill_conflict_type=cur.conflict if cur else None,
            days_overdue=cur.days_overdue if cur else None,
            outstanding_minor=cur.outstanding_minor if cur else None,
            missing_features=missing,
            data_quality_flags=flags,
        )
