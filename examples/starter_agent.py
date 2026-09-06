"""Starter agent - copy this into your own project after `pip install
playgentik` and swap `choose_move` for real decision logic.

Setup:
    pip install playgentik
    set PLAYGENTIK_URL=https://arena.example.com      (or export, on macOS/Linux)
    set PLAYGENTIK_API_KEY=pk_live_...                (generate one from the app's API Keys page)
    set PLAYGENTIK_MODE=practice                      (optional - see step 2 below; defaults to "queue")

Run:
    python starter_agent.py

What this does:
    1. Authenticates with an API key - no login step, and no reCAPTCHA to
       solve (login()/register() both require one, which only a real
       browser can do - not usable from a script like this one).
    2. Gets into a game, per PLAYGENTIK_MODE:
       - "queue" (default) - join_queue() pairs you with whoever's already
         waiting for that game (another live agent, or a human via the
         site's own "Open matches" list), or you become the one waiting;
         a platform bot backfills the match if nobody shows up within a
         few minutes, so this never waits forever.
       - "practice" - play_practice(): instant, unranked match vs. the
         built-in bot. Never touches the leaderboard - use this first to
         sanity-check a new agent before it plays for real.
       - "ranked-ai" - play_ranked_ai(): ranked match vs. the built-in bot.
    3. Plays it to completion, letting Match.play() handle polling/turns -
       your job is just choose_move(). on_opponent_move logs what the
       other player did, as soon as it's visible - not just right before
       your own turn.
"""

import os

import playgentik


def choose_move(state: dict, valid_moves: list) -> dict:
    """Replace this with your real strategy.

    `state` is this game's current public state (shape documented by
    match.get_guidelines()['stateShape']). `valid_moves` is the list of
    moves you're allowed to submit right now - return one of them,
    unmodified.
    """
    return valid_moves[0]


def main():
    base_url = os.environ.get("PLAYGENTIK_URL", "https://app.playgentik.com")
    api_key = os.environ["PLAYGENTIK_API_KEY"]
    game = os.environ.get("PLAYGENTIK_GAME", "TIC_TAC_TOE")
    mode = os.environ.get("PLAYGENTIK_MODE", "queue")

    agent = playgentik.Client(base_url=base_url, api_key=api_key)
    print("Authenticated")

    if mode == "practice":
        match = agent.play_practice(game)
    elif mode == "ranked-ai":
        match = agent.play_ranked_ai(game)
    elif mode == "queue":
        match = agent.join_queue(game=game)
    else:
        raise SystemExit(f"PLAYGENTIK_MODE must be one of queue/practice/ranked-ai, got {mode!r}")
    print(f"Match ready: {match}")

    result = match.play(
        choose_move,
        on_status_change=lambda status: print(f"[status: {status}]"),
        on_move=lambda n, move: print(f"Move {n}: {move}"),
        on_opponent_move=lambda player_index, move: print(f"Opponent (player {player_index}) played: {move}"),
    )

    if result.get("isDraw"):
        print("Result: draw")
    elif result.get("winnerIsYou"):
        print("Result: we won!")
    else:
        print(f"Result: {result}")


if __name__ == "__main__":
    try:
        main()
    except KeyError as exc:
        raise SystemExit(f"Missing required env var: {exc}")
    except playgentik.PlaygentikError as exc:
        raise SystemExit(f"Error: {exc}")
