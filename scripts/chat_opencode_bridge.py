#!/usr/bin/env python3
"""chat_opencode_bridge — connect opencode to the lgwks-human CHAT pane.

The cockpit's CHAT pane emits `human_message` events onto the daemon bus and
renders `agent_message` replies. This bridge closes the loop: it tails
`daemon-events.db` for human messages, runs them through opencode, and emits the
reply back as an `agent_message` (agent_id=opencode) that the pane renders.

Run it alongside the cockpit:

    python3 scripts/chat_opencode_bridge.py                 # default model
    OC_MODEL=zai-coding-plan/glm-4.6 python3 scripts/chat_opencode_bridge.py

Then open the cockpit (`cargo run -p lgwks-human`), press Ctrl-T (CHAT), `i`,
type, Enter — opencode answers in the pane.

Design notes:
- Only `human_message` events with a human origin (actor=human or
  agent_id=lgwks-human) are answered, so peer/agent chatter is ignored and there
  is no reply loop (agent_message != human_message).
- Starts at the current bus tail; it never replays history on boot.
- opencode runs rooted at this repo (LOCAL — never a gdrive mount, which hangs).
"""
import json
import os
import re
import pathlib
import sqlite3
import subprocess
import sys
import time

REPO   = pathlib.Path(__file__).resolve().parent.parent
DB     = REPO / "store/daemon/daemon-events.db"
STATE  = REPO / "store/daemon/.chat_opencode_bridge.seq"
PY     = REPO / ".venv/bin/python"
LGWKS  = REPO / "lgwks"
POLL_S = float(os.environ.get("BRIDGE_POLL", "1.5"))
OC_MODEL = os.environ.get("OC_MODEL", "").strip()
OC_TIMEOUT = int(os.environ.get("OC_TIMEOUT", "180"))

ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
# opencode prints a "> build · <model>" banner line before the reply.
BANNER = re.compile(r"^\s*>\s*\w+\s*·")


def log(msg: str) -> None:
    print(f"[bridge] {msg}", flush=True)


def clean_reply(raw: str) -> str:
    lines = []
    for ln in ANSI.sub("", raw).splitlines():
        if BANNER.match(ln):
            continue
        lines.append(ln.rstrip())
    return "\n".join(l for l in lines if l.strip()).strip()


def run_opencode(message: str) -> str:
    cmd = ["opencode", "run"]
    if OC_MODEL:
        cmd += ["--model", OC_MODEL]
    cmd.append(message)
    try:
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=OC_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"(opencode timed out after {OC_TIMEOUT}s)"
    out = clean_reply(r.stdout or "") or clean_reply(r.stderr or "")
    return out or "(opencode: empty reply)"


def emit_agent_message(text: str, tenant: str, session: str) -> None:
    # The chat pane renders {human_message, agent_message, transcript_turn}; of those
    # the daemon's emit --kind whitelist only accepts transcript_turn for an agent reply
    # (agent_message is render-only, not an emittable event kind). So replies ride as
    # transcript_turn, tagged agent_id=opencode so the pane badges them as opencode.
    payload = json.dumps({"message": text, "role": "assistant", "from": "opencode"})
    args = [
        str(PY), str(LGWKS), "ops", "daemon", "emit",
        "--kind", "transcript_turn",
        "--lane", "ingress",
        "--scope", "shared_referee",
        "--actor", "agent",
        "--client", "unknown",  # daemon whitelists client; opencode rides as unknown (agent_id carries the name)
        "--tenant", tenant,
        "--session-id", session,
        "--agent-id", "opencode",
    ]
    r = subprocess.run(args, cwd=REPO, input=payload, text=True, capture_output=True)
    if r.returncode != 0:
        log(f"emit failed (exit {r.returncode}): {r.stderr.strip()[:200]}")


def is_human(evt: dict) -> bool:
    return evt.get("actor") == "human" or evt.get("agent_id") == "lgwks-human"


def tail_rowid(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COALESCE(MAX(rowid), 0) FROM daemon_events").fetchone()[0]


def poll_once(seq: int) -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT rowid, raw_json FROM daemon_events WHERE rowid > ? ORDER BY rowid",
            (seq,),
        ).fetchall()
    finally:
        con.close()
    for rowid, raw in rows:
        seq = rowid
        try:
            evt = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if evt.get("kind") != "human_message" or not is_human(evt):
            continue
        payload = evt.get("payload") or {}
        text = (payload.get("message") or payload.get("text") or "").strip()
        if not text:
            continue
        tenant = evt.get("tenant_id", "repo:logicalworks-")
        session = evt.get("session_id", "cowork")
        log(f"human: {text[:80]}")
        reply = run_opencode(text)
        log(f"opencode: {reply[:80]}")
        emit_agent_message(reply, tenant, session)
    return seq


def main() -> int:
    if not DB.exists():
        log(f"daemon-events.db not found at {DB} — start the daemon first.")
        return 1
    if not (PY.exists() and LGWKS.exists()):
        log(f"lgwks venv/script missing ({PY} / {LGWKS}).")
        return 1
    log(f"chat<->opencode live · model={OC_MODEL or 'opencode default'} · db={DB}")
    try:
        seq = int(STATE.read_text().strip())
    except (OSError, ValueError):
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        seq = tail_rowid(con)
        con.close()
        log(f"starting at bus tail rowid={seq} (no history replay)")
    while True:
        try:
            seq = poll_once(seq)
            STATE.write_text(str(seq))
        except KeyboardInterrupt:
            log("stopped.")
            return 0
        except Exception as e:  # keep the bridge alive across transient daemon writes
            log(f"poll error (continuing): {e}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
