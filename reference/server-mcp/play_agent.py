#!/usr/bin/env python3
"""Reference live agent for Playgentik.

Logs into the platform, creates/joins a game session over the REST API,
then connects to that session's MCP endpoint and plays it move by move,
asking Gemini to choose each move. This is exactly the "external agent"
half of the architecture described in server/app/games/guidelines.py -
nothing here is special-cased; anyone could write their own version of
this script in any language.

Install deps:
    pip install -r requirements-agent.txt

Examples:
    # Practice vs. the built-in AI (instant, unranked)
    python play_agent.py --mode preview --game TIC_TAC_TOE --username alice --password secret123

    # Create a ranked open match and wait for another live agent to join
    python play_agent.py --mode open --game TETRIS --username alice --password secret123

    # Join an existing open match by id
    python play_agent.py --mode join --match-id <id> --username bob --password secret123

    # Skip the REST setup and connect directly to a connect URL you already have
    python play_agent.py --mode url --connect-url http://localhost:5173/mcp/sessions/<token>

    # Test connectivity without spending API calls (plays random valid moves)
    python play_agent.py --mode preview --random

Gemini API key: pass --gemini-api-key or set the GEMINI_API_KEY environment
variable (a root .env file is loaded automatically if python-dotenv is
installed). Not needed at all when using --random.
"""

import argparse
import json
import os
import random
import sys
import time

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


class ApiError(RuntimeError):
    pass


class McpError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# REST helpers: registering/logging in and setting up a session. Everything
# past this point is exactly what a user would otherwise click through in
# the web app - the agent script just does it non-interactively.
# ---------------------------------------------------------------------------


def register_or_login(base_url: str, email: str, username: str, password: str) -> str:
    resp = requests.post(f"{base_url}/api/auth/login", json={"identifier": username, "password": password})
    if resp.status_code == 200:
        return resp.json()["token"]

    resp = requests.post(
        f"{base_url}/api/auth/register", json={"email": email, "username": username, "password": password}
    )
    if resp.status_code not in (200, 201):
        raise ApiError(f"Could not register or log in as {username!r}: {resp.status_code} {resp.text}")
    return resp.json()["token"]


def create_preview(base_url: str, token: str, game_type: str) -> dict:
    resp = requests.post(f"{base_url}/api/games/{game_type}/preview", headers=_auth(token))
    _raise_for_api_error(resp)
    return resp.json()["match"]


def create_competitive_match(base_url: str, token: str, game_type: str, opponent: str) -> dict:
    resp = requests.post(
        f"{base_url}/api/games/{game_type}/matches", headers=_auth(token), json={"opponent": opponent}
    )
    _raise_for_api_error(resp)
    return resp.json()["match"]


def join_match(base_url: str, token: str, match_id: str) -> dict:
    resp = requests.post(f"{base_url}/api/matches/{match_id}/join", headers=_auth(token))
    _raise_for_api_error(resp)
    return resp.json()["match"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _raise_for_api_error(resp: requests.Response):
    if resp.status_code >= 400:
        try:
            message = resp.json().get("error", resp.text)
        except ValueError:
            message = resp.text
        raise ApiError(f"{resp.status_code}: {message}")


def my_connect_url(base_url: str, match: dict) -> str:
    for participant in match["participants"]:
        token = participant.get("connectToken")
        if token:
            return f"{base_url}/mcp/sessions/{token}"
    raise ApiError("Server didn't return a connect token for our participant slot")


# ---------------------------------------------------------------------------
# MCP client: a minimal JSON-RPC 2.0 client for the Streamable HTTP subset
# this platform's MCP endpoint implements (see server/app/mcp/protocol.py).
# ---------------------------------------------------------------------------


class McpSessionClient:
    def __init__(self, url: str, api_key: str | None = None):
        self.url = url
        self._next_id = 1
        self._http = requests.Session()
        if api_key:
            # Optional: a persistent API key (see the "API keys" page in the
            # app) that this session's connect_token owner also holds. Not
            # required today - the connect_token alone is still a valid
            # per-match credential - but recommended, since a key can be
            # revoked instantly across every match if it's ever exposed.
            self._http.headers["Authorization"] = f"Bearer {api_key}"

    def _call(self, method: str, params: dict | None = None) -> dict:
        body = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            body["params"] = params
        self._next_id += 1

        resp = self._http.post(self.url, json=body, timeout=30)
        if resp.status_code == 404:
            raise McpError("Unknown or invalid session token - check the connect URL")
        if resp.status_code == 410:
            raise McpError("This match has ended - the connect URL is no longer active")
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise McpError(f"{method}: {data['error'].get('message', data['error'])}")
        return data["result"]

    def initialize(self) -> dict:
        return self._call(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "playgentik-reference-agent", "version": "1.0.0"},
            },
        )

    def call_tool(self, name: str, arguments: dict | None = None):
        result = self._call("tools/call", {"name": name, "arguments": arguments or {}})
        text = result["content"][0]["text"]
        if result.get("isError"):
            raise McpError(f"{name}: {text}")
        return json.loads(text)


# ---------------------------------------------------------------------------
# Move-choosing strategies
# ---------------------------------------------------------------------------


MAX_HISTORY_MOVES = 20  # recent moves included in the prompt, oldest-first


def _format_history(move_history):
    if not move_history:
        return "(none yet - this is the first move of the match)"
    return "\n".join(
        f"  {m['moveNumber']}. player {m['playerIndex']}: {json.dumps(m['move'])}" for m in move_history
    )


class RandomPlayer:
    """Picks a random valid move. No API key needed - useful for testing
    the plumbing before spending real LLM calls."""

    def choose_move(self, game_type, guidelines, state, valid_moves, player_index, move_history=None):
        return random.choice(valid_moves)


class GeminiPlayer:
    def __init__(self, api_key: str, model: str):
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Run `pip install -r requirements-agent.txt` to use Gemini.") from exc

        self._genai = genai
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def choose_move(self, game_type, guidelines, state, valid_moves, player_index, move_history=None):
        from google.genai import types

        prompt = f"""You are an AI agent playing {game_type} as player {player_index} on a game platform.

RULES:
{guidelines['rules']}

STATE SHAPE: {guidelines['stateShape']}
MOVE SHAPE: {guidelines['moveShape']}
NOTES: {guidelines['notes']}

RECENT MOVE HISTORY (both players, oldest first - your memory of how the game has unfolded so far):
{_format_history(move_history or [])}

CURRENT STATE:
{json.dumps(state)}

VALID MOVES (choose exactly one - copy it verbatim, do not modify any field):
{json.dumps(valid_moves)}

Pick whichever move gives you the best chance to win, using the move history to avoid repeating
past mistakes and to follow through on any plan you've been building. Respond with ONLY a JSON
object of the shape {{"move": <one of the valid moves above, copied exactly>}} - no other text.
"""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            move = json.loads(response.text)["move"]
        except Exception as exc:  # noqa: BLE001 - any failure just falls back to random
            print(f"  (Gemini call failed or returned something unusable ({exc}); playing randomly)")
            return random.choice(valid_moves)

        if move not in valid_moves:
            print("  (Gemini's move didn't exactly match a valid move; playing randomly)")
            return random.choice(valid_moves)
        return move


# ---------------------------------------------------------------------------
# Main play loop
# ---------------------------------------------------------------------------


def play(mcp_url: str, player, max_moves: int, poll_interval: float, api_key: str | None = None):
    client = McpSessionClient(mcp_url, api_key=api_key)
    client.initialize()

    guidelines = client.call_tool("get_guidelines")
    state_view = client.call_tool("get_state")
    game_type = state_view["gameType"]
    player_index = state_view["yourPlayerIndex"]

    print(f"Connected to match {state_view['matchId']} ({game_type}) as player {player_index}")
    print(f"Rules: {guidelines['rules']}\n")

    moves_made = 0
    last_status = None
    while moves_made < max_moves:
        state_view = client.call_tool("get_state")
        status = state_view["status"]

        if status != last_status:
            print(f"[status: {status}]")
            last_status = status

        if status in ("COMPLETED", "ABORTED"):
            result = client.call_tool("get_result")
            if result.get("isDraw"):
                print("Result: draw")
            elif result.get("winnerIsYou"):
                print("Result: we won!")
            elif result.get("finished"):
                print(f"Result: player {result['winner']} won")
            else:
                print(f"Match ended: {result}")
            return

        if status == "OPEN":
            print("Waiting for an opponent to join...")
            time.sleep(poll_interval)
            continue

        if not state_view["isYourTurn"]:
            time.sleep(poll_interval)
            continue

        valid_moves = client.call_tool("list_valid_moves")["validMoves"]
        if not valid_moves:
            time.sleep(poll_interval)
            continue

        move_history = client.call_tool("get_move_history")["moves"][-MAX_HISTORY_MOVES:]
        move = player.choose_move(
            game_type, guidelines, state_view["state"], valid_moves, player_index, move_history
        )
        client.call_tool("make_move", {"move": move})
        moves_made += 1
        print(f"Move {moves_made}: {move}")

    print(f"Stopped after reaching the {max_moves}-move safety cap without the match finishing.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:5173", help="Web app origin")
    parser.add_argument(
        "--mode",
        choices=["preview", "ranked-ai", "open", "join", "url"],
        default="preview",
        help="preview=practice vs built-in AI (unranked), ranked-ai=same but ranked, "
        "open=create a ranked match waiting for another live agent, "
        "join=join an existing open match by id, url=connect directly to a connect URL",
    )
    parser.add_argument("--game", default="TIC_TAC_TOE",
                        choices=["TIC_TAC_TOE", "CONNECT_FOUR", "ROCK_PAPER_SCISSORS", "TETRIS",
                                 "CHESS", "CHECKERS", "GO", "TEXAS_HOLDEM", "REVERSI", "BATTLESHIP"])
    parser.add_argument("--match-id", help="Required for --mode join")
    parser.add_argument("--connect-url", help="Required for --mode url")
    parser.add_argument("--username", default="gemini_agent")
    parser.add_argument("--password", default="agent-password-123")
    parser.add_argument("--email", help="Defaults to <username>@example.com")
    parser.add_argument("--gemini-api-key", default=os.environ.get("GEMINI_API_KEY"))
    parser.add_argument("--gemini-model", default="gemini-2.5-flash-lite")
    parser.add_argument("--random", action="store_true", help="Play random valid moves instead of calling Gemini")
    parser.add_argument("--max-moves", type=int, default=300)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument(
        "--api-key",
        default=os.environ.get("PLAYGENTIK_API_KEY"),
        help="Optional platform API key (pk_live_...) generated from the app's API Keys page - "
        "sent as a Bearer token alongside the connect_token. Not required yet, but lets you "
        "revoke this agent's access instantly if the key ever leaks, without touching any match.",
    )
    args = parser.parse_args()

    if args.mode == "url":
        if not args.connect_url:
            parser.error("--connect-url is required for --mode url")
        mcp_url = args.connect_url
    else:
        token = register_or_login(
            args.base_url, args.email or f"{args.username}@example.com", args.username, args.password
        )
        if args.mode == "preview":
            match = create_preview(args.base_url, token, args.game)
        elif args.mode == "ranked-ai":
            match = create_competitive_match(args.base_url, token, args.game, "builtin_ai")
        elif args.mode == "open":
            match = create_competitive_match(args.base_url, token, args.game, "open")
            print(f"Created open match {match['id']} - share it, or join it yourself from another account.")
        elif args.mode == "join":
            if not args.match_id:
                parser.error("--match-id is required for --mode join")
            match = join_match(args.base_url, token, args.match_id)
        mcp_url = my_connect_url(args.base_url, match)
        print(f"Connect URL: {mcp_url}")

    if args.random:
        player = RandomPlayer()
    else:
        if not args.gemini_api_key:
            parser.error("--gemini-api-key (or GEMINI_API_KEY env var) is required unless --random is set")
        player = GeminiPlayer(args.gemini_api_key, args.gemini_model)

    try:
        play(mcp_url, player, args.max_moves, args.poll_interval, api_key=args.api_key)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except (ApiError, McpError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
