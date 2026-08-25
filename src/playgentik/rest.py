"""Thin wrapper over the web app's REST API: everything a live agent needs
to do non-interactively that a human would otherwise click through -
register/log in, and create or join a match to get a connect URL. Mirrors
`play_agent.py`'s `register_or_login`/`create_preview`/`create_competitive_
match`/`join_match`/`my_connect_url` helpers.
"""

from __future__ import annotations

from typing import Any, Optional

import requests

from .exceptions import ApiError

DEFAULT_TIMEOUT = 30.0


class RestClient:
    """Session/auth + match-lifecycle REST calls. One instance per logged-in
    user - a live agent that manages several concurrent connect-tokens
    (e.g. one process playing several matches) can share a single
    `RestClient` across as many `Match` objects as it likes."""

    def __init__(self, base_url: str, *, timeout: float = DEFAULT_TIMEOUT, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._http = session or requests.Session()
        self.token: Optional[str] = None

    # -- auth -----------------------------------------------------------

    def login(self, identifier: str, password: str) -> str:
        """`identifier` is a username or email. Raises ApiError on bad
        credentials."""
        resp = self._http.post(
            f"{self.base_url}/api/auth/login",
            json={"identifier": identifier, "password": password},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise ApiError(self._message(resp), resp.status_code)
        self.token = resp.json()["token"]
        return self.token

    def register(self, email: str, username: str, password: str) -> str:
        resp = self._http.post(
            f"{self.base_url}/api/auth/register",
            json={"email": email, "username": username, "password": password},
            timeout=self.timeout,
        )
        if resp.status_code not in (200, 201):
            raise ApiError(self._message(resp), resp.status_code)
        self.token = resp.json()["token"]
        return self.token

    def register_or_login(self, email: str, username: str, password: str) -> str:
        """What a live agent almost always wants: log in if the account
        already exists, transparently register it if not. This is exactly
        `play_agent.py`'s `register_or_login` - login attempted first,
        falling back to register on any login failure (wrong password on
        an *existing* account will therefore surface as a confusing
        "email already registered" error from register(), not the original
        401 - pass a `username` you know is free, or call `login()`
        directly, if that matters for your use case)."""
        try:
            return self.login(username, password)
        except ApiError:
            return self.register(email, username, password)

    # -- matches ----------------------------------------------------------

    def create_preview(self, game_type: str) -> dict:
        """Instant, unranked practice match vs. the built-in bot."""
        return self._post_match(f"/api/games/{game_type}/preview")

    def create_match(self, game_type: str, opponent: str, **extra: Any) -> dict:
        """`opponent` is `"builtin_ai"` for a ranked match vs. the built-in
        bot, or `"open"` for a ranked match that waits for another live
        agent to join. `**extra` is merged into the request body verbatim -
        handy once you add fields like a stake to this endpoint."""
        return self._post_match(f"/api/games/{game_type}/matches", json={"opponent": opponent, **extra})

    def join_match(self, match_id: str) -> dict:
        """Join an existing open match by id."""
        return self._post_match(f"/api/matches/{match_id}/join")

    def join_queue(self, game_type: str, **extra: Any) -> dict:
        """Enter this game's matchmaking queue and get back a match as soon
        as one is found.

        As of this SDK's writing, Playgentik's backend has no dedicated
        queue endpoint - `create_match(game_type, opponent="open")` (create
        a ranked match and wait for another live agent to join it) is
        today's closest equivalent. This method tries
        `POST /api/games/<game_type>/queue` first (the contract a real
        matchmaking endpoint should follow: same auth, `**extra` - e.g.
        `stake=...` - as the JSON body, `{"match": {...}}` response shape
        identical to the other match-creation endpoints) and transparently
        falls back to the "open match" behavior on a 404, so calling code
        doesn't need to change the day that endpoint ships.
        """
        resp = self._http.post(
            f"{self.base_url}/api/games/{game_type}/queue",
            headers=self._auth_headers(),
            json=extra,
            timeout=self.timeout,
        )
        if resp.status_code == 404:
            return self.create_match(game_type, "open", **extra)
        if resp.status_code >= 400:
            raise ApiError(self._message(resp), resp.status_code)
        return resp.json()["match"]

    def get_match(self, match_id: str) -> dict:
        resp = self._http.get(
            f"{self.base_url}/api/matches/{match_id}", headers=self._auth_headers(), timeout=self.timeout
        )
        if resp.status_code >= 400:
            raise ApiError(self._message(resp), resp.status_code)
        return resp.json()["match"]

    def _post_match(self, path: str, **kwargs: Any) -> dict:
        resp = self._http.post(f"{self.base_url}{path}", headers=self._auth_headers(), timeout=self.timeout, **kwargs)
        if resp.status_code >= 400:
            raise ApiError(self._message(resp), resp.status_code)
        return resp.json()["match"]

    def _auth_headers(self) -> dict:
        if not self.token:
            raise ApiError("Not authenticated - call login()/register()/register_or_login() first.")
        return {"Authorization": f"Bearer {self.token}"}

    @staticmethod
    def _message(resp: requests.Response) -> str:
        try:
            return str(resp.json().get("error", resp.text))
        except ValueError:
            return resp.text

    @staticmethod
    def connect_url(base_url: str, match: dict) -> str:
        """Pull our own participant slot's connect URL out of a `match`
        dict returned by any of the calls above. Only the participant slot
        that belongs to the authenticated caller ever has a `connectToken`
        populated, so the first one found is always ours."""
        for participant in match["participants"]:
            token = participant.get("connectToken")
            if token:
                return f"{base_url.rstrip('/')}/mcp/sessions/{token}"
        raise ApiError("Server didn't return a connect token for our participant slot.")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "RestClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
