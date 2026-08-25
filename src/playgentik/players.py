"""Ready-made strategies for `Match.play()`.

A strategy is anything with a `.choose_move(game_type, guidelines, state,
valid_moves, player_index, move_history) -> move` method - see `Match.play`
for the simpler plain-callable form too.
"""

from __future__ import annotations

import random
from typing import List, Optional


class RandomPlayer:
    """Picks a uniformly random valid move. No model, no API key - good for
    smoke-testing connectivity/plumbing before wiring up real decision
    logic, exactly like `play_agent.py --random`."""

    def choose_move(
        self,
        game_type: str,
        guidelines: dict,
        state: dict,
        valid_moves: List[dict],
        player_index: int,
        move_history: Optional[list] = None,
    ) -> dict:
        return random.choice(valid_moves)
