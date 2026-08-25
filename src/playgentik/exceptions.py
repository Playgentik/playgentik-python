"""Every error this package raises lives here."""

from __future__ import annotations

from typing import Optional


class PlaygentikError(Exception):
    """Base class for every error raised by this package."""


class ApiError(PlaygentikError):
    """The web app's REST API (auth, match creation/joining) returned an
    error - `str(exc)` includes the server's message when it sent one."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class McpError(PlaygentikError):
    """A match's MCP session endpoint returned a JSON-RPC error, or a tool
    call came back with `isError: true` (e.g. an illegal move)."""


class SessionNotFoundError(McpError):
    """The connect token doesn't exist (HTTP 404)."""


class SessionExpiredError(McpError):
    """The match this connect token belonged to has already finished - the
    token is dead permanently, same as if it had never existed (HTTP 410)."""


class InvalidApiKeyError(McpError):
    """An API key was sent with the request but the server rejected it -
    invalid, revoked, or belonging to a different user than this session's
    participant slot (HTTP 401)."""
