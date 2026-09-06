"""High-level wrapper around one player's connection to one match: the
five MCP tools behind a friendlier surface, plus a `play()` loop that's a
direct port of `play_agent.py`'s `play()` function.
"""

from __future__ import annotations

import time
from typing import Any, Callable, List, Optional, Protocol, runtime_checkable

from .exceptions import McpError
from .mcp import McpSession

FINISHED_STATUSES = ("COMPLETED", "ABORTED")
MAX_HISTORY_MOVES = 20  # matches play_agent.py's MAX_HISTORY_MOVES


@runtime_checkable
class Player(Protocol):
    """What `Match.play()` expects when you don't just hand it a plain
    callable - the same shape as `play_agent.py`'s `RandomPlayer`/
    `GeminiPlayer`, so those drop in unmodified."""

    def choose_move(
        self,
        game_type: str,
        guidelines: dict,
        state: dict,
        valid_moves: List[dict],
        player_index: int,
        move_history: list,
    ) -> dict: ...


# A plain-callable strategy: fn(state, valid_moves) -> move
SimpleStrategyFn = Callable[[dict, List[dict]], dict]


class Match:
    """One player's live view of one match, reached over its connect_token
    MCP endpoint. Get one from `Client.play_practice()`, `.play_ranked_ai()`,
    `.create_open_match()`, `.join_match()`, `.join_queue()`, or directly
    from a connect URL via `Match.from_url()`.
    """

    # Class-level defaults (not just set in __init__) so an instance built
    # via Match.__new__(Match) - the pattern this package's own tests use
    # to swap in a fake McpSession without a real connection - still finds
    # these via normal attribute lookup instead of raising AttributeError
    # the first time play() touches them.
    _player_index: Optional[int] = None
    _opponent_last_move: Optional[dict] = None
    _opponent_last_move_number: Optional[int] = None

    def __init__(self, connect_url: str, *, api_key: Optional[str] = None, match_id: Optional[str] = None):
        self.connect_url = connect_url
        self.match_id = match_id
        self._mcp = McpSession(connect_url, api_key=api_key)
        self._guidelines: Optional[dict] = None
        self._last_state: Optional[dict] = None
        self._result: Optional[dict] = None

    @classmethod
    def from_url(cls, connect_url: str, *, api_key: Optional[str] = None) -> "Match":
        """Connect directly to a connect URL you already have (e.g. copied
        from the app's "My Sessions" page), skipping REST auth entirely -
        equivalent to `play_agent.py --mode url --connect-url ...`."""
        return cls(connect_url, api_key=api_key)

    # -- the five tools, plus get_move_history, behind plain methods -----

    def get_guidelines(self) -> dict:
        """This game's rules and the JSON shape of its state and moves.
        Cached after the first call - guidelines don't change mid-match."""
        if self._guidelines is None:
            self._guidelines = self._mcp.get_guidelines()
        return self._guidelines

    def get_state(self) -> dict:
        """Current match state, whether it's your turn, and the winner if
        finished. `{matchId, gameType, status, yourPlayerIndex, isYourTurn,
        isDraw, winnerPlayerIndex, state}`."""
        self._last_state = self._mcp.get_state()
        player_index = self._last_state.get("yourPlayerIndex")
        if player_index is not None:
            self._player_index = player_index
        return self._last_state

    def list_valid_moves(self) -> List[dict]:
        """Moves you may submit right now - `[]` if it isn't your turn."""
        return self._mcp.list_valid_moves()

    def submit_move(self, move: dict) -> dict:
        """Submit one of the moves `list_valid_moves()` returned. Must
        match one verbatim - copy it, don't reconstruct it by hand."""
        return self._mcp.make_move(move)

    def get_result(self) -> dict:
        """Final outcome. `finished` is `False` until the match ends."""
        self._result = self._mcp.get_result()
        return self._result

    def get_move_history(self, limit: Optional[int] = None) -> List[dict]:
        """Every move made so far (both players, oldest first): `[{move
        Number, playerIndex, move}]`. Pass `limit` to keep only the most
        recent N, e.g. for feeding a model's context window."""
        moves = self._mcp.get_move_history()
        return moves[-limit:] if limit else moves

    # -- opponent's last move ------------------------------------------------

    @property
    def opponent_last_move(self) -> Optional[dict]:
        """The most recent move the *other* player made - `{moveNumber,
        playerIndex, move}`, or `None` before they've moved yet. Kept
        current automatically while `play()` is running (it now checks for
        a new opponent move every loop iteration, not just right before
        your own turn - see `on_opponent_move` below for a callback
        instead of polling this). Driving your own loop instead of
        `play()`? Call `refresh_opponent_last_move()` each time round it."""
        return self._opponent_last_move

    def refresh_opponent_last_move(self) -> Optional[dict]:
        """Fetches the move history and updates/returns `opponent_last_move`
        from it. `play()` already does this every iteration; call this
        yourself only if you're polling `get_state()`/`list_valid_moves()`
        by hand instead of using `play()`."""
        if self._player_index is None:
            self.get_state()
        return self._note_opponent_move(self.get_move_history())

    def _note_opponent_move(
        self, history: List[dict], on_opponent_move: Optional[Callable[[int, dict], None]] = None
    ) -> Optional[dict]:
        latest = None
        for entry in reversed(history):
            if entry.get("playerIndex") != self._player_index:
                latest = entry
                break
        if latest is None or latest.get("moveNumber") == self._opponent_last_move_number:
            return self._opponent_last_move
        self._opponent_last_move = latest
        self._opponent_last_move_number = latest.get("moveNumber")
        if on_opponent_move:
            on_opponent_move(latest["playerIndex"], latest)
        return self._opponent_last_move

    # -- convenience --------------------------------------------------------

    @property
    def result(self) -> Optional[dict]:
        """The last `get_result()` payload, if one has been fetched (`play()`
        populates this when the match ends). `None` until then."""
        return self._result

    @property
    def finished(self) -> bool:
        """Re-fetches state. For a tight loop, read `status` off
        `get_state()` yourself instead of polling this repeatedly."""
        state = self.get_state()
        return state["status"] in FINISHED_STATUSES

    def play(
        self,
        strategy: Any,
        *,
        max_moves: int = 300,
        poll_interval: float = 2.0,
        on_status_change: Optional[Callable[[str], None]] = None,
        on_move: Optional[Callable[[int, dict], None]] = None,
        on_opponent_move: Optional[Callable[[int, dict], None]] = None,
    ) -> dict:
        """Run this match to completion, calling `strategy` for each of our
        turns. A direct port of `play_agent.py`'s `play()` loop: poll
        `get_state()`, wait out `OPEN`/not-our-turn/no-valid-moves, choose
        and submit a move on our turn, repeat until `COMPLETED`/`ABORTED`.

        `strategy` may be:
          - a `Player`-shaped object: `.choose_move(game_type, guidelines,
            state, valid_moves, player_index, move_history)`
          - a plain callable: `fn(state, valid_moves) -> move`

        `on_opponent_move(player_index, move)` fires the moment a new move
        from the *other* player shows up in the match's history - checked
        every loop iteration, including while waiting for their turn, not
        only right before yours. Also available without a callback via the
        `opponent_last_move` property, updated the same way. Both reflect
        `get_move_history()`, so they see a move the instant it's recorded
        server-side - no separate polling of your own needed.

        Returns the final `get_result()` payload. Raises `McpError` if
        `max_moves` is hit first (a safety cap against a runaway/stuck
        loop, not expected in normal play).
        """
        choose = _adapt_strategy(strategy)
        guidelines = self.get_guidelines()
        moves_made = 0
        last_status = None

        while moves_made < max_moves:
            state_view = self.get_state()
            status = state_view["status"]

            if status != last_status:
                last_status = status
                if on_status_change:
                    on_status_change(status)

            if status in FINISHED_STATUSES:
                return self.get_result()

            if status == "OPEN":
                time.sleep(poll_interval)
                continue

            # Fetched (and opponent_last_move refreshed from it) every
            # iteration from here on, whether or not it's currently your
            # turn - so on_opponent_move/opponent_last_move reflect a new
            # opponent move as soon as it's visible, not just once it's
            # your turn again.
            move_history = self.get_move_history(limit=MAX_HISTORY_MOVES)
            self._note_opponent_move(move_history, on_opponent_move)

            if not state_view["isYourTurn"]:
                time.sleep(poll_interval)
                continue

            valid_moves = self.list_valid_moves()
            if not valid_moves:
                time.sleep(poll_interval)
                continue

            move = choose(guidelines, state_view, valid_moves, move_history)
            self.submit_move(move)
            moves_made += 1
            if on_move:
                on_move(moves_made, move)

        raise McpError(f"Stopped after reaching the {max_moves}-move safety cap without the match finishing.")

    # -- housekeeping ---------------------------------------------------

    def close(self) -> None:
        self._mcp.close()

    def __enter__(self) -> "Match":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Match(match_id={self.match_id!r}, connect_url={self.connect_url!r})"


def _adapt_strategy(strategy: Any) -> Callable[[dict, dict, List[dict], list], dict]:
    if hasattr(strategy, "choose_move"):

        def choose(guidelines: dict, state_view: dict, valid_moves: List[dict], move_history: list) -> dict:
            return strategy.choose_move(
                state_view["gameType"],
                guidelines,
                state_view["state"],
                valid_moves,
                state_view["yourPlayerIndex"],
                move_history,
            )

        return choose

    def choose(guidelines: dict, state_view: dict, valid_moves: List[dict], move_history: list) -> dict:
        return strategy(state_view["state"], valid_moves)

    return choose
