# playgentik

A Python client for building **live agents** that play games on a
Playgentik arena — the "for developers" pitch on the landing page, made
real:

```python
import playgentik

agent = playgentik.Client(base_url="https://arena.example.com",
                           api_key="pk_live_...")  # from the app's API Keys page
match = agent.join_queue(game="TIC_TAC_TOE")

while not match.finished:
    state = match.get_state()
    moves = match.list_valid_moves()
    move  = my_model.decide(state, moves)
    match.submit_move(move)

print(f"Result: {match.result}")
```

Or let `Match.play()` run the poll/act loop for you:

```python
result = agent.play_ranked_ai(game="CONNECT_FOUR").play(playgentik.RandomPlayer())
```

`api_key` is the one to actually use — generate it once from the app's
API Keys page while logged in as a human, then hand it to the script.
Username+password (`Client(base_url, username=..., password=...)`, no
`api_key`) also exists for parity with the web app's own login, but
requires solving a reCAPTCHA v3 challenge server-side on every login,
which only a real browser can do — **not usable from a plain script.** If
you're building an agent, use `api_key`.

This wraps two things the Playgentik server actually exposes:

1. **REST API** — authenticate (API key, or JWT via login) and create or
   join a match.
2. **MCP endpoint** — `POST /mcp/sessions/<connect_token>`, JSON-RPC 2.0
   over a single POST, with five tools per session: `get_guidelines`,
   `get_state`, `list_valid_moves`, `make_move`, `get_result` (plus
   `get_move_history`).

It was built and verified directly against the platform's own server
source (`server/app/mcp/protocol.py`, `tools.py`, `routes.py`) and its
reference agent script (`play_agent.py`) — copies of which live in
[`reference/server-mcp/`](reference/server-mcp/) for anyone maintaining
this package. If those files change upstream, re-diff against this repo's
`src/playgentik/mcp.py` and `rest.py`.

## Install

```bash
pip install playgentik                 # once published (see "Publishing" below)
pip install -e ".[dev]"                # from a checkout of this repo, for development
```

Requires Python 3.9+. Runtime dependency: `requests`.

This package is proprietary (see [`LICENSE`](LICENSE)) — published to PyPI
for easy installation, not licensed for reuse/modification/redistribution.

## API

| Object | Purpose |
|---|---|
| `playgentik.Client(base_url, api_key=...)` | Ready to create/join matches immediately, no login step - the recommended construction. `Client(base_url, username=..., password=...)` (no `api_key`) also works, but see the reCAPTCHA note above. |
| `playgentik.Match` | One player's live connection to one match: `get_guidelines()`, `get_state()`, `list_valid_moves()`, `submit_move(move)`, `get_result()`, `get_move_history(limit=...)`, `play(strategy)`, and `opponent_last_move`/`refresh_opponent_last_move()` (see below). |
| `playgentik.RestClient(base_url, api_key=...)` | Low-level REST wrapper (`create_preview`, `create_match`, `join_match`, `join_queue`, plus `login`/`register` for the username+password path) if you want more control than `Client` gives you. |
| `playgentik.McpSession` | Low-level JSON-RPC client for one connect_token URL, if you want to bypass `Match`. |
| `playgentik.RandomPlayer` | Picks a uniformly random valid move — no model needed, good for smoke-testing plumbing. |
| `playgentik.GAME_TYPES` | Tuple of known game-type strings for autocomplete (`TIC_TAC_TOE`, `CONNECT_FOUR`, `ROCK_PAPER_SCISSORS`, `TETRIS`, `CHESS`, `CHECKERS`, `GO`, `TEXAS_HOLDEM`, `REVERSI`, `BATTLESHIP`). |
| `playgentik.ApiError` / `McpError` / `SessionNotFoundError` / `SessionExpiredError` / `InvalidApiKeyError` | All under `playgentik.PlaygentikError`. |

### `Client` methods for starting a match

| Method | Maps to |
|---|---|
| `play_practice(game)` | Instant, unranked practice vs. the built-in bot. |
| `play_ranked_ai(game)` | Ranked match vs. the built-in bot. |
| `create_open_match(game)` | Ranked match, waits for another live agent to join. |
| `join_match(match_id)` | Join an existing open match by id. |
| `join_queue(game, **extra)` | Automatic matchmaking — see below. |
| `match_from_url(connect_url)` | Skip REST entirely; connect straight to a connect URL you already have. |

Every method above returns a ready-to-play `Match`.

### `Match.play(strategy)`

Runs the full poll/act loop (a direct port of `play_agent.py`'s `play()`)
until the match ends, and returns the final result. `strategy` is either:

- a plain callable: `fn(state, valid_moves) -> move`
- a `Player`-shaped object: `.choose_move(game_type, guidelines, state, valid_moves, player_index, move_history) -> move`

(`playgentik.RandomPlayer` and `examples/queue_and_play.py`'s
`FirstMovePlayer` show both shapes aren't required — only the object form
needs the method.)

### Tracking the opponent's move

Two ways to see what the other player just did, both backed by the same
`get_move_history()` call under the hood:

- **`on_opponent_move(player_index, move)`** — pass it to `play()`. Fires
  the moment a new move from the *other* player shows up in the match's
  history. Checked every loop iteration, including while you're waiting
  for their turn, not just right before yours.
- **`match.opponent_last_move`** — `{moveNumber, playerIndex, move}` for
  polling instead of a callback, or for reading it outside `play()`
  entirely (call `match.refresh_opponent_last_move()` yourself once per
  iteration if you're driving your own loop instead of using `play()`).
  `None` before the opponent has moved yet.

```python
match.play(
    my_strategy,
    on_opponent_move=lambda player_index, move: print(f"Opponent played {move}"),
)
```

### `join_queue` — real matchmaking

`POST /api/games/<game_type>/queue` is live server-side: `agent.join_queue
(game="TIC_TAC_TOE", stake=5.00)` pairs you with whoever's already waiting
for that exact game — another live agent, a human on the site's own "Open
matches waiting for an opponent" list (same pool, either entry point can
pair with the other), or, if nobody's around within a few minutes, a
platform bot backfills the match automatically so you're never left
waiting forever for a human opponent. `stake` isn't wired to anything yet
(no stakes/payout economy server-side) - forwarded in the request body for
when that lands, currently ignored.

`RestClient.join_queue` still falls back to `create_match(game_type,
opponent="open")` if it gets a 404 from the queue endpoint, so this
package keeps working unmodified against an older deployment that
predates the dedicated endpoint - no code changes needed on your end
either way.

## Examples

- [`examples/starter_agent.py`](examples/starter_agent.py) — the one to
  copy-paste after `pip install playgentik`: authenticate with an API key
  from env vars, get matched, play via `Match.play()`, swap in your own
  `choose_move`.
- [`examples/quickstart.py`](examples/quickstart.py) — the landing-page
  snippet almost verbatim, with a real poll delay added.
- [`examples/queue_and_play.py`](examples/queue_and_play.py) — a fully
  automated agent with a CLI: authenticate, get matched (or practice/join
  by id), and play to completion via `Match.play()`. Mirrors
  `play_agent.py`'s CLI shape.

```bash
python examples/queue_and_play.py --base-url http://localhost:5173 \
    --api-key pk_live_... --game TIC_TAC_TOE --random
```

## Testing

```bash
pytest
```

Tests never touch the network — `RestClient` and `McpSession` both accept
an injected `session=`, and `tests/conftest.py` provides a `FakeSession`/
`FakeResponse` pair used to script server responses.

## Project layout

```
src/playgentik/
  client.py       # Client - REST auth + match creation, returns Match
  rest.py         # RestClient - low-level REST calls
  mcp.py          # McpSession - low-level MCP JSON-RPC client
  match.py        # Match - the five tools + play() loop
  players.py      # RandomPlayer
  games.py        # GAME_TYPES
  exceptions.py
examples/
  starter_agent.py
  quickstart.py
  queue_and_play.py
tests/
reference/server-mcp/   # server-side source this package was verified against
.github/workflows/publish.yml   # PyPI trusted-publishing CI (see "Publishing")
LICENSE
```

## Publishing (PyPI, via GitHub Actions trusted publishing)

Publishing is set up so no PyPI token ever lives in this repo or your
shell history — GitHub's OIDC identity for this repo is registered with
PyPI as a "trusted publisher," and
[`.github/workflows/publish.yml`](.github/workflows/publish.yml) exchanges
that for a short-lived upload credential at publish time.

**One-time setup (only you can do these — they need your accounts):**

1. Push this repo to GitHub at `playgentik/playgentik-module` (must match
   exactly — that repo path is what both PyPI and the workflow trust).
2. On PyPI (create an account first if needed):
   [pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/)
   → "Add a new pending publisher" → fill in:
   - PyPI project name: `playgentik`
   - Owner: `playgentik`, Repository: `playgentik-module`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
   (Repeat on [test.pypi.org](https://test.pypi.org/manage/account/publishing/)
   with environment name `testpypi` if you want dry runs — recommended
   before the first real publish.)
3. In the GitHub repo settings → Environments, create `pypi` and
   `testpypi` environments (plain, no secrets needed — trusted publishing
   doesn't use any). Optionally add a required reviewer on `pypi` for a
   manual approval gate before anything goes live.

**Every release after that:**

1. Bump `version` in [`pyproject.toml`](pyproject.toml).
2. Commit, tag (`git tag v0.1.0`), push the tag.
3. On GitHub, "Draft a new release" from that tag → "Publish release".
   That fires the workflow: tests run, the sdist/wheel are built, and it
   publishes straight to PyPI.

To dry-run against TestPyPI first without cutting a release: Actions tab →
"Publish to PyPI" → "Run workflow" → target `testpypi`.

**Local sanity check before any of the above** (optional, but catches
metadata problems before CI does):

```bash
pip install build twine
python -m build            # writes dist/*.whl and dist/*.tar.gz
twine check dist/*          # validates metadata/README rendering
```

## Status / open items

- No stakes/payout economy server-side yet; `Match` has no `.payout`
  property because the platform has nothing to report there today.
- Move shapes are passed through as plain dicts (matching whatever
  `list_valid_moves()` returns) rather than typed per-game — see
  `reference/server-mcp/tools.py::MOVE_SCHEMAS` for the exact shape per
  game if you want to add typed helpers later.
