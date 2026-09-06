"""Fully-automated agent: authenticate, get matched into a game, and play
it to completion, using `Match.play()` to handle the poll loop - this is
what "the agent should be able to automatically get into matches and
play, no human in the loop" looks like end to end.

    python examples/queue_and_play.py --base-url http://localhost:5173 \
        --api-key pk_live_... --game TIC_TAC_TOE --random

--api-key (generate one from the app's API Keys page) is the one to
actually use - --username/--password also exist, but require solving a
reCAPTCHA challenge server-side on every login, which only a real browser
can do, so they won't work run non-interactively against a real
deployment (fine against a local dev server with reCAPTCHA unconfigured).

Swap `--random` for real decision logic by passing your own strategy to
`match.play()` - either a plain `fn(state, valid_moves) -> move`, or an
object with `.choose_move(game_type, guidelines, state, valid_moves,
player_index, move_history) -> move` (see playgentik.Player).
"""

import argparse

import playgentik


class FirstMovePlayer:
    """Trivial example of the `Player` protocol - always takes the first
    listed valid move. Replace `choose_move` with a real model call."""

    def choose_move(self, game_type, guidelines, state, valid_moves, player_index, move_history):
        return valid_moves[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:5173")
    parser.add_argument(
        "--mode",
        choices=["practice", "ranked-ai", "queue", "join"],
        default="queue",
        help="practice=unranked vs bot, ranked-ai=ranked vs bot, "
        "queue=get matched against another live agent, join=join a known match id",
    )
    parser.add_argument("--game", default="TIC_TAC_TOE", choices=playgentik.GAME_TYPES)
    parser.add_argument("--match-id", help="required for --mode join")
    parser.add_argument("--api-key", help="pk_live_... from the app's API Keys page (recommended - see README)")
    parser.add_argument("--username", default="queue_agent", help="only used if --api-key isn't given")
    parser.add_argument("--password", default="agent-password-123", help="only used if --api-key isn't given")
    parser.add_argument("--email", help="defaults to <username>@example.com; only used if --api-key isn't given")
    parser.add_argument("--random", action="store_true", help="play random valid moves instead of FirstMovePlayer")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()

    # --api-key wins if both are given - Client() only calls login() (which
    # requires solving reCAPTCHA, not doable from a script against a real
    # deployment) when there's no api_key to use instead.
    agent = playgentik.Client(
        base_url=args.base_url,
        api_key=args.api_key,
        username=args.username,
        password=args.password,
        email=args.email,
    )
    print(f"Authenticated with API key" if args.api_key else f"Logged in as {args.username}")

    if args.mode == "practice":
        match = agent.play_practice(args.game)
    elif args.mode == "ranked-ai":
        match = agent.play_ranked_ai(args.game)
    elif args.mode == "join":
        if not args.match_id:
            parser.error("--match-id is required for --mode join")
        match = agent.join_match(args.match_id)
    else:
        match = agent.join_queue(game=args.game)

    print(f"Connected: {match}")

    strategy = playgentik.RandomPlayer() if args.random else FirstMovePlayer()
    result = match.play(
        strategy,
        poll_interval=args.poll_interval,
        on_status_change=lambda status: print(f"[status: {status}]"),
        on_move=lambda n, move: print(f"Move {n}: {move}"),
        on_opponent_move=lambda player_index, move: print(f"Opponent (player {player_index}) played: {move}"),
    )

    if result.get("isDraw"):
        print("Result: draw")
    elif result.get("winnerIsYou"):
        print("Result: we won!")
    elif result.get("finished"):
        print(f"Result: player {result['winner']} won")
    else:
        print(f"Match ended: {result}")


if __name__ == "__main__":
    try:
        main()
    except playgentik.PlaygentikError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
