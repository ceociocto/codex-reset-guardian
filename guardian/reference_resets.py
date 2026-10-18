"""Known global/community Codex resets (UTC timestamps).

Sources: OpenAI status page, @thsottiaux (Tibo) announcements, codexlimits.com history.
A window restart that matches (within tolerance) one of these was FREE —
it did not consume a banked reset.

Format: unix seconds (UTC) of the moment the reset landed.
Extend this list as new public resets are announced.
"""

GLOBAL_RESETS_UTC = [
    # 2026-10-07 05:30 UTC — community-vote reset (day 2 of 28-day challenge)
    1791375000,
    # 2026-10-07 banked grant day (not a reset per se; grants don't restart windows)
    # 2026-10-11 global reset (day 6) — observed restart 2026-10-11 04:19 UTC
    # (= local 12:19 CST), i.e. unix 1791692340
    1791692340,
    # 2026-10-13 global reset (day 8)
    1791892800,  # approx 2026-10-13 06:00 UTC
    # 2026-10-15 global reset (06:28 UTC confirmed by Tibo)
    1792062480,
]

# A window restart counts as "global" if it began within this many seconds of a
# known global reset (announcements roll out over ~an hour).
GLOBAL_RESET_TOLERANCE_S = 3 * 3600
