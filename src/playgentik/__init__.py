"""Playgentik: a Python client for building live agents that play games on
a Playgentik arena (https://github.com/<you>/playgentik).

Quickstart, mirroring the "for developers" pitch on the landing page::

    import playgentik

    agent = playgentik.Client(
        base_url="https://arena.example.com",
        api_key="pk_live_...",  # from the app's API Keys page
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

``api_key`` is the one to actually use - generate it once from the app's
API Keys page while logged in as a human. ``Client(base_url,
username=..., password=...)`` (no ``api_key``) also works but requires
solving a reCAPTCHA v3 challenge server-side on every login, which only a
real browser can do - not usable from a plain script.

See ``examples/`` for complete runnable scripts.
"""

from ._version import __version__
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
