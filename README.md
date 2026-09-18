# antigravity-bridge-mcp

Allows agents (opencode, Claude Code, or any MCP-compatible agent) to communicate bidirectionally with the **Antigravity IDE CLI** agent.

## Files

| File | Purpose |
|------|---------|
| `server.py` | MCP server (stdio JSON-RPC 2.0). Drop this into your agent's MCP config. |
| `bridge_monitor.py` | Background daemon. Watches `~/.claude/inbox/messages.jsonl` and wakes the right agent on new messages. |
| `antigravity-bridge.service` | systemd `--user` unit for running `bridge_monitor.py` as an always-on daemon. |

## MCP Tools

| Tool | Description |
|------|-------------|
| `send_message_to_antigravity` | Send a message to Antigravity. |
| `check_inbox_from_antigravity` | Check for replies from Antigravity. |
| `reply_to_antigravity` | Thread a reply to a specific message ID. |
| `get_conversation_history` | Get recent message history. |

## Setup

### 1. Add to opencode

In `~/.config/opencode/opencode.json`:

```json
"mcp": {
    "antigravity-bridge": {
        "type": "local",
        "command": ["python3", "/path/to/server.py"],
        "enabled": true
    }
}
```

### 2. Run the wake daemon

```bash
cp bridge_monitor.py ~/.config/antigravity-bridge/bridge_monitor.py
cp antigravity-bridge.service ~/.config/systemd/user/antigravity-bridge.service
systemctl --user daemon-reload
systemctl --user enable --now antigravity-bridge.service
```

## Wake-up flow

```
opencode agent
    │  calls send_message_to_antigravity(...)
    ▼
~/.claude/inbox/messages.jsonl  ◄── bridge_monitor.py (polls every 2 s)
    │                                       │
    │  to="antigravity"                     │  to="opencode"
    ▼                                       ▼
antigravity_watcher.py               oc_send.js --no-reply
(reactive stdout alert)          (queues wake in opencode session)
    │                                       │
    ▼                                       ▼
Antigravity IDE wakes up           opencode agent wakes up
```

## Inbox format

Messages are newline-delimited JSON in `~/.claude/inbox/messages.jsonl`:

```json
{
    "id": "msg_1726662000_a1b2c3d4",
    "timestamp": "2026-09-18T16:00:00Z",
    "from": "opencode",
    "to": "antigravity",
    "subject": "Code review request",
    "content": "Can you review this architecture?",
    "status": "unread"
}
```
