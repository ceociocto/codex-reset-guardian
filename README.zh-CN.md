# codex-reset-guardian

[English](README.md) | **中文**

> 审计与预测你的 OpenAI Codex 用量限额——别再浪费 banked 重置。

`codex-reset-guardian` 读取本机 Codex CLI / 桌面版已经写到磁盘上的数据
（`~/.codex/sessions/**/*.jsonl` 和 `~/.codex/thread_history_*.sqlite`），还原你的
5 小时窗口与周窗口用量，识别每一次被应用到账号上的重置（包括你自己手动触发的
banked 重置），预测你什么时候会撞限额，并告诉你——现在用一次 banked 重置是明智之举，
还是纯属浪费。

无需联网，无需任何凭据，对 `~/.codex` 只读。

## 它能知道什么

- **5h 窗口（primary）**：`used_percent`、`window_minutes=300`、`resets_at`
- **周窗口（secondary）**：`used_percent`、`window_minutes=10080`、`resets_at`
- **Turn 历史**：每个 turn 的状态，包括 `usage_limit_exceeded` 失败，
  错误信息里带官方给的重试时间
- **重置事件**：新窗口在旧窗口自然结束*之前*开始 = 有一次提前重置被应用了
  （可能是全局/社区重置，也可能是你消耗的一次 banked 重置）

## 安装

Python 3.9+（仅标准库，无需安装任何依赖）。

```bash
git clone <this-repo> codex-reset-guardian
cd codex-reset-guardian
python3 -m guardian analyze
```

## 使用

```bash
# 生成/刷新本地 sqlite 镜像并输出完整报告
python3 -m guardian analyze

# 监视模式：每 N 分钟轮询，超过阈值时发 macOS 通知
python3 -m guardian watch --interval 10 --warn 75 --critical 95

# 只看重置审计：列出每一次窗口提前重启及其归类
python3 -m guardian resets
```

## 重置归类的原理

Codex 有两个用量窗口。当我们观察到周窗口的自然结束时间是 `E1`，随后出现了一个
开始时间 `S2 < E1` 的新窗口，说明窗口被提前重置了：

- 开始时间与已知的**全局/社区重置**（OpenAI 官方公告）吻合 → 免费重置，什么都没消耗。
- 否则大概率是你自己在 设置 → 用量 里应用了一次 **banked 重置**——它还会把你的
  周重置日改到 `S2 + 7天`。

全局重置参照表在 `guardian/reference_resets.py`，欢迎随新公告补充。
工具还会标记**浪费的**重置：周窗口用量还很低（默认低于 40%）时就消耗 banked 重置，
几乎没刷新到任何东西。

## 关于"自动触发重置"

应用一次 banked 重置必须走带登录态的 UI（桌面版/CLI/网页的 设置 → 用量）。
直接用 CLI 的 bearer token 调后端接口会被 Cloudflare 403，所以本项目刻意止步于
决策环节：它告诉你*什么时候该触发*，并给出
`https://chatgpt.com/codex/settings/usage` 的跳转链接。如果你在跑 Hermes 之类的
Agent，`advise` 的输出是机器可读的，可以直接在其上接一层浏览器自动化。

## 已发现的 API 端点（给贡献者）

Codex CLI 二进制（`codex_cli_rs`）中引用了这些后端端点：

- `GET https://chatgpt.com/backend-api/api/codex/usage`
- `GET https://chatgpt.com/backend-api/api/codex/rate-limit-reset-credits`

两者都需要浏览器级 cookie；仅凭 CLI `auth.json` 里的 token 会得到 403。

## 许可

MIT
