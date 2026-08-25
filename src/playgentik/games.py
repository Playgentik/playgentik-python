"""Known game-type identifiers.

This is just a convenience list for autocomplete/typo-catching - the
platform identifies a game purely by the string you pass in URLs like
`/api/games/<game_type>/matches`, so anything the server recognizes works
here even before this tuple is updated. Keep in sync with
`server/app/mcp/tools.py::MOVE_SCHEMAS` and `server/app/games/registry.py`.
"""

from __future__ import annotations

GAME_TYPES = (
    "TIC_TAC_TOE",
    "CONNECT_FOUR",
    "ROCK_PAPER_SCISSORS",
    "TETRIS",
    "CHESS",
    "CHECKERS",
    "GO",
    "TEXAS_HOLDEM",
    "REVERSI",
    "BATTLESHIP",
)
