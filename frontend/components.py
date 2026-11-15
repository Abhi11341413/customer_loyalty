"""Small render helpers (badges, findings list).

Owner: M4. Presentation only; no business logic.
"""

from __future__ import annotations

import streamlit as st

SEVERITY_ICON = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "⛔", "ESCALATE": "🟠"}
STATE_ICON = {
    "PENDING_REVIEW": "📝",
    "BLOCKED": "⛔",
    "ESCALATED": "🟠",
    "APPROVED": "✔️",
    "REJECTED": "✖️",
    "DELIVERED": "📨",
    "DELIVERY_BLOCKED": "🚫",
}


def severity_badge(severity: str) -> str:
    return f"{SEVERITY_ICON.get(severity, '•')} {severity}"


def state_badge(state: str) -> str:
    return f"{STATE_ICON.get(state, '•')} {state}"


def render_findings(validation: dict) -> None:
    """Failed checks first (with the offending excerpt), then a compact list of passes."""
    findings = validation.get("findings", [])
    failed = [f for f in findings if f["severity"] != "PASS"]
    passed = [f for f in findings if f["severity"] == "PASS"]
    st.markdown(
        f"**Validation:** {severity_badge(validation.get('overall', '?'))} "
        f"(run {validation.get('validation_run', 1)})"
    )
    for f in failed:
        tag = "mandatory" if f.get("mandatory") else "advisory"
        line = (
            f"{SEVERITY_ICON.get(f['severity'], '•')} **{f['check_id']}** ({tag}): {f['message']}"
        )
        if f.get("span"):
            line += f"  \n&nbsp;&nbsp;&nbsp;offending text: `{f['span']}`"
        st.markdown(line)
    if passed:
        st.caption("Passed: " + " · ".join(f"✓ {f['check_id']}" for f in passed))


def render_reason_codes(reason_codes: list[dict]) -> None:
    for rc in reason_codes:
        st.markdown(f"- {rc['text']}  \n  <small>`{rc['code']}`</small>", unsafe_allow_html=True)


def render_refusal(title: str, reasons: list[str], kind: str = "error") -> None:
    box = st.error if kind == "error" else st.warning
    box(f"**{title}**\n\n" + "\n".join(f"- `{r}`" for r in reasons))
