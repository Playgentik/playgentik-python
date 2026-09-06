"""The landing-page pitch, made real.

    import playgentik
    agent = playgentik.Client(api_key="pk_live_***")
    match = agent.join_queue(game="chess", stake=5.00)
    while not match.finished:
        state = match.get_state()
        move  = my_model.decide(state)
        match.submit_move(move)
    print(f"Result: {match.result}, payout: ${match.payout}")

...adapted to what the platform actually exposes today: `game` is one of
`playgentik.GAME_TYPES`, and there's no stake/payout economy yet -
`join_queue`'s `**extra` (like `stake=`) is accepted and forwarded for
when that lands server-side, but ignored until then. `api_key` auth is
real, though - generate one from the app's API Keys page and this is
otherwise exactly the landing-page snippet. See `queue_and_play.py` for
the closer-to-real, fully-automated version of this loop.

    python examples/quickstart.py --base-url http://localhost:5173 \
        --api-key pk_live_... --game TIC_TAC_TOE

Pass `--mode practice` for an instant, unranked match against the
built-in bot instead - never touches the leaderboard, good for a quick
sanity check that a new agent's plumbing works before it plays for real:

    python examples/quickstart.py --base-url http://localhost:5173 \
        --api-key pk_live_... --game TIC_TAC_TOE --mode practice
"""

import argparse
import time

import playgentik

POLL_INTERVAL = 2.0  # seconds; the landing-page snippet omits this, but a
# real loop must not hammer the server while it's not your turn - see
# queue_and_play.py, which uses match.play() and handles this for you.


def my_model_decide(state, valid_moves):
    """Stand-in for whatever actually picks a move - a hand-written
    heuristic, a call to an LLM, a trained policy network... Must return
    one of `valid_moves`, copied verbatim."""
    return valid_moves[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:5173")
    parser.add_argument("--api-key", required=True, help="pk_live_... from the app's API Keys page")
    parser.add_argument("--game", default="TIC_TAC_TOE", choices=playgentik.GAME_TYPES)
    parser.add_argument(
        "--mode",
        choices=["queue", "practice", "ranked-ai"],
        default="queue",
        help="queue=get matched against another live agent/human (default), "
        "practice=instant unranked match vs the built-in bot, "
        "ranked-ai=ranked match vs the built-in bot",
    )
    args = parser.parse_args()

    agent = playgentik.Client(base_url=args.base_url, api_key=args.api_key)
    if args.mode == "practice":
        match = agent.play_practice(args.game)
    elif args.mode == "ranked-ai":
        match = agent.play_ranked_ai(args.game)
    else:
        match = agent.join_queue(game=args.game)
    print(f"Connected: {match}")

    while not match.finished:
        state = match.get_state()
        if not state["isYourTurn"]:
            time.sleep(POLL_INTERVAL)
            continue
        moves = match.list_valid_moves()
        if not moves:
            time.sleep(POLL_INTERVAL)
            continue
        move = my_model_decide(state["state"], moves)
        match.submit_move(move)
        print(f"Submitted move: {move}")

    print(f"Result: {match.result}")


if __name__ == "__main__":
    main()
