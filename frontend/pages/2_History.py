"""F. Audit & history page.

Owner: M4. Table of drafts -> pick one -> timeline of all audit events for its request(s).
"""

from __future__ import annotations

import streamlit as st
from api_client import ApiClient, ApiError
from components import severity_badge, state_badge

st.set_page_config(page_title="Audit & History", page_icon="🗂️", layout="wide")
st.title("F. Audit & History")


@st.cache_resource
def get_client() -> ApiClient:
    return ApiClient()


api = get_client()

f1, f2 = st.columns(2)
customer_filter = f1.text_input("Filter by customer ID", placeholder="C0005").strip().upper()
state_filter = f2.selectbox(
    "Filter by state",
    [
        "",
        "PENDING_REVIEW",
        "BLOCKED",
        "ESCALATED",
        "APPROVED",
        "REJECTED",
        "DELIVERED",
        "DELIVERY_BLOCKED",
    ],
)

try:
    drafts = api.list_drafts(customer_filter or None, state_filter or None)
except ApiError as exc:
    st.error(exc.friendly)
    st.stop()

if not drafts:
    st.info("No drafts yet.")
else:
    st.dataframe(
        [
            {
                "created": d["created_at"][:19].replace("T", " "),
                "customer": d["customer_id"],
                "objective": d["objective"],
                "model": d["model_id"],
                "validation": severity_badge(d["validation_status"]),
                "state": state_badge(d["state"]),
                "reviewer": d.get("last_reviewer_id") or "",
                "delivery": d.get("delivery_status") or "",
                "draft_id": d["draft_id"],
            }
            for d in drafts
        ],
        hide_index=True,
        use_container_width=True,
    )
    options = {
        f"{d['customer_id']} · {d['objective']} · {d['draft_id'][:8]}": d["draft_id"]
        for d in drafts
    }
    picked = st.selectbox("Show audit timeline for", list(options))
    if picked:
        draft_id = options[picked]
        try:
            events = api.audit(draft_id=draft_id, limit=200)
            # Pull the whole request (classification/policy events precede the draft id).
            seen = {e["event_id"] for e in events}
            for cid in {e["correlation_id"] for e in events}:
                for e in api.audit(correlation_id=cid, limit=200):
                    if e["event_id"] not in seen:
                        events.append(e)
                        seen.add(e["event_id"])
        except ApiError as exc:
            st.error(exc.friendly)
            st.stop()
        events.sort(key=lambda e: e["ts"])
        for e in events:
            with st.container(border=True):
                st.markdown(
                    f"**{e['event_type']}** · {e['ts'][:23].replace('T', ' ')} · "
                    f"actor `{e['actor']}`"
                )
                st.json(e["payload"], expanded=False)

st.divider()
st.subheader("Refusals and escalations")
st.caption("Requests that never produced a draft are only in the audit log.")
if customer_filter:
    try:
        events = [
            e
            for e in api.audit(customer_id=customer_filter, limit=200)
            if e["event_type"] in ("REFUSED", "ESCALATED")
        ]
    except ApiError as exc:
        st.error(exc.friendly)
        events = []
    for e in events:
        st.markdown(
            f"- {e['ts'][:19].replace('T', ' ')} · **{e['event_type']}** · "
            f"{', '.join(e['payload'].get('reasons', []))}"
        )
else:
    st.caption("Enter a customer ID above to list them.")
