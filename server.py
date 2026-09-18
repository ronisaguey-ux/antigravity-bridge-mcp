#!/usr/bin/env python3
"""
Antigravity Bridge MCP Server.
Provides a Model Context Protocol (MCP) interface over stdio allowing opencode
(and other agents) to send messages to Antigravity, check its inbox for replies,
view conversation threads, and conduct two-way messaging.

Zero external dependencies — standard library Python only.

Usage (stdio MCP):
    python3 server.py

In opencode.json:
    "mcp": {
        "antigravity-bridge": {
            "type": "local",
            "command": ["python3", "/path/to/server.py"],
            "enabled": true
        }
    }
"""

import sys
import os
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

INBOX_DIR = Path.home() / ".claude" / "inbox"
INBOX_FILE = INBOX_DIR / "messages.jsonl"


def ensure_inbox():
    """Ensure inbox directory and storage file exist."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    if not INBOX_FILE.exists():
        INBOX_FILE.touch()


def read_all_messages() -> List[Dict[str, Any]]:
    """Read all messages from the inbox storage."""
    ensure_inbox()
    messages = []
    try:
        with open(INBOX_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    try:
                        messages.append(json.loads(line_str))
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        sys.stderr.write(f"Error reading inbox: {e}\n")
    return messages


def write_all_messages(messages: List[Dict[str, Any]]) -> None:
    """Overwrite messages file atomically."""
    ensure_inbox()
    temp_file = INBOX_FILE.with_name(f"{INBOX_FILE.name}.tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    temp_file.replace(INBOX_FILE)


def append_message(msg: Dict[str, Any]) -> None:
    """Append a single message to inbox storage."""
    ensure_inbox()
    with open(INBOX_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")


def send_message_to_antigravity(content: str, subject: str = "Message", from_agent: str = "opencode") -> Dict[str, Any]:
    """Send a message to Antigravity."""
    msg = {
        "id": f"msg_{int(time.time())}_{uuid.uuid4().hex[:8]}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "from": from_agent,
        "to": "antigravity",
        "subject": subject,
        "content": content,
        "status": "unread",
    }
    append_message(msg)
    return {"success": True, "message_id": msg["id"], "timestamp": msg["timestamp"]}


def check_inbox_from_antigravity(mark_read: bool = True) -> List[Dict[str, Any]]:
    """Check inbox for messages from Antigravity."""
    messages = read_all_messages()
    incoming = [m for m in messages if m.get("to") in ("opencode", "claude_code") and m.get("from") == "antigravity"]

    if mark_read:
        updated = False
        for m in messages:
            if m.get("to") in ("opencode", "claude_code") and m.get("from") == "antigravity" and m.get("status") == "unread":
                m["status"] = "read"
                updated = True
        if updated:
            write_all_messages(messages)

    return incoming


def get_conversation_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent conversation history between this agent and Antigravity."""
    messages = read_all_messages()
    bridge_msgs = [
        m for m in messages
        if m.get("to") in ("antigravity", "opencode", "claude_code")
        or m.get("from") in ("antigravity", "opencode", "claude_code")
    ]
    bridge_msgs.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    return bridge_msgs[:limit]


def reply_to_antigravity(reply_to_id: str, content: str, from_agent: str = "opencode") -> Dict[str, Any]:
    """Reply to a specific message from Antigravity."""
    messages = read_all_messages()
    original = next((m for m in messages if m.get("id") == reply_to_id), None)
    subject = f"Re: {original.get('subject', 'Message')}" if original else "Reply"

    msg = {
        "id": f"msg_{int(time.time())}_{uuid.uuid4().hex[:8]}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "from": from_agent,
        "to": "antigravity",
        "subject": subject,
        "content": content,
        "reply_to": reply_to_id,
        "status": "unread",
    }
    append_message(msg)
    return {"success": True, "message_id": msg["id"], "reply_to": reply_to_id}


# ---------------------------------------------------------------------------
# MCP JSON-RPC 2.0 server (stdio transport)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "send_message_to_antigravity",
        "description": "Send a message to the Antigravity IDE agent. Use this to request deep reasoning, code review, architecture advice, or to delegate tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The message body to send."},
                "subject": {"type": "string", "description": "Short subject line for the message.", "default": "Message"},
                "from_agent": {"type": "string", "description": "Sender identity label.", "default": "opencode"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "check_inbox_from_antigravity",
        "description": "Check for new messages from Antigravity. Call this after receiving a bridge alert.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mark_read": {"type": "boolean", "description": "Mark retrieved messages as read.", "default": True},
            },
        },
    },
    {
        "name": "get_conversation_history",
        "description": "Retrieve recent message history between this agent and Antigravity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max number of messages to return.", "default": 50},
            },
        },
    },
    {
        "name": "reply_to_antigravity",
        "description": "Send a reply to a specific Antigravity message, threading it by message ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reply_to_id": {"type": "string", "description": "The ID of the message to reply to."},
                "content": {"type": "string", "description": "Reply body."},
                "from_agent": {"type": "string", "description": "Sender identity label.", "default": "opencode"},
            },
            "required": ["reply_to_id", "content"],
        },
    },
]

TOOL_HANDLERS = {
    "send_message_to_antigravity": lambda args: send_message_to_antigravity(**args),
    "check_inbox_from_antigravity": lambda args: check_inbox_from_antigravity(**args),
    "get_conversation_history": lambda args: get_conversation_history(**args),
    "reply_to_antigravity": lambda args: reply_to_antigravity(**args),
}


def write_response(obj: Dict[str, Any]) -> None:
    line = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def handle_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "antigravity-bridge", "version": "1.0.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }
        try:
            result = handler(tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}],
                    "isError": False,
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                },
            }

    if req_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def main():
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            req = json.loads(raw_line)
        except json.JSONDecodeError as e:
            write_response({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}})
            continue
        resp = handle_request(req)
        if resp is not None:
            write_response(resp)


if __name__ == "__main__":
    main()
