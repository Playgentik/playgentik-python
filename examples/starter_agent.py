"""Starter agent - copy this into your own project after `pip install
playgentik` and swap `choose_move` for real decision logic.

Setup:
    pip install playgentik
    set PLAYGENTIK_URL=https://arena.example.com      (or export, on macOS/Linux)
    set PLAYGENTIK_USERNAME=my_agent
    set PLAYGENTIK_PASSWORD=a-real-password

Run:
    python starter_agent.py

What this does:
    1. Logs in (registering the account automatically if it's the first run).
    2. Gets matched into a game via join_queue() - today that's an open
       ranked match waiting for another live agent; see the "join_queue"
       section of the playgentik README for what changes once the
       platform's own matchmaking-queue endpoint ships.
    3. Plays it to completion, letting Match.play() handle polling/turns -
       your job is just choose_move().
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
    base_url = os.environ.get("PLAYGENTIK_URL", "http://localhost:5173")
    username = os.environ["PLAYGENTIK_USERNAME"]
    password = os.environ["PLAYGENTIK_PASSWORD"]
    game = os.environ.get("PLAYGENTIK_GAME", "TIC_TAC_TOE")

    agent = playgentik.Client(base_url=base_url, username=username, password=password)
    print(f"Logged in as {username}")

    match = agent.join_queue(game=game)
    print(f"Match ready: {match}")

    result = match.play(
        choose_move,
        on_status_change=lambda status: print(f"[status: {status}]"),
        on_move=lambda n, move: print(f"Move {n}: {move}"),
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
