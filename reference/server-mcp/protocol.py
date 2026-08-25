"""A minimal, spec-following implementation of MCP's Streamable HTTP
transport: JSON-RPC 2.0 over a single POST endpoint, one request per
response (no SSE streaming, no resources/prompts). This covers exactly
what's needed to let an external agent discover and call this session's
tools - see Guidelines in the app for the exact wire format.
"""

import json
import logging

from app.extensions import db
from app.mcp.tools import call_tool, tool_definitions
from app.matches.errors import MatchActionError
from app.models import Match, MatchParticipant

PROTOCOL_VERSION = "2025-06-18"
logger = logging.getLogger(__name__)


def handle_request(body, match: Match, participant: MatchParticipant) -> tuple[dict | None, int]:
    """Returns (response_json_or_None, http_status). None means no body
    (JSON-RPC notifications get no response per spec)."""
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0" or "method" not in body:
        msg_id = body.get("id") if isinstance(body, dict) else None
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32600, "message": "Invalid Request"}}, 400

    method = body["method"]
    params = body.get("params") or {}
    msg_id = body.get("id")
    is_notification = "id" not in body

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": f"playgentik-{match.game_type.value.lower()}",
                "version": "1.0.0",
            },
        }
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}, 200

    if method == "notifications/initialized":
        return None, 202

    if method == "ping":
        if is_notification:
            return None, 202
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}, 200

    if method == "tools/list":
        result = {"tools": tool_definitions(match.game_type.value)}
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}, 200

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            tool_result = call_tool(match, participant.player_index, name, arguments)
            result = {"content": [{"type": "text", "text": json.dumps(tool_result)}], "isError": False}
        except MatchActionError as exc:
            db.session.rollback()
            result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        except Exception:
            db.session.rollback()
            logger.exception("Unexpected error handling tools/call name=%r", name)
            result = {"content": [{"type": "text", "text": "Internal error handling tool call"}], "isError": True}
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}, 200

    if is_notification:
        return None, 202

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }, 200
