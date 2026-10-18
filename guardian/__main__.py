"""codex-reset-guardian — CLI entry point."""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
import time

from .parser import (parse_sessions, parse_limit_hits, group_windows,
                     current_window_samples, fmt_local)
from .resets import detect_resets, format_resets
from .forecast import forecast, advise, format_forecast

USAGE_SETTINGS_URL = "https://chatgpt.com/codex/settings/usage"


def cmd_analyze(args) -> int:
    s5, sw = parse_sessions(args.codex_home)
    w5, ww = group_windows(s5), group_windows(sw)
    hits = parse_limit_hits(args.codex_home)
    resets = detect_resets(ww)

    print("=" * 72)
    print(f"codex-reset-guardian — {datetime.datetime.now():%Y-%m-%d %H:%M} "
          f"({len(s5)} samples, {len(w5)} 5h-windows, {len(ww)} weekly-windows, "
          f"{len(hits)} limit hits)")
    print("=" * 72)

    print("\n■ LIMIT HITS (turns failed with usage_limit_exceeded)")
    if hits:
        for h in hits:
            print(f"  {fmt_local(h.ts)}  {h.message[:110]}")
    else:
        print("  none")

    print("\n■ CURRENT WINDOWS + FORECAST")
    fc5 = forecast(current_window_samples(s5, lookback_h=6), "5h")
    fcw = forecast(current_window_samples(sw, lookback_h=24 * 8), "weekly")
    print("  " + format_forecast(fc5))
    print("  " + format_forecast(fcw))

    print("\n■ BANKED-RESET ADVICE")
    for line in advise(fc5, fcw, ww[-1].peak if ww else 0).splitlines():
        print("  " + line)
    print(f"  Trigger manually at: {USAGE_SETTINGS_URL}")

    print("\n■ RESET AUDIT (early window restarts)")
    for line in format_resets(resets).splitlines():
        print("  " + line)
    if resets:
        banked = [r for r in resets if r.kind == "banked"]
        wasted = [r for r in banked if r.wasted]
        print(f"\n  Banked resets consumed: {len(banked)}  (of which wasted: {len(wasted)})")

    print("\n■ 5H WINDOW HISTORY (peak usage per window)")
    for w in w5[-12:]:
        print(f"  reset@{fmt_local(w.resets_at)}  peak={w.peak:5.1f}%  "
              f"first={w.first_seen[:16] if w.first_seen else '?'}")
    return 0


def cmd_resets(args) -> int:
    _, sw = parse_sessions(args.codex_home)
    resets = detect_resets(group_windows(sw))
    print(format_resets(resets))
    if not resets:
        return 0
    banked = [r for r in resets if r.kind == "banked"]
    wasted = [r for r in banked if r.wasted]
    print(f"\nBanked consumed: {len(banked)} | wasted: {len(wasted)}")
    return 0


def notify(title: str, message: str) -> None:
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{message}" with title "{title}"'],
                       timeout=5, capture_output=True)
    except Exception:
        pass


def cmd_watch(args) -> int:
    print(f"watching every {args.interval}min (warn>{args.warn}% critical>{args.critical}%), Ctrl-C to stop")
    last_state = {}
    while True:
        s5, sw = parse_sessions(args.codex_home)
        fc5 = forecast(current_window_samples(s5, lookback_h=6), "5h")
        fcw = forecast(current_window_samples(sw, lookback_h=24 * 8), "weekly")
        now = datetime.datetime.now().strftime("%H:%M")
        for fc in (fc5, fcw):
            if fc is None:
                continue
            key = fc.window
            level = "ok" if fc.used_percent < args.warn else (
                "warn" if fc.used_percent < args.critical else "critical")
            if last_state.get(key) != level:
                last_state[key] = level
            elif level == "ok":
                continue
            print(f"[{now}] {fc.window}: {fc.used_percent:.0f}% ({level})")
            if level == "critical":
                notify("Codex 限额告急",
                       f"{fc.window} 窗口已用 {fc.used_percent:.0f}%，"
                       f"重置于 {fmt_local(fc.resets_at)}")
        time.sleep(args.interval * 60)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="guardian",
                                description="Audit and forecast Codex usage limits & resets")
    p.add_argument("--codex-home", default="~/.codex", help="path to ~/.codex")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("analyze", help="full report")
    sub.add_parser("resets", help="reset audit only")
    pw = sub.add_parser("watch", help="poll and notify")
    pw.add_argument("--interval", type=int, default=10, help="minutes")
    pw.add_argument("--warn", type=float, default=75)
    pw.add_argument("--critical", type=float, default=95)

    args = p.parse_args(argv)
    import os
    args.codex_home = os.path.expanduser(args.codex_home)

    if args.cmd == "analyze":
        return cmd_analyze(args)
    if args.cmd == "resets":
        return cmd_resets(args)
    if args.cmd == "watch":
        return cmd_watch(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
