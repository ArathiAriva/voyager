"""Request authentication.

**This is a lock, not an identity system.** Voyager is single-tenant by
construction -- there is no user model, and profile isolation is process-level
(`run.sh --profile` sets `DATABASE_URL`/`CHROMA_PATH` for the whole process). A
shared token is the honest fit for that: it stops strangers from spending the
deployment's OpenRouter credit and from reaching the 15 write endpoints, which is
the actual threat when the app is on the public internet.

It is deliberately *not* a step toward multi-user. That needs `user_id` on every
table, `user_id` in Chroma metadata with every query filtering on it, and
request-scoped sessions replacing the import-time singleton -- see the memory
analysis, which flags process-level isolation as failing silently the moment one
process serves two users. Adding a login screen in front of a single-tenant app
would look multi-user while pooling everyone's data, which is worse than no login.

What *is* forward-looking is the shape: everything resolves a `Principal` from one
function. Today that is the shared token yielding "owner"; later it can be a JWT
yielding a real user id, and the call sites do not change.

Disabled when `VOYAGER_AUTH_TOKEN` is unset, so local development and the test
suite are unaffected. That default is deliberate -- a deployment that forgets the
variable fails open, so `scripts/run.sh` warns rather than silently trusting it.
"""

from __future__ import annotations

import hmac
import logging
import os
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("voyager.auth")

#: Paths reachable without a token. `/health` so a platform health check does not
#: need credentials, and the OpenAPI routes so the docs stay usable locally.
PUBLIC_PATHS = frozenset({"/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"})


@dataclass(frozen=True)
class Principal:
    """Who is making this request.

    One field today. It exists so call sites that will eventually need a user id
    already read from a single place -- see the module docstring.
    """

    id: str


OWNER = Principal(id="owner")


def auth_token() -> str | None:
    """The configured shared token, or None when auth is disabled."""
    token = os.environ.get("VOYAGER_AUTH_TOKEN", "").strip()
    return token or None


def _presented_token(request: Request) -> str | None:
    """Token from the Authorization header, or the query string for SSE.

    EventSource cannot set headers, and the chat endpoint streams over SSE. The
    frontend uses fetch-based streaming so the header works there, but the query
    fallback keeps plain EventSource clients and manual curl testing usable.
    Query strings land in server logs, so the header is preferred where possible.
    """
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return request.query_params.get("token") or None


def resolve_principal(request: Request) -> Principal | None:
    """Identify the caller, or None if the token is missing or wrong.

    Returns OWNER when auth is disabled, so downstream code never has to special-case
    the unauthenticated development path.
    """
    expected = auth_token()
    if expected is None:
        return OWNER
    presented = _presented_token(request)
    if presented is None:
        return None
    # Constant-time: a plain `==` leaks the token's length and prefix through
    # timing. Cheap to do correctly, so there is no reason not to.
    return OWNER if hmac.compare_digest(presented, expected) else None


async def auth_middleware(request: Request, call_next):
    """Reject unauthenticated requests before they reach a route.

    Middleware rather than a per-route dependency: 15 write endpoints and growing,
    and a route added later would silently be unprotected if this were opt-in.
    """
    if auth_token() is None:
        request.state.principal = OWNER
        return await call_next(request)

    # CORS preflight carries no Authorization header by design; rejecting it would
    # break the browser before the real request is ever sent.
    if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    principal = resolve_principal(request)
    if principal is None:
        logger.warning("auth | rejected %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    request.state.principal = principal
    return await call_next(request)
