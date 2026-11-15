# Assumptions

All project assumptions, kept in sync. Thresholds are illustrative defaults, not company policy.

## Data & classification (M1)

| # | Assumption | Where configured |
|---|---|---|
| A-01 | Activity is aggregated monthly (active days, usage events). "Last 6 months" = the 6 full calendar months before the as-of month; the as-of month itself is partial and only used for `days_since_last_activity`. | `app/features/builder.py` |
| A-02 | Everything is computed as of a fixed reference date (default 2026-11-15). Data dated after it is ignored (two leakage guards: repository queries + `restrict_to_as_of`). | `AS_OF_DATE` in `.env` |
| A-03 | One bill per customer per month; the bill that sets the billing state is the most severe one issued in the last 3 months (conflict > dispute > overdue > not yet due > paid). | `segments.yaml: features.bill_lookback_months` |
| A-04 | Single currency INR; money stored as integer paise. | DB schema |
| A-07 | Names and emails are fake (`<name>.<id>@example.test`); names are assigned at random, independent of archetype. The DB rejects other email domains and non-synthetic rows. | `data/synthetic/generate.py`, `app/data/models.py` |
| S-01 | A month is "active" with ≥ 3 active days. | `segments.yaml` |
| S-02 | INSUFFICIENT_DATA: tenure < 3 months, or < 3 of the last 6 months observed, or recent activity missing. | `segments.yaml` |
| S-03 | DORMANT: ≥ 60 days since last activity, or zero usage in the last 3 months with an active plan. | `segments.yaml` |
| S-04 | DECLINING_ACTIVITY: prior 3-month average ≥ 5 events and recent/prior ratio ≤ 0.70. | `segments.yaml` |
| S-05 | CONSISTENT: active ≥ 5 of 6 months, ratio > 0.70, coefficient of variation ≤ 0.5, on-time payment rate ≥ 80%. | `segments.yaml` |
| S-06 | LOYALTY_CANDIDATE: CONSISTENT, tenure ≥ 12 months, on-time ≥ 90%, no bill settled late in the last 6 months, ≥ 1 active plan. Spend is never used (income proxy). | `segments.yaml` |
| S-07 | PAYMENT_REMINDER: current bill OVERDUE or PARTIALLY_PAID_OVERDUE. Disputed / contradictory bills never set it; they add BILL_DISPUTED / BILL_DATA_CONFLICT for escalation. | `segments.yaml` |
| S-08 | "On time" = paid in full on or before the due date. A bill that is still unpaid counts against the on-time rate but is not a "late payment" (it is handled by PAYMENT_REMINDER). | `app/features/builder.py` |
| S-09 | Confidence is a transparent rule score (completeness × margin), not a probability. Bands: HIGH ≥ 0.75, MEDIUM ≥ 0.45. | `segments.yaml` |

> TODO (M2): add billing, offer and contact assumptions.
