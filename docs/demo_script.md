# Demo Script

Owner: M4. Target: 8 minutes or less. All data is synthetic; `as_of_date` is fixed at
2026-11-15 so every run is identical.

## Before the demo

1. Reset state: delete `data/app.db` and the files in `outbox/` (both git-ignored).
2. `.env`: `LLM_PROVIDER=template` for the safe rehearsal; switch to the real provider once
   M3's client is wired. While M1–M3 components are still pending, `PIPELINE_STUBS=true`.
3. Start the backend: `uvicorn app.main:app --port 8000`, then check
   http://localhost:8000/api/v1/health (`status: ok`).
4. Start the UI: `streamlit run frontend/streamlit_app.py` and open http://localhost:8501.
5. Rehearse twice, once in template-only mode in case the network fails.

## Flow

| # | Customer | Show | Say |
|---|---|---|---|
| 1 | C0001 Consistent | B: reason codes; C: no offer (`OFF-LOY-200` rejected: tenure short) | "Every segment comes with reasons a reviewer can check." |
| 2 | C0002 Loyalty | Offer `OFF-LOY-200` eligible, `OFF-LOY-OLD` rejected `OFFER_EXPIRED`; offer terms disclaimer in body | "Offers are validated deterministically; the LLM never chooses one." |
| 3 | C0003 Declining | Draft does not mention the drop or any numbers | "Internal analytics never leak into the message." |
| 4 | C0004 Dormant | Win-back tone, no guilt | |
| 5 | C0005 Overdue (stage 1) | Edit greeting -> **Save edit & re-validate** -> run 2 PASS -> **Approve** -> **Send (mock)** -> outbox path | "Approval is bound to the exact text; any edit is re-checked." |
| 5b | C0005 again | **Analyze & Draft** -> REFUSED `CONTACT_DUPLICATE_RECENT` | "Duplicate outreach is blocked." |
| 6 | C0006 Overdue (stage 3) | Firm but respectful; no fees or threats | |
| 7 | C0009 Loyal + overdue | C: `LOYALTY_REWARD` deferred (`OFFER_BLOCKED_BY_BILLING`) | "One message, one objective: no reward bundled with a debt reminder." |
| 8 | C0007 Opted out | Red refusal card; no draft area | "Refused before any LLM call." |
| 9 | C0008 Unsafe output | BLOCKED: `NUMBER_GROUNDED` (20%), `DATE_GROUNDED` (within 24 hours), `OFFER_ID_VALID`, `BLOCKED_LANGUAGE` (legal action); Approve disabled; open "Demo: attempt delivery without approval" -> 409 `NOT_APPROVED` | "Unsafe text cannot be approved or sent, even by calling the API directly." |
| 10 | C0010 Disputed | Orange escalation card `BILL_DISPUTED` | "Uncertain or disputed facts go to a human." |
| 11 | History page | Draft table -> pick C0005 -> full audit timeline; filter C0007 -> REFUSED | "Every decision is auditable, without names, emails or message bodies." |

## Bonus: unapproved delivery request

Create a C0005 draft (after a reset), then use the "Demo: attempt delivery without approval"
expander, or `POST /api/v1/drafts/{id}/deliver` from http://localhost:8000/docs. Expected:
409 `NOT_APPROVED`, `deliveries.status = BLOCKED`, audit event `DELIVERY_BLOCKED`.
