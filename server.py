#!/usr/bin/env python3
"""
Antigravity Bridge MCP Server.
Provides a Model Context Protocol (MCP) interface over stdio allowing opencode,
Claude Code, or Antigravity to send messages, check inboxes, and reply bidirectionally.

Zero external dependencies — standard library Python only.

Usage (stdio MCP):
    python3 server.py
"""

import sys
import os
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

CONFIG_FILE = Path.home() / ".config" / "antigravity-bridge" / "config.json"
INBOX_DIR = Path.home() / ".claude" / "inbox"
INBOX_FILE = INBOX_DIR / "messages.jsonl"


def get_default_from_agent() -> str:
    if os.environ.get("BRIDGE_AGENT_NAME"):
        return os.environ["BRIDGE_AGENT_NAME"]
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                c = json.load(f)
                target = c.get("target_agent", "").lower()
                if target in ("opencode", "openbot"):
                    return "opencode"
                if target in ("claude", "claude_code"):
                    return "claude_code"
        except Exception:
            pass
    return "opencode"


def ensure_inbox():
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    if not INBOX_FILE.exists():
        INBOX_FILE.touch()


def read_all_messages() -> List[Dict[str, Any]]:
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
    ensure_inbox()
    temp_file = INBOX_FILE.with_name(f"{INBOX_FILE.name}.tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    temp_file.replace(INBOX_FILE)


def append_message(msg: Dict[str, Any]) -> None:
    ensure_inbox()
    with open(INBOX_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Peer -> Antigravity actions
# ---------------------------------------------------------------------------

def send_message_to_antigravity(content: str, subject: str = "Message", from_agent: Optional[str] = None) -> Dict[str, Any]:
    sender = from_agent or get_default_from_agent()
    msg = {
        "id": f"msg_{int(time.time())}_{uuid.uuid4().hex[:8]}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "from": sender,
        "to": "antigravity",
        "subject": subject,
        "content": content,
        "status": "unread",
    }
    append_message(msg)
    return {"success": True, "message_id": msg["id"], "timestamp": msg["timestamp"]}


def check_inbox_for_peer(mark_read: bool = True) -> List[Dict[str, Any]]:
    messages = read_all_messages()
    incoming = [m for m in messages if m.get("to") in ("opencode", "claude_code", "peer") and m.get("from") == "antigravity"]
    if mark_read:
        updated = False
        for m in messages:
            if m.get("to") in ("opencode", "claude_code", "peer") and m.get("from") == "antigravity" and m.get("status") == "unread":
                m["status"] = "read"
                updated = True
        if updated:
            write_all_messages(messages)
    return incoming


def check_inbox_for_antigravity(mark_read: bool = True) -> List[Dict[str, Any]]:
    messages = read_all_messages()
    incoming = [m for m in messages if m.get("to") == "antigravity"]
    if mark_read:
        updated = False
        for m in messages:
            if m.get("to") == "antigravity" and m.get("status") == "unread":
                m["status"] = "read"
                updated = True
        if updated:
            write_all_messages(messages)
    return incoming


def check_inbox_from_antigravity(mark_read: bool = True) -> List[Dict[str, Any]]:
    return check_inbox_for_peer(mark_read=mark_read)


def reply_to_antigravity(reply_to_id: str, content: str, from_agent: Optional[str] = None) -> Dict[str, Any]:
    sender = from_agent or get_default_from_agent()
    messages = read_all_messages()
    original = next((m for m in messages if m.get("id") == reply_to_id), None)
    subject = f"Re: {original.get('subject', 'Message')}" if original else "Reply"

    msg = {
        "id": f"msg_{int(time.time())}_{uuid.uuid4().hex[:8]}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "from": sender,
        "to": "antigravity",
        "subject": subject,
        "content": content,
        "reply_to": reply_to_id,
        "status": "unread",
    }
    append_message(msg)
    return {"success": True, "message_id": msg["id"], "reply_to": reply_to_id}


# ---------------------------------------------------------------------------
# Antigravity -> Peer actions (opencode / claude_code / peer)
# ---------------------------------------------------------------------------

def send_message_to_peer(content: str, subject: str = "Message", recipient: str = "auto") -> Dict[str, Any]:
    target = recipient
    if target == "auto":
        target = "opencode"
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    c = json.load(f)
                    t = c.get("target_agent", "auto").lower()
                    if t in ("claude", "claude_code"):
                        target = "claude_code"
                    elif t in ("opencode", "openbot"):
                        target = "opencode"
                    elif t == "both":
                        target = "peer"
            except Exception:
                pass

    msg = {
        "id": f"msg_{int(time.time())}_{uuid.uuid4().hex[:8]}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "from": "antigravity",
        "to": target,
        "subject": subject,
        "content": content,
        "status": "unread",
    }
    append_message(msg)
    return {"success": True, "message_id": msg["id"], "target": target}


def get_conversation_history(limit: int = 50) -> List[Dict[str, Any]]:
    messages = read_all_messages()
    messages.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    return messages[:limit]


# ---------------------------------------------------------------------------
# MCP Definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "send_message_to_antigravity",
        "description": "Send a message to the Antigravity IDE agent (for deep reasoning, architectural review, or paired coding).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Message content."},
                "subject": {"type": "string", "description": "Subject line.", "default": "Message"},
                "from_agent": {"type": "string", "description": "Sender identity ('opencode' or 'claude_code')."},
            },
            "required": ["content"],
        },
    },
    {
        "name": "check_inbox_from_antigravity",
        "description": "Check for messages received from Antigravity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mark_read": {"type": "boolean", "description": "Mark unread messages as read.", "default": True},
            },
        },
    },
    {
        "name": "reply_to_antigravity",
        "description": "Send a reply to a specific message from Antigravity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reply_to_id": {"type": "string", "description": "ID of the message being replied to."},
                "content": {"type": "string", "description": "Reply content."},
                "from_agent": {"type": "string", "description": "Sender identity ('opencode' or 'claude_code')."},
            },
            "required": ["reply_to_id", "content"],
        },
    },
    {
        "name": "send_message_to_peer",
        "description": "Send a message to the peer agent (opencode, Claude Code, or both based on configuration).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Message content."},
                "subject": {"type": "string", "description": "Subject line.", "default": "Message"},
                "recipient": {"type": "string", "description": "Recipient: 'auto', 'opencode', 'claude_code', or 'peer'.", "default": "auto"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "send_message_to_opencode",
        "description": "Send a message from Antigravity specifically to the opencode agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message text."},
                "subject": {"type": "string", "description": "Subject line.", "default": "General"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "send_message_to_claude",
        "description": "Send a message from Antigravity specifically to Claude Code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message text."},
                "subject": {"type": "string", "description": "Subject line.", "default": "General"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "check_inbox_from_claude",
        "description": "Check for messages received from Claude Code / peer agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mark_read": {"type": "boolean", "description": "Mark unread messages as read.", "default": True},
            },
        },
    },
    {
        "name": "check_inbox_from_opencode",
        "description": "Check for messages received from opencode.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mark_read": {"type": "boolean", "description": "Mark unread messages as read.", "default": True},
            },
        },
    },
    {
        "name": "reply_to_claude",
        "description": "Reply to a message from Claude Code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Message ID."},
                "reply": {"type": "string", "description": "Reply body."},
            },
            "required": ["message_id", "reply"],
        },
    },
    {
        "name": "reply_to_opencode",
        "description": "Reply to a message from opencode.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Message ID."},
                "reply": {"type": "string", "description": "Reply body."},
            },
            "required": ["message_id", "reply"],
        },
    },
    {
        "name": "get_conversation_history",
        "description": "Get chronological conversation history across the bridge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of messages to return.", "default": 50},
            },
        },
    },
]

TOOL_HANDLERS = {
    "send_message_to_antigravity": lambda a: send_message_to_antigravity(**a),
    "check_inbox_from_antigravity": lambda a: check_inbox_from_antigravity(**a),
    "reply_to_antigravity": lambda a: reply_to_antigravity(**a),
    "send_message_to_peer": lambda a: send_message_to_peer(**a),
    "send_message_to_opencode": lambda a: send_message_to_peer(content=a.get("message", ""), subject=a.get("subject", "General"), recipient="opencode"),
    "send_message_to_claude": lambda a: send_message_to_peer(content=a.get("message", ""), subject=a.get("subject", "General"), recipient="claude_code"),
    "check_inbox_from_claude": lambda a: check_inbox_for_antigravity(mark_read=a.get("mark_read", True) if "mark_read" in a else (not a.get("unread_only", True))),
    "check_inbox_from_opencode": lambda a: check_inbox_for_antigravity(mark_read=a.get("mark_read", True) if "mark_read" in a else (not a.get("unread_only", True))),
    "reply_to_claude": lambda a: send_message_to_peer(content=a.get("reply", ""), subject="Re: Message", recipient="claude_code"),
    "reply_to_opencode": lambda a: send_message_to_peer(content=a.get("reply", ""), subject="Re: Message", recipient="opencode"),
    "get_conversation_history": lambda a: get_conversation_history(**a),
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
                "serverInfo": {"name": "antigravity-bridge", "version": "1.1.0"},
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
