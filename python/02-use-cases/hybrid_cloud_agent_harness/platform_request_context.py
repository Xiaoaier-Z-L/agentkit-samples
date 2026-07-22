"""Request-scoped credentials used by platform component adapters.

AgentKit authenticates a public ``/invoke`` request with an ``Authorization``
header.  The Knowledge service accepts the same bearer credential, but VeADK
tools run after the HTTP handler has handed the request to the agent runner.
Keeping the value in a :class:`contextvars.ContextVar` makes it available to a
tool call without storing a per-user credential on the Agent or in an
environment variable.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import os
from typing import Callable


_request_authorization: ContextVar[str] = ContextVar("agentkit_request_authorization", default="")
_request_identity: ContextVar["GatewayIdentity | None"] = ContextVar(
    "agentkit_request_identity", default=None
)


@dataclass(frozen=True, slots=True)
class GatewayIdentity:
    tenant_id: str
    user_id: str
    session_id: str
    source: str


def request_authorization() -> str:
    """Return the current request Authorization header, never logging it."""
    return _request_authorization.get()


def request_identity() -> GatewayIdentity | None:
    """Return gateway-bound identity, or ``None`` outside an HTTP request."""
    return _request_identity.get()


class RequestAuthorizationMiddleware:
    """Bind inbound credential and identity headers to this request only."""

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers: dict[str, str] = {}
        for key, value in scope.get("headers", []):
            headers[key.decode("latin-1").lower()] = value.decode("latin-1")

        authorization = headers.get("authorization", "")
        identity = GatewayIdentity(
            tenant_id=(
                headers.get("tenant_id")
                or headers.get("x-tenant-id")
                or os.getenv("HARNESS_TENANT_ID", "")
            ),
            user_id=headers.get("user_id") or headers.get("x-user-id", ""),
            session_id=headers.get("session_id") or headers.get("x-session-id", ""),
            source="gateway-bearer" if authorization else "gateway-request",
        )

        authorization_token = _request_authorization.set(authorization)
        identity_token = _request_identity.set(identity)
        try:
            await self.app(scope, receive, send)
        finally:
            _request_identity.reset(identity_token)
            _request_authorization.reset(authorization_token)
