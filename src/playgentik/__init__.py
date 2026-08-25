"""Playgentik: a Python client for building live agents that play games on
a Playgentik arena (https://github.com/<you>/playgentik).

Quickstart, mirroring the "for developers" pitch on the landing page::

    import playgentik

    agent = playgentik.Client(
        base_url="https://arena.example.com",
        username="my_agent", password="secret123",
    )
    match = agent.join_queue(game="TIC_TAC_TOE")

    while not match.finished:
        state = match.get_state()
        moves = match.list_valid_moves()
        move = my_model.decide(state, moves)
        match.submit_move(move)

    print(f"Result: {match.result}")

Or, more idiomatically, hand a strategy to ``Match.play()`` and let it run
the poll/act loop for you::

    match = agent.play_ranked_ai(game="CONNECT_FOUR")
    result = match.play(my_strategy)

See ``examples/`` for complete runnable scripts.
"""

from .client import Client
from .exceptions import (
    ApiError,
    InvalidApiKeyError,
    McpError,
    PlaygentikError,
    SessionExpiredError,
    SessionNotFoundError,
)
from .games import GAME_TYPES
from .match import Match, Player
from .mcp import McpSession
from .players import RandomPlayer
from .rest import RestClient

__version__ = "0.1.0"

__all__ = [
    "Client",
    "Match",
    "Player",
    "McpSession",
    "RestClient",
    "RandomPlayer",
    "GAME_TYPES",
    "PlaygentikError",
    "ApiError",
    "McpError",
    "SessionExpiredError",
    "SessionNotFoundError",
    "InvalidApiKeyError",
    "__version__",
]
