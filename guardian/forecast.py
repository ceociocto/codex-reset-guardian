"""Forecast: burn rate and time-to-limit for the current 5h/weekly windows."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import List, Optional

from .parser import Window, LimitSample, fmt_local, _parse_iso


@dataclass
class Forecast:
    window: str            # "5h" | "weekly"
    used_percent: float
    resets_at: int
    resets_in_h: float
    burn_rate_pct_per_h: float
    eta_limit_h: Optional[float]   # hours until 100% at current burn rate, None if <=0
    will_hit_before_reset: bool


def forecast(window_samples: List[LimitSample], label: str) -> Optional[Forecast]:
    """Estimate burn rate from the last hour of samples; extrapolate to 100%."""
    if not window_samples:
        return None
    samples = sorted(window_samples, key=lambda s: s.ts or "")
    latest = samples[-1]
    last_dt = _parse_iso(latest.ts)
    if last_dt is None:
        return None
    now = datetime.datetime.now()
    # samples from the last 60 minutes of observation
    recent = [s for s in samples
              if (t := _parse_iso(s.ts)) and (last_dt - t).total_seconds() <= 3600]
    burn = 0.0
    if len(recent) >= 2:
        first, last = recent[0], recent[-1]
        t0, t1 = _parse_iso(first.ts), _parse_iso(last.ts)
        dt_h = (t1 - t0).total_seconds() / 3600
        if dt_h > 0.05:
            burn = max(0.0, (last.percent - first.percent) / dt_h)
    resets_dt = datetime.datetime.fromtimestamp(latest.resets_at)
    resets_in_h = (resets_dt - now).total_seconds() / 3600
    eta = None
    if burn > 0.1:
        eta = (100.0 - latest.percent) / burn
    return Forecast(
        window=label,
        used_percent=latest.percent,
        resets_at=latest.resets_at,
        resets_in_h=resets_in_h,
        burn_rate_pct_per_h=burn,
        eta_limit_h=eta,
        will_hit_before_reset=bool(eta is not None and eta < resets_in_h),
    )


def advise(fc5: Optional[Forecast], fcw: Optional[Forecast],
           weekly_peak: float, waste_threshold: float = 40.0) -> str:
    """Decide whether triggering a banked reset right now makes sense."""
    lines = []
    trigger = False
    if fc5 and fc5.will_hit_before_reset:
        lines.append(
            f"⚠️  5h window will hit 100% in ~{fc5.eta_limit_h:.1f}h, "
            f"but resets only in {fc5.resets_in_h:.1f}h — you WILL be blocked.")
        trigger = True
    if fcw and fcw.will_hit_before_reset:
        lines.append(
            f"⚠️  Weekly window will hit 100% in ~{fcw.eta_limit_h:.1f}h, "
            f"but resets only in {fcw.resets_in_h:.1f}h — a banked reset would refresh BOTH windows.")
        trigger = True
    if trigger:
        lines.append("👉 VERDICT: USE a banked reset (Settings → Usage). "
                     "It refreshes 5h+weekly and moves weekly reset day to today+7d.")
    else:
        lines.append("✅ VERDICT: HOLD — natural resets cover you. A banked reset now would be wasted.")
    return "\n".join(lines)


def format_forecast(fc: Optional[Forecast]) -> str:
    if fc is None:
        return "(no data)"
    eta = f"{fc.eta_limit_h:.1f}h" if fc.eta_limit_h is not None else "n/a"
    hit = "  ← WILL HIT LIMIT FIRST" if fc.will_hit_before_reset else ""
    return (f"{fc.window:<7} used {fc.used_percent:5.1f}% | resets in {fc.resets_in_h:5.1f}h "
            f"(@{fmt_local(fc.resets_at)}) | burn {fc.burn_rate_pct_per_h:5.1f}%/h | "
            f"ETA 100%: {eta}{hit}")
