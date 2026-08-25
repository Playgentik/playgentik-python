from typing import Any

from app.games.guidelines import get_guidelines as _get_guidelines
from app.games.registry import get_engine
from app.matches.errors import MatchActionError
from app.matches.service import apply_player_move
from app.models import Match, MatchMove

MOVE_SCHEMAS: dict[str, dict] = {
    "TIC_TAC_TOE": {
        "type": "object",
        "properties": {"position": {"type": "integer", "minimum": 0, "maximum": 8}},
        "required": ["position"],
    },
    "CONNECT_FOUR": {
        "type": "object",
        "properties": {"column": {"type": "integer", "minimum": 0, "maximum": 6}},
        "required": ["column"],
    },
    "ROCK_PAPER_SCISSORS": {
        "type": "object",
        "properties": {"choice": {"type": "string", "enum": ["rock", "paper", "scissors"]}},
        "required": ["choice"],
    },
    "TETRIS": {
        "type": "object",
        "description": "Copy one of the objects returned by list_valid_moves verbatim.",
        "properties": {
            "rotation": {"type": "integer"},
            "column": {"type": "integer"},
            "cells": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
        },
        "required": ["rotation", "column", "cells"],
    },
    "CHESS": {
        "type": "object",
        "description": "Copy one of the objects returned by list_valid_moves verbatim.",
        "properties": {
            "from": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
            "to": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
            "promotion": {"type": ["string", "null"], "enum": ["Q", "R", "B", "N", None]},
        },
        "required": ["from", "to", "promotion"],
    },
    "CHECKERS": {
        "type": "object",
        "description": "Copy one of the objects returned by list_valid_moves verbatim.",
        "properties": {
            "from": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
            "to": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
        },
        "required": ["from", "to"],
    },
    "GO": {
        "type": "object",
        "description": "Either {\"pass\": true} or a {\"row\", \"col\"} placement from list_valid_moves.",
        "properties": {
            "pass": {"type": "boolean"},
            "row": {"type": "integer", "minimum": 0, "maximum": 8},
            "col": {"type": "integer", "minimum": 0, "maximum": 8},
        },
    },
    "REVERSI": {
        "type": "object",
        "properties": {
            "row": {"type": "integer", "minimum": 0, "maximum": 7},
            "col": {"type": "integer", "minimum": 0, "maximum": 7},
        },
        "required": ["row", "col"],
    },
    "TEXAS_HOLDEM": {
        "type": "object",
        "description": (
            "{action: 'fold'|'check'|'call'} or {action: 'raise', amount: int} where amount is "
            "the new total committed this street. list_valid_moves offers a min-raise and an "
            "all-in size as examples; any structurally valid amount in between is also accepted."
        ),
        "properties": {
            "action": {"type": "string", "enum": ["fold", "check", "call", "raise"]},
            "amount": {"type": "integer"},
        },
        "required": ["action"],
    },
    "BATTLESHIP": {
        "type": "object",
        "description": (
            "During PLACEMENT: {ships: [{cells: [[row,col],...]}, ...]} - 5 ships matching the "
            "sizes from list_valid_moves, each a contiguous straight line, no overlaps. "
            "During BATTLE: {row: int, col: int} from list_valid_moves."
        ),
        "properties": {
            "ships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "cells": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
                    },
                    "required": ["cells"],
                },
            },
            "row": {"type": "integer", "minimum": 0, "maximum": 9},
            "col": {"type": "integer", "minimum": 0, "maximum": 9},
        },
    },
}


def tool_definitions(game_type: str) -> list[dict]:
    empty_schema = {"type": "object", "properties": {}}
    return [
        {
            "name": "get_guidelines",
            "description": "Get this game's rules and the JSON shape of its state and moves.",
            "inputSchema": empty_schema,
        },
        {
            "name": "get_state",
            "description": "Get the current match state, whether it's your turn, and the winner if finished.",
            "inputSchema": empty_schema,
        },
        {
            "name": "get_move_history",
            "description": (
                "Get every move made so far in this match (both players, oldest first) - use this "
                "as memory of how the game has unfolded rather than deciding from the current "
                "state alone."
            ),
            "inputSchema": empty_schema,
        },
        {
            "name": "list_valid_moves",
            "description": "List the moves you may currently submit. Empty if it isn't your turn.",
            "inputSchema": empty_schema,
        },
        {
            "name": "make_move",
            "description": "Submit a move. Must be exactly one of the moves list_valid_moves returned.",
            "inputSchema": {
                "type": "object",
                "properties": {"move": MOVE_SCHEMAS[game_type]},
                "required": ["move"],
            },
        },
        {
            "name": "get_result",
            "description": "Get the final result. finished is false until the match ends.",
            "inputSchema": empty_schema,
        },
    ]


def _state_view(match: Match, player_index: int) -> dict:
    engine = get_engine(match.game_type.value)
    awaiting = engine.awaiting_players(match.current_state)
    return {
        "matchId": match.id,
        "gameType": match.game_type.value,
        "status": match.status.value,
        "yourPlayerIndex": player_index,
        "isYourTurn": player_index in awaiting,
        "isDraw": match.is_draw,
        "winnerPlayerIndex": match.winner_player_index,
        "state": engine.public_state(match.current_state, viewer=player_index),
    }


def call_tool(match: Match, player_index: int, name: str, arguments: dict[str, Any]) -> dict:
    engine = get_engine(match.game_type.value)

    if name == "get_guidelines":
        return _get_guidelines(match.game_type.value)

    if name == "get_state":
        return _state_view(match, player_index)

    if name == "get_move_history":
        moves = MatchMove.query.filter_by(match_id=match.id).order_by(MatchMove.move_number).all()
        return {
            "moves": [
                {"moveNumber": m.move_number, "playerIndex": m.player_index, "move": m.move.get("action")}
                for m in moves
            ]
        }

    if name == "list_valid_moves":
        awaiting = engine.awaiting_players(match.current_state)
        is_turn = player_index in awaiting
        valid = engine.get_valid_moves(match.current_state, player_index) if is_turn else []
        return {"isYourTurn": is_turn, "validMoves": valid}

    if name == "make_move":
        move = arguments.get("move")
        if not isinstance(move, dict):
            raise MatchActionError("move must be an object")
        result = apply_player_move(match, player_index, move)
        return {**_state_view(match, player_index), "result": result}

    if name == "get_result":
        result = engine.get_result(match.current_state)
        winner_is_you = (
            result["winner"] == player_index if result["finished"] and not result["isDraw"] else None
        )
        return {**result, "winnerIsYou": winner_is_you}

    raise MatchActionError(f"Unknown tool: {name}")
