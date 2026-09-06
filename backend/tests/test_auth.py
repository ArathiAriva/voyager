"""Shared-token authentication.

A lock on a single-tenant app, not an identity system -- see app/auth.py. The
threat is a public URL letting strangers spend the deployment's OpenRouter credit
and reach the 15 write endpoints.
"""

import pytest


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("VOYAGER_AUTH_TOKEN", "s3cret")
    return "s3cret"


@pytest.mark.asyncio
async def test_requests_without_a_token_are_rejected(client, token):
    assert (await client.get("/api/trips")).status_code == 401


@pytest.mark.asyncio
async def test_a_wrong_token_is_rejected(client, token):
    resp = await client.get("/api/trips", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_the_right_token_is_accepted(client, token):
    resp = await client.get("/api/trips", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_write_endpoints_are_protected_too(client, token):
    """The expensive half: 15 write endpoints that can create and delete data."""
    assert (await client.post("/api/conversations")).status_code == 401


@pytest.mark.asyncio
async def test_health_stays_public(client, token):
    """A platform health check has no credentials to offer."""
    assert (await client.get("/health")).status_code == 200


@pytest.mark.asyncio
async def test_token_can_arrive_by_query_string(client, token):
    """EventSource cannot set headers and the chat endpoint streams over SSE."""
    resp = await client.get(f"/api/trips?token={token}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cors_preflight_is_not_blocked(client, token):
    """Preflight carries no Authorization header by design. Rejecting it breaks the
    browser before the real request is ever sent."""
    resp = await client.request("OPTIONS", "/api/trips", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_a_401_still_carries_cors_headers(client, token):
    """Auth is added before CORS so CORS wraps it. Otherwise the browser sees an
    opaque network error rather than a 401, which is undebuggable from the client."""
    resp = await client.get("/api/trips", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 401
    assert "access-control-allow-origin" in resp.headers


@pytest.mark.asyncio
async def test_auth_is_off_by_default(client):
    """No VOYAGER_AUTH_TOKEN means local development and the test suite are
    unaffected. Failing open is why startup logs a warning."""
    assert (await client.get("/api/trips")).status_code == 200


def test_comparison_is_constant_time():
    """A plain == leaks the token's length and prefix through timing."""
    import inspect
    from app import auth

    assert "compare_digest" in inspect.getsource(auth.resolve_principal)


def test_blank_token_counts_as_disabled(monkeypatch):
    """An empty env var is a common deployment slip -- it must not mean "accept the
    empty string as a valid token"."""
    from app import auth

    monkeypatch.setenv("VOYAGER_AUTH_TOKEN", "   ")
    assert auth.auth_token() is None
