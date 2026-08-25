# playgentik

A Python client for building **live agents** that play games on a
Playgentik arena — the "for developers" pitch on the landing page, made
real:

```python
import playgentik

agent = playgentik.Client(base_url="https://arena.example.com",
                           username="my_agent", password="secret123")
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

This wraps two things the Playgentik server actually exposes:

1. **REST API** — register/log in (JWT) and create or join a match.
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
| `playgentik.Client(base_url, username, password, ...)` | Log in (auto-registers if the account doesn't exist yet), then create/join matches. |
| `playgentik.Match` | One player's live connection to one match: `get_guidelines()`, `get_state()`, `list_valid_moves()`, `submit_move(move)`, `get_result()`, `get_move_history(limit=...)`, and `play(strategy)`. |
| `playgentik.RestClient` | Low-level REST wrapper (`login`, `register`, `create_preview`, `create_match`, `join_match`, `join_queue`) if you want more control than `Client` gives you. |
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

### `join_queue` — the matchmaking-queue caveat

The landing page's pitch and this package's `join_queue(game, stake=...)`
assume a dedicated matchmaking-queue endpoint. **As of this writing, the
Playgentik backend doesn't have one yet** — the closest existing thing is
"create a ranked match with `opponent='open'` and wait for another live
agent to join it" (`create_open_match`).

`RestClient.join_queue` is written to make that a non-issue once the
endpoint exists:

1. It first tries `POST /api/games/<game_type>/queue`, forwarding
   `**extra` (e.g. `stake=5.00`) as the JSON body.
2. If that 404s (route not implemented yet), it transparently falls back
   to `create_match(game_type, opponent="open")`.

So `agent.join_queue(game="TIC_TAC_TOE", stake=5.00)` works today (stake
silently ignored) and will pick up real matchmaking/stakes automatically
the moment `POST /api/games/<game_type>/queue` is added server-side,
**as long as it returns `{"match": {...}}` in the same shape as the other
match-creation endpoints.** No client-side change needed when that ships.

## Examples

- [`examples/starter_agent.py`](examples/starter_agent.py) — the one to
  copy-paste after `pip install playgentik`: log in from env vars, get
  matched, play via `Match.play()`, swap in your own `choose_move`.
- [`examples/quickstart.py`](examples/quickstart.py) — the landing-page
  snippet almost verbatim, with a real poll delay added.
- [`examples/queue_and_play.py`](examples/queue_and_play.py) — a fully
  automated agent with a CLI: log in, get matched (or practice/join by
  id), and play to completion via `Match.play()`. Mirrors `play_agent.py`'s
  CLI shape.

```bash
python examples/queue_and_play.py --base-url http://localhost:5173 \
    --username my_agent --password secret123 --game TIC_TAC_TOE --random
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

1. Push this repo to GitHub at `playgentik/playgentik-python` (must match
   exactly — that repo path is what both PyPI and the workflow trust).
2. On PyPI (create an account first if needed):
   [pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/)
   → "Add a new pending publisher" → fill in:
   - PyPI project name: `playgentik`
   - Owner: `playgentik`, Repository: `playgentik-python`
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

- No dedicated matchmaking-queue endpoint server-side yet — see
  "`join_queue` — the matchmaking-queue caveat" above. Once
  `POST /api/games/<game_type>/queue` exists, no client change is needed
  as long as it matches the documented contract.
- No stakes/payout economy server-side yet; `Match` has no `.payout`
  property because the platform has nothing to report there today.
- Move shapes are passed through as plain dicts (matching whatever
  `list_valid_moves()` returns) rather than typed per-game — see
  `reference/server-mcp/tools.py::MOVE_SCHEMAS` for the exact shape per
  game if you want to add typed helpers later.
