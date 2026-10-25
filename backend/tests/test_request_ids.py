"""Request-correlation contract tests."""

from uuid import UUID

import pytest
from starlette.routing import Route

from app.models.entities import AuditEvent
from app.services.audit_service import log_audit_event
from conftest import get_auth_headers


def _assert_generated_uuid4(value: str) -> None:
    parsed = UUID(value)
    assert parsed.version == 4
    assert str(parsed) == value


def test_safe_caller_request_id_is_echoed(client):
    request_id = "client-trace_2026.10.24"

    response = client.get("/", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id


def test_missing_request_id_is_generated(client):
    response = client.get("/")

    assert response.status_code == 200
    _assert_generated_uuid4(response.headers["X-Request-ID"])


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "contains space",
        "../../another-case",
        b"unicode-\xe9",
        "<script>",
        "x" * 129,
    ],
)
def test_unsafe_request_id_is_replaced(client, unsafe_value):
    response = client.get("/", headers={"X-Request-ID": unsafe_value})

    assert response.status_code == 200
    replacement = response.headers["X-Request-ID"]
    assert replacement != unsafe_value
    _assert_generated_uuid4(replacement)


def test_request_id_is_returned_on_http_errors(client):
    request_id = "not-found-correlation"

    response = client.get(
        "/api/v1/route-that-does-not-exist",
        headers={"X-Request-ID": request_id},
    )

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == request_id


def test_request_id_is_returned_on_validation_errors(client, test_users):
    request_id = "validation-correlation"
    headers = get_auth_headers(test_users["clinician_a"])
    headers["X-Request-ID"] = request_id

    response = client.post(
        "/api/v1/cases",
        headers=headers,
        json={},
    )

    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == request_id


def test_request_id_is_returned_on_unhandled_errors(client):
    request_id = "server-error-correlation"

    async def fail_for_contract_test(_request):
        raise RuntimeError("request-id contract fixture")

    route = Route(
        "/__tests__/request-id-unhandled-error",
        fail_for_contract_test,
        methods=["GET"],
    )
    client.app.router.routes.append(route)
    transport = client._transport
    previous = transport.raise_server_exceptions
    transport.raise_server_exceptions = False
    try:
        response = client.get(
            "/__tests__/request-id-unhandled-error",
            headers={"X-Request-ID": request_id},
        )
    finally:
        transport.raise_server_exceptions = previous
        client.app.router.routes.remove(route)

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == request_id
    assert response.json()["request_id"] == request_id


def test_request_id_is_exposed_to_browser_clients(client):
    response = client.get(
        "/",
        headers={"Origin": "http://localhost:8443"},
    )

    exposed = {
        item.strip().lower()
        for item in response.headers["Access-Control-Expose-Headers"].split(",")
    }
    assert "x-request-id" in exposed


def test_request_id_is_added_to_audit_metadata_and_context_is_reset(
    client, db_session, test_users
):
    request_id = "case-create-correlation-001"
    headers = get_auth_headers(test_users["clinician_a"])
    headers["X-Request-ID"] = request_id

    response = client.post(
        "/api/v1/cases",
        headers=headers,
        json={"pseudonymous_id": "REQUEST-ID-AUDIT-FIXTURE"},
    )

    assert response.status_code == 201
    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "CASE_CREATED")
        .order_by(AuditEvent.id.desc())
        .first()
    )
    assert event is not None
    assert event.details["request_id"] == request_id

    outside_request = log_audit_event(
        db=db_session,
        action="BACKGROUND_TEST",
        resource_type="TEST",
        details={"request_id": "spoofed"},
    )
    assert "request_id" not in outside_request.details
