"""Reset audit: classify every early window restart as global (free) or banked (consumed)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import List

from .parser import Window, LimitHit, fmt_local
from .reference_resets import GLOBAL_RESETS_UTC, GLOBAL_RESET_TOLERANCE_S

# A banked reset spent while the weekly window was below this percent was mostly wasted.
WASTE_THRESHOLD_PCT = 40.0


@dataclass
class ResetEvent:
    ts: int                 # when the new window started
    previous_end: int       # natural end of the previous window
    kind: str               # "global" | "banked" | "unknown-early"
    previous_peak: float    # peak usage of the window that got cut short
    wasted: bool            # True if a banked reset refreshed almost nothing


def detect_resets(windows: List[Window]) -> List[ResetEvent]:
    """An early restart = consecutive windows where next.started < prev.resets_at."""
    events = []
    for prev, nxt in zip(windows, windows[1:]):
        prev_start = prev.started_at()
        nxt_start = nxt.started_at()
        if nxt_start >= prev.resets_at:
            continue  # natural expiry, nothing consumed
        kind = "unknown-early"
        for g in GLOBAL_RESETS_UTC:
            if abs(nxt_start - g) <= GLOBAL_RESET_TOLERANCE_S:
                kind = "global"
                break
        else:
            kind = "banked"
        events.append(ResetEvent(
            ts=nxt_start,
            previous_end=prev.resets_at,
            kind=kind,
            previous_peak=prev.peak,
            wasted=(kind == "banked" and prev.peak < WASTE_THRESHOLD_PCT),
        ))
    return events


def format_resets(events: List[ResetEvent]) -> str:
    if not events:
        return "No early window restarts detected."
    lines = []
    for e in events:
        icon = {"global": "🌐 global (free)", "banked": "🏦 banked (consumed)"}.get(e.kind, e.kind)
        waste = "  ⚠️ WASTED" if e.wasted else ""
        lines.append(
            f"{fmt_local(e.ts)}  new window started | prev would have ended "
            f"{fmt_local(e.previous_end)} ({(e.previous_end - e.ts) / 3600:.1f}h early) | "
            f"prev peak {e.previous_peak:.0f}% | {icon}{waste}"
        )
    return "\n".join(lines)
