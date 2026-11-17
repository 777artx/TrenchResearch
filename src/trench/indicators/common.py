"""Shared indicator rules (SPEC §3)."""

from __future__ import annotations

from collections.abc import Sequence


def confirm_states(raw: Sequence[str | None], n: int = 2) -> list[str | None]:
    """Symmetric confirmation: the published state changes only after ``n``
    consecutive readings agree on a new state. The same rule applies in every
    direction, so there is no one-sided cooldown."""
    out: list[str | None] = []
    state: str | None = None
    run_state, run_len = None, 0
    for s in raw:
        if s is None:
            out.append(state)
            continue
        if s == run_state:
            run_len += 1
        else:
            run_state, run_len = s, 1
        if state is None or (s != state and run_len >= n):
            state = s
        out.append(state)
    return out
