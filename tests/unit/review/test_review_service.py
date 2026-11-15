"""ReviewService rules via the API: hash binding, BLOCK cannot be approved, WARN acknowledgement,
edit re-validation and approval invalidation."""

from tests.conftest import REVIEWER


def _approve(client, draft, **extra):
    body = {"reviewer_id": REVIEWER, "content_hash": draft["content_hash"], **extra}
    return client.post(f"/api/v1/drafts/{draft['draft_id']}/approve", json=body)


def _edit(client, draft, body_text, subject=None):
    return client.patch(
        f"/api/v1/drafts/{draft['draft_id']}",
        json={"reviewer_id": REVIEWER, "subject": subject or draft["subject"], "body": body_text},
    )


def test_approve_pass_draft(client, make_draft):
    draft = make_draft("C0005")
    response = _approve(client, draft, comment="Looks right")
    assert response.status_code == 200
    view = response.json()
    assert view["state"] == "APPROVED"
    assert view["reviewer_actions"][-1]["action"] == "APPROVE"
    assert view["reviewer_actions"][-1]["content_hash"] == draft["content_hash"]
    assert "DELIVER" in view["allowed_actions"]


def test_approve_with_stale_hash_is_rejected(client, make_draft):
    draft = make_draft("C0005")
    response = _approve(client, {**draft, "content_hash": "sha256:stale"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HASH_MISMATCH"


def test_blocked_draft_cannot_be_approved(client, make_draft):
    draft = make_draft("C0008")
    assert draft["state"] == "BLOCKED"
    assert "APPROVE" not in draft["allowed_actions"]
    response = _approve(client, draft)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VALIDATION_BLOCKED"


def test_edit_is_revalidated_and_can_unblock(client, make_draft):
    draft = make_draft("C0005")
    bad = _edit(client, draft, draft["body"] + "\nPay within 24 hours or face legal action.")
    assert bad.status_code == 200
    bad_view = bad.json()
    assert bad_view["state"] == "BLOCKED"
    assert bad_view["validation"]["validation_run"] == 2
    failed = {f["check_id"] for f in bad_view["validation"]["findings"] if f["severity"] == "BLOCK"}
    assert {"DATE_GROUNDED", "BLOCKED_LANGUAGE"} <= failed

    fixed = _edit(client, bad_view, draft["body"])
    assert fixed.json()["state"] == "PENDING_REVIEW"
    assert fixed.json()["content_hash"] == draft["content_hash"]


def test_invented_amount_in_edit_blocks(client, make_draft):
    draft = make_draft("C0005")
    view = _edit(client, draft, draft["body"].replace("₹599.00", "₹650.00")).json()
    assert view["state"] == "BLOCKED"
    assert any(
        f["check_id"] == "AMOUNT_GROUNDED" and f["severity"] == "BLOCK"
        for f in view["validation"]["findings"]
    )


def test_warn_requires_acknowledgement(client, make_draft):
    draft = make_draft("C0005")
    warned = _edit(client, draft, draft["body"] + "\nThis is urgent.").json()
    assert warned["validation"]["overall"] == "WARN"
    assert warned["state"] == "PENDING_REVIEW"

    no_ack = _approve(client, warned)
    assert no_ack.status_code == 422
    assert no_ack.json()["error"]["code"] == "WARNINGS_NOT_ACKNOWLEDGED"

    ok = _approve(client, warned, acknowledge_warnings=True)
    assert ok.status_code == 200
    assert ok.json()["state"] == "APPROVED"


def test_edit_after_approval_invalidates_approval(client, make_draft):
    draft = make_draft("C0005")
    approved = _approve(client, draft).json()
    edited = _edit(client, approved, draft["body"] + "\nThank you.").json()
    assert edited["state"] == "PENDING_REVIEW"
    assert edited["content_hash"] != approved["content_hash"]
    # The old approval cannot be used to deliver the new text.
    response = client.post(
        f"/api/v1/drafts/{draft['draft_id']}/deliver", json={"reviewer_id": REVIEWER}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_APPROVED"


def test_reject_records_reason_and_is_terminal(client, make_draft):
    draft = make_draft("C0001")
    response = client.post(
        f"/api/v1/drafts/{draft['draft_id']}/reject",
        json={
            "reviewer_id": REVIEWER,
            "reason": "WRONG_TONE",
            "comment": "Too formal",
            "rubric": {"relevance": 4, "clarity": 4, "personalization": 2, "cta": 3, "tone": 2},
        },
    )
    assert response.status_code == 200
    view = response.json()
    assert view["state"] == "REJECTED"
    assert view["allowed_actions"] == []
    assert view["reviewer_actions"][-1]["rejection_reason"] == "WRONG_TONE"
    assert view["reviewer_actions"][-1]["rubric"]["tone"] == 2

    again = _approve(client, view)
    assert again.status_code == 409


def test_rejected_draft_cannot_be_edited(client, make_draft):
    draft = make_draft("C0001")
    client.post(
        f"/api/v1/drafts/{draft['draft_id']}/reject",
        json={"reviewer_id": REVIEWER, "reason": "OTHER"},
    )
    response = _edit(client, draft, draft["body"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_invalid_reviewer_id_and_reason_rejected(client, make_draft):
    draft = make_draft("C0001")
    bad_reviewer = client.post(
        f"/api/v1/drafts/{draft['draft_id']}/approve",
        json={"reviewer_id": "someone@example.com", "content_hash": draft["content_hash"]},
    )
    assert bad_reviewer.status_code == 422
    bad_reason = client.post(
        f"/api/v1/drafts/{draft['draft_id']}/reject",
        json={"reviewer_id": REVIEWER, "reason": "BECAUSE"},
    )
    assert bad_reason.status_code == 422
    assert bad_reason.json()["error"]["code"] == "REQUEST_INVALID"
