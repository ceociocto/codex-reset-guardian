# codex-reset-guardian

**English** | [中文](README.zh-CN.md)

> Audit and forecast your OpenAI Codex usage limits — and stop wasting banked resets.

`codex-reset-guardian` reads the data your local Codex CLI/Desktop already writes to disk
(`~/.codex/sessions/**/*.jsonl` and `~/.codex/thread_history_*.sqlite`), reconstructs your
5-hour and weekly usage windows, detects every reset that was applied to your account
(including banked ones you triggered yourself), forecasts when you will hit your limits,
and tells you when using a banked reset is a good idea — or a waste.

No network access required. No credentials required. Read-only against `~/.codex`.

## What it knows

- **5h window (primary)**: `used_percent`, `window_minutes=300`, `resets_at`
- **Weekly window (secondary)**: `used_percent`, `window_minutes=10080`, `resets_at`
- **Turn history**: status per turn, including `usage_limit_exceeded` failures with the
  server-provided retry time
- **Reset events**: a new window starting *before* the previous window's natural end means
  an early reset was applied (global/community reset, or a banked reset you consumed)

## Install

Python 3.9+ (stdlib only, nothing to install).

```bash
git clone <this-repo> codex-reset-guardian
cd codex-reset-guardian
python3 guardian.py analyze
```

## Usage

```bash
# Build/refresh the local sqlite mirror and print a full report
python3 guardian.py analyze

# Watch mode: poll every N minutes, macOS notification when thresholds cross
python3 guardian.py watch --interval 10 --warn 75 --critical 95

# Reset audit only: every early restart of your windows, classified
python3 guardian.py resets
```

## How reset classification works

Codex exposes two windows. When we observe a weekly window ending `E1` and later a window
that started `S2 < E1`, something reset the window early:

- If the start time matches a known **global/community reset** (OpenAI announcements),
  it was free — nothing was consumed.
- Otherwise it was most likely a **banked reset you applied** (Settings → Usage), which
  also moved your weekly reset day to `S2 + 7d`.

The reference list of global resets lives in `guardian/reference_resets.py` and is easy to
extend. The tool also flags *wasted* resets: a banked reset consumed while the weekly
window was below the waste threshold (default 40%) refreshed almost nothing.

## Auto-triggering a banked reset

Applying a banked reset must go through an authenticated UI (Desktop/CLI/web
Settings → Usage). Direct API calls with the CLI bearer token are blocked by Cloudflare,
so this project deliberately stops at the decision: it tells you *when* to trigger and
links you to `https://chatgpt.com/codex/settings/usage`. If you run Hermes/another agent,
`advise` output is machine-readable enough to wire a browser automation on top.

## Discovered API surface (for contributors)

The Codex CLI binary (`codex_cli_rs`) references these backend endpoints:

- `GET https://chatgpt.com/backend-api/api/codex/usage`
- `GET https://chatgpt.com/backend-api/api/codex/rate-limit-reset-credits`

Both need browser-grade cookies; the CLI's `auth.json` bearer token alone gets a 403.

## License

MIT
