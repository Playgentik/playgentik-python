"""A minimal JSON-RPC 2.0 client for one match's MCP connect-token endpoint.

Mirrors `server/app/mcp/protocol.py` exactly: a single JSON-RPC request per
POST, one JSON response per request (no SSE, no resources/prompts) - just
enough of the Streamable HTTP transport to discover and call this session's
five tools.
"""

from __future__ import annotations

import json
from typing import Any, List, Optional

import requests

from .exceptions import InvalidApiKeyError, McpError, SessionExpiredError, SessionNotFoundError

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "playgentik-python", "version": "0.1.0"}
DEFAULT_TIMEOUT = 30.0


class McpSession:
    """Low-level JSON-RPC client for a single connect_token URL
    (`<base_url>/mcp/sessions/<connect_token>`).

    One `McpSession` = one player's connection to one match. It's cheap and
    stateless server-side (the connect_token itself is the only state), so
    there's nothing to "close" beyond the underlying HTTP connection pool.
    """

    def __init__(
        self,
        connect_url: str,
        *,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        session: Optional[requests.Session] = None,
    ):
        self.connect_url = connect_url
        self.timeout = timeout
        self._next_id = 1
        self._initialized = False
        self._http = session or requests.Session()
        if api_key:
            # Optional: a persistent platform API key (pk_live_...) that
            # this connect_token's owner also holds. Not required - the
            # connect_token alone is already a valid per-match credential -
            # but lets you revoke this agent's access instantly across
            # every match at once if the key ever leaks.
            self._http.headers["Authorization"] = f"Bearer {api_key}"

    # -- JSON-RPC plumbing --------------------------------------------------

    def _rpc(self, method: str, params: Optional[dict] = None) -> Any:
        body: dict = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            body["params"] = params
        self._next_id += 1

        resp = self._http.post(self.connect_url, json=body, timeout=self.timeout)
        if resp.status_code == 404:
            raise SessionNotFoundError("Unknown or invalid connect token - check the connect URL.")
        if resp.status_code == 410:
            raise SessionExpiredError("This match has ended - the connect URL is no longer active.")
        if resp.status_code == 401:
            raise InvalidApiKeyError("Invalid or revoked API key for this session's participant.")
        resp.raise_for_status()

        data = resp.json()
        if "error" in data:
            err = data["error"]
            raise McpError(f"{method}: {err.get('message', err)}")
        return data["result"]

    def initialize(self) -> dict:
        """Perform the MCP handshake. Called automatically before the first
        tool call if you haven't called it yourself."""
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        self._initialized = True
        return result

    def ping(self) -> dict:
        return self._rpc("ping")

    def list_tools(self) -> List[dict]:
        return self._rpc("tools/list")["tools"]

    def call_tool(self, name: str, arguments: Optional[dict] = None) -> Any:
        if not self._initialized:
            self.initialize()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        text = result["content"][0]["text"]
        if result.get("isError"):
            raise McpError(f"{name}: {text}")
        return json.loads(text)

    # -- typed wrappers around the five tools every session exposes --------

    def get_guidelines(self) -> dict:
        return self.call_tool("get_guidelines")

    def get_state(self) -> dict:
        return self.call_tool("get_state")

    def get_move_history(self) -> List[dict]:
        return self.call_tool("get_move_history")["moves"]

    def list_valid_moves(self) -> List[dict]:
        return self.call_tool("list_valid_moves")["validMoves"]

    def make_move(self, move: dict) -> dict:
        return self.call_tool("make_move", {"move": move})

    def get_result(self) -> dict:
        return self.call_tool("get_result")

    # -- housekeeping ---------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "McpSession":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"McpSession({self.connect_url!r})"
