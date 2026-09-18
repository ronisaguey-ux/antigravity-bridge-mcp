#!/usr/bin/env python3
"""
bridge_monitor.py — Bi-Directional Bridge Monitor between Antigravity and opencode.

Watches ~/.claude/inbox/messages.jsonl every 2 s and:
  - On a message addressed to "antigravity" → wakes Antigravity via the
    reactive watcher stream.
  - On a message addressed to "opencode" or "claude_code" → wakes opencode via
    oc_send.js --no-reply (queued, non-blocking, same mechanism as the
    Telegram wake watcher).

Run as a systemd --user service:
    ExecStart=/usr/bin/python3 /path/to/bridge_monitor.py

Log: /tmp/bridge_monitor.log
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, List

INBOX_FILE = Path.home() / ".claude" / "inbox" / "messages.jsonl"
LOG_FILE = Path("/tmp/bridge_monitor.log")

# opencode bridge helpers — same paths used by oc_wake_watch.sh
BUN_BIN = Path.home() / ".local" / "bin" / "bun"
OC_SEND_JS = Path.home() / ".local" / "lib" / "ocbridge" / "oc_send.js"

# Telegram notifier (optional — silently skipped if not configured)
_SEND_TELEGRAM_SH = Path("/home/roni/Roni_workspace/oculus/scripts/telegram-monitor/bin/send-telegram.sh")
_TELEGRAM_ENV = Path.home() / ".config" / "oculus" / "orchestrator.env"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def send_telegram_alert(text: str) -> None:
    """Send a Telegram notification if the send script and env file exist."""
    if not (_SEND_TELEGRAM_SH.exists() and _TELEGRAM_ENV.exists()):
        return
    try:
        cmd = f'set -a; source "{_TELEGRAM_ENV}"; set +a; bash "{_SEND_TELEGRAM_SH}" "{text}"'
        subprocess.run(
            cmd, shell=True, executable="/bin/bash",
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Wake opencode
# ---------------------------------------------------------------------------

def wake_opencode(msg: Dict[str, Any]) -> None:
    """
    Deliver an incoming Antigravity message to the opencode session.

    Uses oc_send.js --no-reply so the message is queued between turns
    (≈0 s, non-blocking) — identical to the Telegram wake path in
    oc_wake_watch.sh.  Does NOT block on the assistant run.
    """
    subject = msg.get("subject", "Antigravity Message")
    sender = msg.get("from", "antigravity")
    msg_id = msg.get("id", "")

    # Short, always-delivers wake text — the full content is in the inbox;
    # the agent is told to call check_inbox_from_antigravity to read it.
    wake_text = (
        f"⚡ [Antigravity Bridge] New message from {sender}: '{subject}' "
        f"(id={msg_id}). Call check_inbox_from_antigravity to read and reply."
    )

    if not BUN_BIN.exists() or not OC_SEND_JS.exists():
        log(f"WARN wake_opencode: bun or oc_send.js not found — cannot wake opencode for msg {msg_id}")
        return

    try:
        result = subprocess.run(
            [str(BUN_BIN), str(OC_SEND_JS), wake_text, "--no-reply"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=30,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            log(f"wake_opencode: queued wake for msg '{subject}' ({msg_id}) from {sender}")
        else:
            err = result.stderr.decode(errors="replace").strip()
            log(f"WARN wake_opencode: oc_send.js exited {result.returncode} for msg {msg_id}: {err}")
    except subprocess.TimeoutExpired:
        log(f"WARN wake_opencode: oc_send.js timed out for msg {msg_id}")
    except Exception as e:
        log(f"ERROR wake_opencode: {e}")


# ---------------------------------------------------------------------------
# Wake Antigravity
# ---------------------------------------------------------------------------

def wake_antigravity(msg: Dict[str, Any]) -> None:
    """
    Record a wake notification for Antigravity and fire a Telegram alert.

    Antigravity's reactive watcher (antigravity_watcher.py) polls the same
    inbox file and prints alerts to stdout, which the Antigravity CLI picks
    up as reactive wakeups — no extra work needed here beyond the Telegram
    ping for mobile notification.
    """
    subject = msg.get("subject", "opencode Notification")
    content = msg.get("content", "")
    sender = msg.get("from", "opencode")
    msg_id = msg.get("id", "")

    # Write a stream entry for the antigravity_watcher stream log
    stream_file = Path("/tmp/antigravity_bridge_stream.log")
    stream_entry = (
        f"\n📬 [ANTIGRAVITY BRIDGE ALERT] New message from opencode:\n"
        f"   ID: {msg_id}\n"
        f"   Subject: {subject}\n"
        f"   Content:\n{content}\n"
        f"{'-' * 60}\n"
    )
    try:
        with open(stream_file, "a", encoding="utf-8") as sf:
            sf.write(stream_entry)
            sf.flush()
    except Exception:
        pass

    send_telegram_alert(f"📬 opencode → Antigravity: [{subject}] {content[:100]}")
    log(f"wake_antigravity: alerted for msg '{subject}' ({msg_id}) from {sender}")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    log("=== Bridge Monitor Started ===")
    seen_ids: set = set()

    # Pre-populate seen IDs from existing read/sent messages so we don't
    # re-deliver historical entries on startup.
    if INBOX_FILE.exists():
        try:
            for line in INBOX_FILE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    data = json.loads(line)
                    if data.get("status") != "unread":
                        seen_ids.add(data.get("id"))
        except Exception:
            pass

    while True:
        try:
            if INBOX_FILE.exists():
                lines = INBOX_FILE.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg_id = msg.get("id")
                    if not msg_id or msg_id in seen_ids:
                        continue

                    to_recipient = msg.get("to")
                    status = msg.get("status")

                    if status == "unread":
                        if to_recipient in ("opencode", "claude_code"):
                            wake_opencode(msg)
                            seen_ids.add(msg_id)
                        elif to_recipient == "antigravity":
                            wake_antigravity(msg)
                            seen_ids.add(msg_id)
        except Exception as e:
            log(f"Loop error: {e}")

        time.sleep(2)


if __name__ == "__main__":
    main()
