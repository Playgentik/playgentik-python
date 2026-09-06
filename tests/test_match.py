from playgentik.match import Match
from playgentik.players import RandomPlayer


class FakeMcp:
    """Stands in for McpSession inside a Match, scripted with a fixed
    sequence of get_state() results so play() can be tested without any
    real polling delay."""

    def __init__(self, state_sequence, valid_moves, result, move_history_sequence=None):
        self._states = list(state_sequence)
        self._valid_moves = valid_moves
        self._result = result
        self.moves_submitted = []
        # One list per get_move_history() call, in order - keeps returning
        # the last one once exhausted (same "hold the last value" rule as
        # get_state() below). None (the default) means "no move history in
        # this test" - every call just returns [].
        self._history_sequence = list(move_history_sequence) if move_history_sequence is not None else None
        self._last_history: list = []

    def get_guidelines(self):
        return {"rules": "...", "stateShape": "...", "moveShape": "...", "notes": "..."}

    def get_state(self):
        # Keep returning the last state once exhausted.
        return self._states.pop(0) if len(self._states) > 1 else self._states[0]

    def list_valid_moves(self):
        return self._valid_moves

    def make_move(self, move):
        self.moves_submitted.append(move)
        return {}

    def get_result(self):
        return self._result

    def get_move_history(self):
        if self._history_sequence is None:
            return []
        if self._history_sequence:
            self._last_history = self._history_sequence.pop(0)
        return self._last_history


def _state(status, is_your_turn):
    return {
        "matchId": "m1",
        "gameType": "TIC_TAC_TOE",
        "status": status,
        "yourPlayerIndex": 0,
        "isYourTurn": is_your_turn,
        "state": {"board": [None] * 9},
    }


def test_play_submits_one_move_then_returns_result_on_completion():
    valid_moves = [{"position": 0}, {"position": 1}]
    states = [
        _state("IN_PROGRESS", True),
        _state("COMPLETED", False),
    ]
    result_payload = {"finished": True, "winner": 0, "isDraw": False, "winnerIsYou": True}

    match = Match.__new__(Match)  # bypass __init__'s real McpSession construction
    match.connect_url = "https://x/mcp/sessions/tok"
    match.match_id = "m1"
    match._mcp = FakeMcp(states, valid_moves, result_payload)
    match._guidelines = None
    match._last_state = None
    match._result = None

    seen_moves = []
    result = match.play(RandomPlayer(), poll_interval=0, on_move=lambda n, m: seen_moves.append(m))

    assert result == result_payload
    assert len(match._mcp.moves_submitted) == 1
    assert match._mcp.moves_submitted[0] in valid_moves
    assert seen_moves == match._mcp.moves_submitted


def test_play_accepts_plain_callable_strategy():
    valid_moves = [{"position": 3}]
    states = [_state("IN_PROGRESS", True), _state("COMPLETED", False)]
    result_payload = {"finished": True, "winner": None, "isDraw": True, "winnerIsYou": None}

    match = Match.__new__(Match)
    match.connect_url = "https://x/mcp/sessions/tok"
    match.match_id = "m1"
    match._mcp = FakeMcp(states, valid_moves, result_payload)
    match._guidelines = None
    match._last_state = None
    match._result = None

    def always_first_move(state, moves):
        return moves[0]

    result = match.play(always_first_move, poll_interval=0)

    assert result["isDraw"] is True
    assert match._mcp.moves_submitted == [{"position": 3}]


def test_play_waits_out_open_status_until_opponent_joins():
    valid_moves = [{"position": 0}]
    states = [
        _state("OPEN", False),
        _state("OPEN", False),
        _state("IN_PROGRESS", True),
        _state("COMPLETED", False),
    ]
    result_payload = {"finished": True, "winner": 0, "isDraw": False, "winnerIsYou": True}

    match = Match.__new__(Match)
    match.connect_url = "https://x/mcp/sessions/tok"
    match.match_id = "m1"
    match._mcp = FakeMcp(states, valid_moves, result_payload)
    match._guidelines = None
    match._last_state = None
    match._result = None

    statuses_seen = []
    result = match.play(RandomPlayer(), poll_interval=0, on_status_change=statuses_seen.append)

    assert statuses_seen == ["OPEN", "IN_PROGRESS", "COMPLETED"]
    assert result == result_payload


def test_play_fires_on_opponent_move_as_soon_as_it_appears():
    valid_moves = [{"position": 4}]
    states = [
        _state("IN_PROGRESS", False),  # waiting for the opponent's move
        _state("IN_PROGRESS", True),  # they moved - now it's our turn
        _state("COMPLETED", False),
    ]
    opponent_move = {"moveNumber": 1, "playerIndex": 1, "move": {"position": 0}}
    history_sequence = [
        [],  # nothing yet, while waiting
        [opponent_move],  # visible the moment it's our turn - not later
    ]
    result_payload = {"finished": True, "winner": None, "isDraw": False, "winnerIsYou": None}

    match = Match.__new__(Match)
    match.connect_url = "https://x/mcp/sessions/tok"
    match.match_id = "m1"
    match._mcp = FakeMcp(states, valid_moves, result_payload, move_history_sequence=history_sequence)
    match._guidelines = None
    match._last_state = None
    match._result = None

    seen = []
    result = match.play(RandomPlayer(), poll_interval=0, on_opponent_move=lambda idx, move: seen.append((idx, move)))

    assert seen == [(1, opponent_move)]
    assert match.opponent_last_move == opponent_move
    assert result == result_payload


def test_refresh_opponent_last_move_works_without_play():
    match = Match.__new__(Match)
    match.connect_url = "https://x/mcp/sessions/tok"
    match.match_id = "m1"
    opponent_move = {"moveNumber": 3, "playerIndex": 1, "move": {"position": 5}}
    match._mcp = FakeMcp(
        [_state("IN_PROGRESS", False)],
        valid_moves=[],
        result=None,
        move_history_sequence=[[opponent_move]],
    )
    match._guidelines = None
    match._last_state = None
    match._result = None

    assert match.opponent_last_move is None

    latest = match.refresh_opponent_last_move()

    assert latest == opponent_move
    assert match.opponent_last_move == opponent_move
