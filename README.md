# antigravity-bridge-mcp

Allows peer agents (**opencode**, **Claude Code**, or any MCP-compatible client) to communicate bidirectionally with the **Antigravity IDE CLI** agent.

## Features

- **Bi-directional wakeups**:
  - Peer agent -> Antigravity: alerts Antigravity via reactive stream log and optional Telegram notification.
  - Antigravity -> Peer agent: alerts opencode via `oc_send.js --no-reply` (inter-turn queuing) or Claude Code via tmux session injection.
- **Configurable target**:
  - `auto`: Automatically routes by message recipient or detects whether Claude Code (tmux) or opencode is active.
  - `opencode`: Routes all peer wakeups to opencode.
  - `claude`: Routes all peer wakeups to Claude Code.
  - `both`: Broadcasts to both opencode and Claude Code simultaneously.

---

## Files

| File | Purpose |
|------|---------|
| `server.py` | MCP stdio JSON-RPC server providing bridge tools to agents. |
| `bridge_monitor.py` | Daemon that watches `~/.claude/inbox/messages.jsonl` and executes wakeups. |
| `config.json` | Configuration file template for target agent and paths. |
| `antigravity-bridge.service` | systemd `--user` service unit. |

---

## Configuration (`config.json`)

Stored at `~/.config/antigravity-bridge/config.json`:

```json
{
  "target_agent": "auto",
  "claude": {
    "enabled": true,
    "tmux_session": "claude",
    "inbox_file": "~/Roni_workspace/audits_plans/claude_main_inbox.json"
  },
  "opencode": {
    "enabled": true,
    "bun_bin": "~/.local/bin/bun",
    "oc_send_js": "~/.local/lib/ocbridge/oc_send.js"
  },
  "telegram": {
    "enabled": true,
    "send_script": "~/Roni_workspace/oculus/scripts/telegram-monitor/bin/send-telegram.sh",
    "env_file": "~/.config/oculus/orchestrator.env"
  }
}
```

### Overrides

- **Environment Variable**: `export BRIDGE_TARGET_AGENT=opencode` (or `claude`, `both`, `auto`)
- **CLI Flag**: `python3 bridge_monitor.py --target [auto|opencode|claude|both]`

---

## MCP Tools

### For Peer Agents (opencode / Claude Code):
- `send_message_to_antigravity`: Send task requests or questions to Antigravity.
- `check_inbox_from_antigravity`: Read responses or directives from Antigravity.
- `reply_to_antigravity`: Threaded reply to a specific Antigravity message.
- `get_conversation_history`: Retrieve chronological message history.

### For Antigravity:
- `send_message_to_peer`: Generic message to configured peer agent.
- `send_message_to_opencode`: Specifically target opencode.
- `send_message_to_claude`: Specifically target Claude Code.
- `check_inbox_from_claude` / `check_inbox_from_opencode`: Retrieve incoming messages.
- `reply_to_claude` / `reply_to_opencode`: Send threaded replies.

---

## Deployment & Setup

```bash
# 1. Clone or copy files
mkdir -p ~/.config/antigravity-bridge
cp config.json ~/.config/antigravity-bridge/config.json
cp bridge_monitor.py ~/.config/antigravity-bridge/bridge_monitor.py
cp antigravity-bridge.service ~/.config/systemd/user/antigravity-bridge.service

# 2. Reload and enable systemd user daemon
systemctl --user daemon-reload
systemctl --user enable --now antigravity-bridge.service
```

### Add to opencode config (`~/.config/opencode/opencode.json`):

```json
"mcp": {
  "antigravity-bridge": {
    "type": "local",
    "command": ["python3", "/path/to/server.py"],
    "enabled": true
  }
}
```

### Add to Claude Code (`claude mcp add`):

```bash
claude mcp add antigravity-bridge python3 /path/to/server.py
```
