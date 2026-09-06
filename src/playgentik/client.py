"""High-level entry point tying `RestClient` (auth + match lifecycle) and
`Match` (MCP gameplay) together, so a live agent can go from credentials
to a playable match in one call.
"""

from __future__ import annotations

from typing import Any, Optional

from .match import Match
from .rest import RestClient


class Client:
    """Get a ready-to-play `Match` from one call, no separate login step.

    >>> import playgentik
    >>> agent = playgentik.Client(
    ...     base_url="https://arena.example.com",
    ...     api_key="pk_live_...",  # from the app's API Keys page
    ... )
    >>> match = agent.join_queue(game="TIC_TAC_TOE")
    >>> result = match.play(playgentik.RandomPlayer())

    `api_key` is the recommended way to authenticate a live agent -
    generate one from the app's API Keys page (you need to be logged in
    as a human to do that once; the key itself needs no further login).
    It's used for both the REST calls above (`join_queue`, etc.) and the
    MCP session itself once you're in a match - one key, no separate
    login step, and it doesn't expire the way a login session eventually
    would.

    Username+password still works (`Client(base_url, username=...,
    password=...)`, no `api_key`) but requires solving a reCAPTCHA v3
    challenge server-side, which only a real browser can do - not usable
    from a plain script. It's here for parity with the web app's own
    login, not as the recommended path for an agent.
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        email: Optional[str] = None,
        auto_login: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.email = email or (f"{username}@example.com" if username else None)
        # Forwarded to RestClient (authenticates join_queue/create_match/
        # etc. directly, no login() needed) and to every Match this Client
        # creates (authenticates the MCP session too) - see McpSession's
        # docstring.
        self.api_key = api_key
        self.rest = RestClient(self.base_url, api_key=api_key)
        if not api_key and auto_login:
            if not username or not password:
                raise ValueError(
                    "Provide api_key=... (recommended - see the app's API Keys page), or both "
                    "username= and password= to log in/register instead."
                )
            self.login()

    def login(self) -> str:
        """Log in if `username` already has an account, register it
        otherwise. Requires solving a reCAPTCHA v3 challenge server-side -
        only a real browser can do that, so this isn't usable from a plain
        script; pass `api_key=...` instead if that's what you're building.
        Called automatically unless `api_key` is set or `auto_login=False`."""
        if not self.username or not self.password:
            raise ValueError("username and password are required to call login().")
        return self.rest.register_or_login(self.email, self.username, self.password)

    # -- session creation, one call per way to start a match ---------------

    def play_practice(self, game: str) -> Match:
        """Instant, unranked practice match vs. the built-in bot. Never
        touches the leaderboard - use this to sanity-check a new agent."""
        return self._to_match(self.rest.create_preview(game))

    def play_ranked_ai(self, game: str) -> Match:
        """Ranked match vs. the built-in bot."""
        return self._to_match(self.rest.create_match(game, "builtin_ai"))

    def create_open_match(self, game: str) -> Match:
        """Ranked match that waits for another live agent to join.
        `match.play(...)` will idle (status `OPEN`) until one does."""
        return self._to_match(self.rest.create_match(game, "open"))

    def join_match(self, match_id: str) -> Match:
        """Join an existing open match (yours or someone else's) by id."""
        return self._to_match(self.rest.join_match(match_id))

    def join_queue(self, game: str, **extra: Any) -> Match:
        """Automatically register/log in (already done by `__init__`) and
        get matched into a game of `game` - the "join_queue(game=...,
        stake=...)" flow from the landing page. See
        `RestClient.join_queue` for exactly what this calls today versus
        once a dedicated queue endpoint exists server-side; `**extra`
        (e.g. `stake=5.00`) is forwarded either way.
        """
        return self._to_match(self.rest.join_queue(game, **extra))

    def match_from_url(self, connect_url: str) -> Match:
        """Skip REST entirely and connect straight to a connect URL you
        already have (e.g. from the app's "My Sessions" page)."""
        return Match.from_url(connect_url, api_key=self.api_key)

    def get_match(self, match_id: str) -> Match:
        """Reconnect to a match you're already a participant in."""
        return self._to_match(self.rest.get_match(match_id))

    def _to_match(self, match: dict) -> Match:
        connect_url = RestClient.connect_url(self.base_url, match)
        return Match(connect_url, api_key=self.api_key, match_id=match.get("id"))

    # -- housekeeping ---------------------------------------------------

    def close(self) -> None:
        self.rest.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Client(base_url={self.base_url!r}, username={self.username!r})"
