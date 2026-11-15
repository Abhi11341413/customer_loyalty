import ast
import json
from email import message_from_bytes
from pathlib import Path

import pytest

import app.delivery.mock_email as mock_email_module
from app.delivery.mock_email import MockDeliveryError, MockEmailService


def test_writes_eml_and_json(tmp_path):
    service = MockEmailService(tmp_path / "outbox")
    path = service.send(
        draft_id="d1",
        recipient="ravi.c0005@example.test",
        subject="Hello",
        body="Body text ₹599.00",
        metadata={"objective": "BILLING_REMINDER_COURTEOUS"},
    )
    message = message_from_bytes(Path(path).read_bytes())
    assert message["To"] == "ravi.c0005@example.test"
    assert message["X-Mock-Delivery"] == "true"
    record = json.loads((tmp_path / "outbox" / "d1.json").read_text(encoding="utf-8"))
    assert record["mock"] is True and record["objective"] == "BILLING_REMINDER_COURTEOUS"


@pytest.mark.parametrize("recipient", ["someone@gmail.com", "x@example.test.evil.com", "x@test"])
def test_refuses_non_synthetic_recipient(tmp_path, recipient):
    with pytest.raises(MockDeliveryError):
        MockEmailService(tmp_path).send(
            draft_id="d1", recipient=recipient, subject="s", body="b", metadata={}
        )
    assert not list(tmp_path.iterdir())


def test_module_has_no_network_imports():
    tree = ast.parse(Path(mock_email_module.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint({"smtplib", "socket", "httpx", "requests", "urllib", "http"})
