from app.audit.logger import AuditLogger, sanitize_payload
from app.schemas.enums import AuditEventType


def test_sanitize_drops_forbidden_keys_and_masks_emails():
    cleaned, count = sanitize_payload(
        {
            "objective": "APPRECIATION",
            "first_name": "Asha",
            "body": "Hi Asha",
            "nested": {"email": "a@example.test", "note": "contact a.b@example.test"},
            "list": ["ok", "x@y.com"],
        }
    )
    assert cleaned == {
        "objective": "APPRECIATION",
        "nested": {"note": "contact [REDACTED]"},
        "list": ["ok", "[REDACTED]"],
    }
    assert count == 5


def test_log_and_query_in_order(container):
    audit = container.audit
    for event in (
        AuditEventType.CLASSIFIED,
        AuditEventType.POLICY_DECIDED,
        AuditEventType.DRAFT_GENERATED,
    ):
        audit.log(
            event,
            customer_ref="C0001",
            draft_id="d1",
            correlation_id="corr1",
            payload={"subject": "secret", "k": 1},
        )
    audit.log(AuditEventType.REFUSED, customer_ref="C0007", correlation_id="corr2")

    events = audit.query(draft_id="d1")
    assert [e.event_type for e in events] == ["CLASSIFIED", "POLICY_DECIDED", "DRAFT_GENERATED"]
    assert all("subject" not in e.payload and e.payload["_redactions"] == 1 for e in events)
    assert [e.event_type for e in audit.query(customer_id="C0007")] == ["REFUSED"]
    assert len(audit.query(correlation_id="corr1", limit=2)) == 2


def test_audit_logger_is_append_only():
    public = {name for name in dir(AuditLogger) if not name.startswith("_")}
    assert public == {"log", "query"}


def test_pipeline_audit_has_no_pii(client, make_draft):
    draft = make_draft("C0005")
    events = client.get("/api/v1/audit?customer_id=C0005").json()
    blob = str(events).lower()
    assert "ravi" not in blob and "@example.test" not in blob
    assert draft["body"][:30].lower() not in blob
    types = [e["event_type"] for e in events]
    assert types == ["CLASSIFIED", "POLICY_DECIDED", "DRAFT_GENERATED", "VALIDATED"]
    assert len({e["correlation_id"] for e in events}) == 1
