import json

import pytest

from playgentik.exceptions import InvalidApiKeyError, McpError, SessionExpiredError, SessionNotFoundError
from playgentik.mcp import McpSession

from conftest import FakeResponse, FakeSession


def _tool_call_response(payload, is_error=False):
    return FakeResponse(
        200,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": is_error},
        },
    )


def test_call_tool_auto_initializes_then_returns_decoded_payload():
    init_resp = FakeResponse(200, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}})
    state_resp = _tool_call_response({"matchId": "m1", "status": "IN_PROGRESS", "isYourTurn": True})
    session = FakeSession(responses=[init_resp, state_resp])

    mcp = McpSession("https://x/mcp/sessions/tok", session=session)
    result = mcp.get_state()

    assert result == {"matchId": "m1", "status": "IN_PROGRESS", "isYourTurn": True}
    assert mcp._initialized is True
    # initialize happened first, tools/call second
    assert session.calls[0]["json"]["method"] == "initialize"
    assert session.calls[1]["json"]["method"] == "tools/call"
    assert session.calls[1]["json"]["params"]["name"] == "get_state"


def test_call_tool_raises_on_is_error():
    session = FakeSession(responses=[
        FakeResponse(200, {"jsonrpc": "2.0", "id": 1, "result": {}}),  # initialize
        _tool_call_response("not your turn", is_error=True),
    ])
    mcp = McpSession("https://x/mcp/sessions/tok", session=session)

    with pytest.raises(McpError, match="not your turn"):
        mcp.call_tool("make_move", {"move": {"position": 0}})


def test_jsonrpc_level_error_raises_mcperror():
    session = FakeSession(responses=[
        FakeResponse(200, {"jsonrpc": "2.0", "id": 1, "result": {}}),  # initialize
        FakeResponse(200, {"jsonrpc": "2.0", "id": 2, "error": {"code": -32601, "message": "Method not found"}}),
    ])
    mcp = McpSession("https://x/mcp/sessions/tok", session=session)

    with pytest.raises(McpError, match="Method not found"):
        mcp.call_tool("bogus_tool")


@pytest.mark.parametrize(
    "status_code,exc_cls",
    [(404, SessionNotFoundError), (410, SessionExpiredError), (401, InvalidApiKeyError)],
)
def test_http_status_codes_map_to_specific_exceptions(status_code, exc_cls):
    session = FakeSession(responses=[FakeResponse(status_code, {}, text="nope")])
    mcp = McpSession("https://x/mcp/sessions/tok", session=session)

    with pytest.raises(exc_cls):
        mcp.get_state()


def test_api_key_sets_bearer_header():
    session = FakeSession()
    McpSession("https://x/mcp/sessions/tok", api_key="pk_live_abc", session=session)
    assert session.headers["Authorization"] == "Bearer pk_live_abc"


def test_get_move_history_and_list_valid_moves_unwrap_result():
    session = FakeSession(responses=[
        FakeResponse(200, {"jsonrpc": "2.0", "id": 1, "result": {}}),  # initialize
        _tool_call_response({"moves": [{"moveNumber": 1, "playerIndex": 0, "move": {"position": 4}}]}),
    ])
    mcp = McpSession("https://x/mcp/sessions/tok", session=session)
    assert mcp.get_move_history() == [{"moveNumber": 1, "playerIndex": 0, "move": {"position": 4}}]
