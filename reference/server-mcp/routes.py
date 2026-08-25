from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app.apikeys.service import authenticate as authenticate_api_key
from app.errors import ApiError
from app.extensions import db
from app.mcp.protocol import handle_request
from app.models import ControlMode, MatchParticipant, MatchStatus

mcp_bp = Blueprint("mcp", __name__, url_prefix="/mcp")

FINISHED_STATUSES = (MatchStatus.COMPLETED, MatchStatus.ABORTED)


@mcp_bp.post("/sessions/<connect_token>")
def mcp_session(connect_token: str):
    participant = MatchParticipant.query.filter_by(
        connect_token=connect_token, control=ControlMode.MCP
    ).first()
    if participant is None:
        raise ApiError(404, "Unknown or invalid session token")

    # A match's connect_token is only ever valid while the match can still
    # be played - once it's finished (completed or aborted) the token is
    # dead permanently, the same as if it never existed. Without this, a
    # leaked/logged connect URL from a finished match would stay callable
    # forever.
    if participant.match.status in FINISHED_STATUSES:
        raise ApiError(410, "This match has ended - the connect URL is no longer active")

    # The connect_token is already a per-match secret, so an API key isn't
    # required yet - but if the agent sends one (Authorization: Bearer
    # pk_live_...), it must be valid, unrevoked, and belong to the same
    # user who owns this participant slot. This lets a user revoke a
    # compromised key across every match at once, and is the hook point
    # for making keys mandatory later without changing this contract.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw_key = auth_header[len("Bearer ") :]
        key_record = authenticate_api_key(raw_key)
        if key_record is None or key_record.user_id != participant.user_id:
            raise ApiError(401, "Invalid or revoked API key")

    now = datetime.now(timezone.utc)
    if participant.connected_at is None:
        participant.connected_at = now
    participant.last_seen_at = now
    db.session.commit()

    body = request.get_json(silent=True)
    response_body, status = handle_request(body, participant.match, participant)

    if response_body is None:
        return "", status
    return jsonify(response_body), status
