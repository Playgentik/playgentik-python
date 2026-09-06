import pytest

from playgentik.exceptions import ApiError
from playgentik.rest import RestClient

from conftest import FakeResponse, FakeSession


def test_login_success_stores_token():
    session = FakeSession(responses=[FakeResponse(200, {"token": "jwt123"})])
    rest = RestClient("https://x", session=session)

    token = rest.login("alice", "secret")

    assert token == "jwt123"
    assert rest.token == "jwt123"
    assert session.calls[0]["url"] == "https://x/api/auth/login"


def test_register_or_login_falls_back_to_register_on_login_failure():
    session = FakeSession(responses=[
        FakeResponse(401, {"error": "bad credentials"}, text="bad credentials"),  # login fails
        FakeResponse(201, {"token": "new-jwt"}),  # register succeeds
    ])
    rest = RestClient("https://x", session=session)

    token = rest.register_or_login("a@example.com", "alice", "secret")

    assert token == "new-jwt"
    assert session.calls[0]["url"] == "https://x/api/auth/login"
    assert session.calls[1]["url"] == "https://x/api/auth/register"


def test_create_preview_requires_auth_first():
    rest = RestClient("https://x", session=FakeSession())
    with pytest.raises(ApiError, match="Not authenticated"):
        rest.create_preview("TIC_TAC_TOE")


def test_api_key_authenticates_rest_calls_with_no_login_call_at_all():
    session = FakeSession(responses=[FakeResponse(200, {"match": {"id": "m1", "participants": []}})])
    rest = RestClient("https://x", api_key="pk_live_abc123", session=session)

    match = rest.create_preview("TIC_TAC_TOE")

    assert match["id"] == "m1"
    assert len(session.calls) == 1  # no separate login request
    assert session.calls[0]["headers"] == {"Authorization": "Bearer pk_live_abc123"}


def test_api_key_wins_over_a_stale_token_if_both_are_set():
    session = FakeSession(responses=[FakeResponse(200, {"match": {"id": "m1", "participants": []}})])
    rest = RestClient("https://x", api_key="pk_live_abc123", session=session)
    rest.token = "some-old-jwt"

    rest.create_preview("TIC_TAC_TOE")

    assert session.calls[0]["headers"] == {"Authorization": "Bearer pk_live_abc123"}


def test_create_match_sends_opponent_body_and_auth_header():
    session = FakeSession(responses=[
        FakeResponse(200, {"token": "jwt"}),
        FakeResponse(200, {"match": {"id": "m1", "participants": []}}),
    ])
    rest = RestClient("https://x", session=session)
    rest.login("alice", "secret")

    match = rest.create_match("CONNECT_FOUR", "builtin_ai")

    assert match == {"id": "m1", "participants": []}
    call = session.calls[-1]
    assert call["url"] == "https://x/api/games/CONNECT_FOUR/matches"
    assert call["json"] == {"opponent": "builtin_ai"}
    assert call["headers"] == {"Authorization": "Bearer jwt"}


def test_join_queue_falls_back_to_open_match_on_404():
    def handler(method, url, json_body):
        if url.endswith("/queue"):
            return FakeResponse(404, text="no such route")
        assert url.endswith("/matches")
        assert json_body == {"opponent": "open", "stake": 5.0}
        return FakeResponse(200, {"match": {"id": "m2", "participants": []}})

    session = FakeSession(handler=handler)
    rest = RestClient("https://x", session=session)
    rest.token = "jwt"  # skip login for this test

    match = rest.join_queue("TIC_TAC_TOE", stake=5.0)

    assert match["id"] == "m2"


def test_join_queue_uses_dedicated_endpoint_when_present():
    session = FakeSession(responses=[FakeResponse(200, {"match": {"id": "queued-1", "participants": []}})])
    rest = RestClient("https://x", session=session)
    rest.token = "jwt"

    match = rest.join_queue("TIC_TAC_TOE", stake=5.0)

    assert match["id"] == "queued-1"
    assert session.calls[0]["url"] == "https://x/api/games/TIC_TAC_TOE/queue"


def test_connect_url_finds_own_participant_slot():
    match = {
        "participants": [
            {"username": "opponent"},
            {"username": "me", "connectToken": "abc-123"},
        ]
    }
    assert RestClient.connect_url("https://x/", match) == "https://x/mcp/sessions/abc-123"


def test_connect_url_raises_when_no_token_present():
    with pytest.raises(ApiError):
        RestClient.connect_url("https://x", {"participants": [{"username": "opponent"}]})
