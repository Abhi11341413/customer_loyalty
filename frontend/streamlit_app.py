"""Streamlit workflow page (sections A-E).

Owner: M4. Run with: streamlit run frontend/streamlit_app.py

A. Customer  ->  B. Analysis  ->  C. Strategy & eligibility  ->  D. Draft + findings  ->  E. Review
Every rule (what may be approved, sent, edited) comes from the API's `allowed_actions`.
"""

from __future__ import annotations

import streamlit as st
from api_client import ApiClient, ApiError
from components import (
    render_findings,
    render_reason_codes,
    render_refusal,
    severity_badge,
    state_badge,
)

st.set_page_config(page_title="Customer Engagement Assistant", page_icon="✉️", layout="wide")

REJECTION_REASONS = ["FACTUAL_ERROR", "WRONG_TONE", "WRONG_STRATEGY", "POLICY", "OTHER"]


@st.cache_resource
def get_client() -> ApiClient:
    return ApiClient()


api = get_client()
ss = st.session_state
for key, default in {"analysis": None, "draft": None, "outcome": None, "flash": None}.items():
    ss.setdefault(key, default)


def flash(kind: str, text: str) -> None:
    ss.flash = (kind, text)


def show_error(exc: ApiError) -> None:
    detail = f" (ref {exc.correlation_id[:8]})" if exc.correlation_id else ""
    flash("error", f"{exc.friendly}{detail}")


def load_draft(draft: dict) -> None:
    ss.draft = draft
    ss.analysis = draft.get("policy_decisions") or ss.analysis
    ss.outcome = None


def analyze_and_draft(customer_id: str, regenerate_of: str | None = None) -> None:
    ss.draft, ss.outcome = None, None
    try:
        resp = api.create_draft(customer_id, regenerate_of=regenerate_of)
    except ApiError as exc:
        if exc.code == "DUPLICATE_PENDING_DRAFT" and exc.details.get("open_draft_ids"):
            load_draft(api.get_draft(exc.details["open_draft_ids"][0]))
            flash("info", "This customer already has an open draft; it has been loaded.")
        else:
            show_error(exc)
        return
    ss.analysis = resp.get("analysis")
    if resp["status"] == "CREATED":
        ss.draft = resp["draft"]
    else:
        ss.outcome = (resp["status"], resp.get("refusal_reasons", []))


# ---- sidebar ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Session")
    try:
        health = api.health()
        st.markdown(f"**LLM:** `{health['llm_mode']}` · **as of** {health['as_of_date']}")
        st.caption(f"DB {health['db']} · {health['ruleset_version']}")
        if health.get("pipeline_stubs"):
            st.warning(
                "PIPELINE_STUBS is on: classification, policy, generation and guardrails are "
                "scripted placeholders until M1–M3 components land."
            )
    except ApiError as exc:
        st.error(exc.friendly)
        st.stop()
    reviewer_id = st.text_input("Reviewer ID (pseudonymous)", value="rev-01")

st.title("Customer Engagement Assistant")
if ss.flash:
    kind, text = ss.flash
    getattr(st, kind)(text)
    ss.flash = None

col_a, col_main = st.columns([1, 3], gap="large")

# ---- A. customer -----------------------------------------------------------------------
with col_a:
    st.subheader("A. Customer")
    try:
        samples = api.customers()
    except ApiError as exc:
        samples = []
        st.error(exc.friendly)
    labels = {f"{c['customer_id']} · {c.get('hint', '')}": c["customer_id"] for c in samples}
    choice = st.selectbox("Sample customer", list(labels)) if labels else None
    typed = st.text_input("…or customer ID", placeholder="C0001")
    customer_id = (typed.strip().upper() or (labels[choice] if choice else "")).strip()
    if st.button("Analyze & Draft ▶", type="primary", disabled=not customer_id):
        analyze_and_draft(customer_id)
        st.rerun()

# ---- B/C. analysis and strategy --------------------------------------------------------
with col_main:
    analysis = ss.analysis
    if not analysis:
        st.info("Pick a customer and click **Analyze & Draft**.")
        st.stop()

    cls, billing = analysis["classification"], analysis["billing"]
    offers, contact, strategy = analysis["offers"], analysis["contact"], analysis["strategy"]

    st.subheader("B. Analysis")
    others = [s for s in cls["segments"] if s != cls["primary_segment"]]
    st.markdown(
        f"**Primary:** `{cls['primary_segment']}`"
        + (f" · **also:** {', '.join(f'`{s}`' for s in others)}" if others else "")
        + f"  \n**Confidence:** {cls['confidence']:.2f} ({cls['confidence_band']})"
        + f" · ruleset `{cls['ruleset_version']}`"
    )
    render_reason_codes(cls.get("reason_codes", []))
    with st.expander("Billing evidence"):
        st.markdown(
            f"State **{billing['state']}** · reminder allowed: {billing['reminder_allowed']}"
            + (f" · stage {billing['stage']}" if billing.get("stage") else "")
        )
        if billing.get("verified_facts"):
            st.table(
                {
                    "fact": list(billing["verified_facts"]),
                    "verified value": list(billing["verified_facts"].values()),
                }
            )
        if billing.get("reason_codes"):
            st.caption("Codes: " + ", ".join(billing["reason_codes"]))

    st.subheader("C. Strategy & eligibility")
    st.markdown(
        f"**Objective:** `{strategy['objective']}`"
        + (f" · template `{strategy['template_id']}`" if strategy.get("template_id") else "")
        + (f" · tone `{strategy['tone']}`" if strategy.get("tone") else "")
    )
    for ev in offers.get("eligible", []):
        st.markdown(f"✅ Offer `{ev['offer_id']}` eligible")
    for ev in offers.get("rejected", []):
        st.markdown(f"✗ Offer `{ev['offer_id']}` rejected: {', '.join(ev['failed_checks'])}")
    for sup in strategy.get("suppressed", []):
        st.markdown(f"⏸ `{sup['objective']}` deferred ({', '.join(sup['reason_codes'])})")
    st.markdown(
        "**Contact:** "
        + " · ".join(
            f"{cat} {'✓' if d['allowed'] else '✗ ' + ', '.join(d['reasons'])}"
            for cat, d in contact.items()
        )
    )

    if ss.outcome:
        status, reasons = ss.outcome
        if status == "REFUSED":
            render_refusal(
                "Refused: no message may be sent to this customer. No LLM call was made.", reasons
            )
        else:
            render_refusal(
                "Escalated to a human: no automated draft is created.", reasons, kind="warning"
            )
        st.stop()

    draft = ss.draft
    if not draft:
        st.stop()

    # ---- D. draft ----------------------------------------------------------------------
    st.subheader("D. Draft")
    allowed = set(draft["allowed_actions"])
    st.markdown(
        f"**State:** {state_badge(draft['state'])} · "
        f"**Validation:** {severity_badge(draft['validation']['overall'])}"
    )
    key = draft["content_hash"][-12:]
    editable = "EDIT" in allowed
    subject = st.text_input(
        "Subject", value=draft["subject"], key=f"subj_{key}", disabled=not editable
    )
    body = st.text_area(
        "Body", value=draft["body"], height=320, key=f"body_{key}", disabled=not editable
    )
    changed = subject != draft["subject"] or body != draft["body"]
    m = draft["model"]
    st.caption(
        f"Model `{m['model_id']}` ({m['provider']}) · prompt {m.get('prompt_version') or '—'}"
        f" · template `{m['template']}`" + (" · FALLBACK" if m.get("fallback_used") else "")
    )
    render_findings(draft["validation"])

    b1, b2, _ = st.columns([1, 1, 2])
    if b1.button("Save edit & re-validate", disabled=not (editable and changed)):
        try:
            load_draft(api.edit_draft(draft["draft_id"], reviewer_id, subject, body))
            flash("success", "Edit saved and re-validated.")
        except ApiError as exc:
            show_error(exc)
        st.rerun()
    if b2.button("Re-validate", disabled="REVALIDATE" not in allowed or changed):
        try:
            api.revalidate(draft["draft_id"])
            load_draft(api.get_draft(draft["draft_id"]))
        except ApiError as exc:
            show_error(exc)
        st.rerun()
    if changed:
        st.info("You have unsaved edits. Save them (they will be re-validated) before approving.")

    # ---- E. review ---------------------------------------------------------------------
    st.subheader("E. Review")
    comment = st.text_input("Comment (optional)", key=f"comment_{key}")
    rubric = None
    if st.checkbox("Score this draft (rubric 1–5)", key=f"rub_{key}"):
        cols = st.columns(5)
        dims = ["relevance", "clarity", "personalization", "cta", "tone"]
        rubric = {d: cols[i].slider(d, 1, 5, 4, key=f"{d}_{key}") for i, d in enumerate(dims)}
    ack = True
    if draft["validation"]["overall"] == "WARN" and "APPROVE" in allowed:
        ack = st.checkbox("I have reviewed the warnings", key=f"ack_{key}")

    c1, c2, c3, c4 = st.columns(4)
    if c1.button(
        "✓ Approve", type="primary", disabled="APPROVE" not in allowed or changed or not ack
    ):
        try:
            load_draft(
                api.approve(
                    draft["draft_id"],
                    reviewer_id,
                    draft["content_hash"],
                    comment,
                    rubric,
                    acknowledge_warnings=ack,
                )
            )
            flash("success", "Approved. You can now send it (mock).")
        except ApiError as exc:
            show_error(exc)
        st.rerun()
    reason = c2.selectbox(
        "Reject reason",
        REJECTION_REASONS,
        label_visibility="collapsed",
        disabled="REJECT" not in allowed,
    )
    if c2.button("✗ Reject", disabled="REJECT" not in allowed):
        try:
            load_draft(api.reject(draft["draft_id"], reviewer_id, reason, comment, rubric))
            flash("info", "Draft rejected.")
        except ApiError as exc:
            show_error(exc)
        st.rerun()
    if c3.button("↻ Regenerate", disabled="REGENERATE" not in allowed):
        analyze_and_draft(draft["customer_id"], regenerate_of=draft["draft_id"])
        st.rerun()
    if "DELIVER" in allowed and c4.button("✉ Send (mock)", type="primary"):
        try:
            result = api.deliver(draft["draft_id"], reviewer_id)
            flash("success", f"Delivered (mock) ✓ → `{result['outbox_path']}`")
        except ApiError as exc:
            show_error(exc)
        load_draft(api.get_draft(draft["draft_id"]))
        st.rerun()

    if draft.get("delivery"):
        d = draft["delivery"]
        st.markdown(
            f"**Delivery:** {d['status']}"
            + (f" · {d['block_reason']}" if d.get("block_reason") else "")
            + (f" · `{d['outbox_path']}`" if d.get("outbox_path") else "")
        )

    with st.expander("Demo: attempt delivery without approval"):
        st.caption("Calls the delivery endpoint directly. The delivery gate must refuse it (409).")
        if st.button("Attempt delivery now", disabled=draft["state"] in ("APPROVED", "DELIVERED")):
            try:
                api.deliver(draft["draft_id"], reviewer_id)
                flash("error", "Unexpected: delivery was accepted.")
            except ApiError as exc:
                flash(
                    "warning",
                    f"Refused as expected: {exc.code} ({exc.details.get('block_reason', '')})",
                )
            load_draft(api.get_draft(draft["draft_id"]))
            st.rerun()

    if draft.get("reviewer_actions"):
        with st.expander("Reviewer actions"):
            for a in draft["reviewer_actions"]:
                st.markdown(
                    f"- {a['created_at'][:19]} · `{a['reviewer_id']}` · **{a['action']}**"
                    + (f" · {a['rejection_reason']}" if a.get("rejection_reason") else "")
                    + (f" · “{a['comment']}”" if a.get("comment") else "")
                )
