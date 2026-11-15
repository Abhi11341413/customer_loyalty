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

## Billing, offers, contact and strategy (M2)

| # | Assumption | Where configured |
|---|---|---|
| B-01 | Which bill counts, and its state, use M1's rule (A-03) — one shared implementation (`app/features/billing_state.py`), so the PAYMENT_REMINDER flag and the reminder decision cannot disagree. `grace_days` and `bill_lookback_months` must match `segments.yaml` (checked by a test). | `billing.yaml` |
| B-02 | No grace period: a bill is overdue from the day after its due date. | `billing.yaml: grace_days` |
| B-03 | Reminder stages: 1 = courteous (1–10 days overdue), 2 = polite follow-up (11–20), 3 = firm but respectful (21–60). More than 60 days → escalate to a human (collections), no automated email. | `billing.yaml: reminder_stages` |
| B-04 | At most one reminder per bill every 7 days, and no stage skipping: a customer always gets stage 1 before 2 before 3, even if the days overdue would allow a later stage. | `billing.yaml` |
| B-05 | A partially paid bill is reminded for the outstanding amount only. | `app/policy/billing.py` |
| B-06 | Missing or contradictory billing data (missing due date, PAID with too little paid, overpayment, UNPAID but fully paid) and open disputes are never messaged: they escalate. | `app/policy/billing.py` |
| B-07 | Every billing reminder includes the same support / dispute path text. | `billing.yaml: support_path` |
| O-01 | Offers are pre-approved upstream (A-08); the engine only validates and selects, never creates. | `data/seed/campaign_offers.csv` |
| O-02 | Rewards are not offered while a bill is overdue, partially paid, disputed or contradictory (offer flag `requires_no_overdue`, default on). OPEN-4 default: defer, re-evaluate after payment. | `campaign_offers.csv` |
| O-03 | The same offer is not emailed to the same customer twice within 30 days. | `contact.yaml: duplicate_window_days.same_offer` |
| O-04 | An offer with no plan restriction applies to every active plan. | `offer_plan_eligibility.csv` |
| O-05 | If several offers are eligible, the one with the lowest offer id is chosen (deterministic, no ranking model). | `app/policy/strategy.py` |
| K-01 | Consent is split into service (bill reminders) and marketing (appreciation, rewards, re-engagement, win-back). Appreciation without an offer still counts as marketing (OPEN-5). **Not legal advice.** | `contact.yaml` |
| K-02 | A global opt-out, a closed account, an active "do not contact until" date or preferred channel NONE blocks every email. A suspended account can still get bill reminders. | `contact.yaml: global_blockers` |
| K-03 | Frequency caps: at least 14 days between marketing emails; at most 4 emails of any kind in 30 days; the same objective not within 7 days. | `contact.yaml` |
| K-04 | A missing preference record is treated as "no consent", never guessed. | `app/policy/contact.py` |
| T-01 | One message, one objective. Precedence: escalate > refused by contact policy > billing reminder > loyalty reward > win-back > re-engagement > appreciation > no contact. | `strategy.yaml` |
| T-02 | A loyalty candidate with no eligible reward offer gets an appreciation email instead. | `strategy.yaml: fallback_objective` |
| T-03 | An overdue customer whose last reminder is too recent gets nothing (not a marketing email instead). | `app/policy/strategy.py` |
| T-04 | INSUFFICIENT_DATA always escalates; STANDARD customers get no targeted outreach. | `strategy.yaml` |
