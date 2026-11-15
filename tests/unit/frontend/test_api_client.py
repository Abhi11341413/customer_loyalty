import httpx
import pytest

from frontend.api_client import FALLBACK_CUSTOMERS, ApiClient, ApiError


def _client(handler) -> ApiClient:
    return ApiClient("http://backend", transport=httpx.MockTransport(handler))


def test_error_json_becomes_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "error": {"code": "HASH_MISMATCH", "message": "changed", "details": {}},
                "correlation_id": "abc",
            },
        )

    with pytest.raises(ApiError) as info:
        _client(handler).approve("d1", "rev-01", "sha256:x")
    assert info.value.code == "HASH_MISMATCH"
    assert info.value.correlation_id == "abc"
    assert "Reload" in info.value.friendly


def test_unreachable_backend():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ApiError) as info:
        _client(handler).health()
    assert info.value.code == "BACKEND_UNREACHABLE"


def test_customers_falls_back_when_endpoint_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Not Found"})

    assert _client(handler).customers() == FALLBACK_CUSTOMERS


def test_create_draft_sends_expected_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.read()
        return httpx.Response(201, json={"status": "CREATED"})

    _client(handler).create_draft("C0005", regenerate_of="d0")
    assert seen["path"] == "/api/v1/drafts"
    assert b'"regenerate_of":"d0"' in seen["body"].replace(b" ", b"")
