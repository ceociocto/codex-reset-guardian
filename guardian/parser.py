"""Parse Codex session rollouts and thread history into usage windows.

Data sources (all local, read-only):
- ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
    every turn emits rate_limit events:
    {"rate_limits": {"limit_id": "codex",
      "primary":   {"used_percent": X, "window_minutes": 300,   "resets_at": ts},
      "secondary": {"used_percent": X, "window_minutes": 10080, "resets_at": ts},
      "credits": {"has_credits": bool, "unlimited": bool, "balance": "0"},
      "plan_type": "plus", ...}}
- ~/.codex/thread_history_*.sqlite  table thread_turns(thread_id, turn_id, status,
    error_json, started_at, completed_at, duration_ms, ...)
    status='failed' + error_json containing "usage limit" => a limit hit,
    the message includes the server-provided retry time.
"""

from __future__ import annotations

import glob
import json
import os
import sqlite3
import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

DEFAULT_CODEX_HOME = os.path.expanduser("~/.codex")


@dataclass
class LimitSample:
    ts: str          # ISO timestamp of the event
    percent: float
    window_minutes: int
    resets_at: int


@dataclass
class Window:
    resets_at: int                       # natural end of the window
    samples: List[LimitSample] = field(default_factory=list)

    @property
    def peak(self) -> float:
        return max((s.percent for s in self.samples), default=0.0)

    @property
    def first_seen(self) -> Optional[str]:
        return self.samples[0].ts if self.samples else None

    @property
    def last_seen(self) -> Optional[str]:
        return self.samples[-1].ts if self.samples else None

    def started_at(self) -> int:
        return self.resets_at - self.samples[0].window_minutes * 60 if self.samples else 0


@dataclass
class LimitHit:
    ts: int
    message: str
    retry_hint: Optional[str] = None


def _walk_rate_limits(obj):
    """Yield every dict that looks like a rate_limits payload."""
    if isinstance(obj, dict):
        prim = obj.get("primary")
        if isinstance(prim, dict) and "used_percent" in prim:
            yield obj
        for v in obj.values():
            yield from _walk_rate_limits(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_rate_limits(v)


def parse_sessions(codex_home: str = DEFAULT_CODEX_HOME):
    """Return (samples5h, samples_weekly) — flat lists of LimitSample."""
    s5, sw = [], []
    for path in glob.glob(os.path.join(codex_home, "sessions", "**", "*.jsonl"), recursive=True):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"rate_limits"' not in line:
                        continue
                    try:
                        doc = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = doc.get("timestamp")
                    for rl in _walk_rate_limits(doc):
                        try:
                            p, s = rl["primary"], rl["secondary"]
                            if p.get("used_percent") is not None:
                                s5.append(LimitSample(ts, float(p["used_percent"]),
                                                      int(p["window_minutes"]), int(p["resets_at"])))
                            if s.get("used_percent") is not None:
                                sw.append(LimitSample(ts, float(s["used_percent"]),
                                                      int(s["window_minutes"]), int(s["resets_at"])))
                        except (KeyError, TypeError, ValueError):
                            continue
        except OSError:
            continue
    return s5, sw


def group_windows(samples: List[LimitSample]) -> List[Window]:
    """Group samples into physical windows by walking the timeline.

    Key insight: a new window's resets_at is always >= the previous window's
    resets_at (an early restart still lands its natural end after the old end
    in practice, and a natural expiry lands later still). So walking samples
    chronologically, a resets_at *increase* marks a new physical window, while
    a sample carrying an older resets_at is a replay from a resumed thread and
    belongs to that older window.
    """
    samples = sorted(samples, key=lambda s: (s.ts or "", s.resets_at))
    windows: List[Window] = []
    by_key: List[Window] = []          # all windows, searchable by resets_at
    current: Optional[Window] = None
    for s in samples:
        target = None
        if current is not None and abs(current.resets_at - s.resets_at) <= 120:
            target = current
        else:
            for w in by_key:
                if abs(w.resets_at - s.resets_at) <= 120:
                    target = w
                    break
            if target is None:
                target = Window(resets_at=s.resets_at, samples=[])
                by_key.append(target)
                windows.append(target)
        # a later observed window supersedes an earlier one only if its
        # resets_at moved forward: promote chronological "current"
        if current is None or target.resets_at >= current.resets_at:
            current = target
        target.samples.append(s)
    windows.sort(key=lambda w: w.resets_at)
    return windows


def current_window_samples(samples: List[LimitSample],
                           lookback_h: float) -> List[LimitSample]:
    """Samples of the *live* window.

    Resumed threads replay their last-known rate_limits with a fresh timestamp,
    so a stale window can appear newer than reality. The live window is the one
    with the FRESHEST resets_at among samples observed in the recent lookback
    period — a stale replay by definition carries an older resets_at.
    """
    import datetime as _dt
    cutoff = None
    for s in reversed(samples):
        t = _parse_iso(s.ts)
        if t:
            cutoff = t - _dt.timedelta(hours=lookback_h)
            break
    if cutoff is None:
        return []
    recent = [s for s in samples if (t := _parse_iso(s.ts)) and t >= cutoff]
    if not recent:
        return []
    best_resets_at = max(s.resets_at for s in recent)
    live = [s for s in recent if s.resets_at == best_resets_at]
    live.sort(key=lambda s: s.ts or "")
    return live


def _parse_iso(ts):
    import datetime as _dt
    try:
        return _dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def parse_limit_hits(codex_home: str = DEFAULT_CODEX_HOME) -> List[LimitHit]:
    """Extract usage-limit failures from thread_history sqlite."""
    hits = []
    for db_path in sorted(glob.glob(os.path.join(codex_home, "thread_history_*.sqlite"))):
        try:
            db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.Error:
            continue
        try:
            rows = db.execute(
                "SELECT started_at, error_json FROM thread_turns "
                "WHERE status='failed' AND error_json LIKE '%usage limit%'"
            ).fetchall()
        except sqlite3.Error:
            db.close()
            continue
        for started_at, err in rows:
            if started_at is None:
                continue
            msg = ""
            retry = None
            try:
                parsed = json.loads(err)
                msg = parsed.get("message", "")
                retry = parsed.get("codexErrorInfo", {}).get("retry_at") if isinstance(
                    parsed.get("codexErrorInfo"), dict) else None
            except (json.JSONDecodeError, TypeError):
                msg = str(err)
            hits.append(LimitHit(int(started_at), msg, retry))
        db.close()
    hits.sort(key=lambda h: h.ts)
    return hits


def fmt_local(ts: int) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")
