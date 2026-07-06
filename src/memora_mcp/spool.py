import fcntl
import json
import os
import time

from memora_mcp.config import memora_home


def spool_path():
    p = memora_home() / "spool.jsonl"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def append(transcript_path, from_offset, to_offset, *, reason, session_id="", cwd=""):
    """Record a to-be-distilled transcript span. Cheap and lock-safe: the hook
    must return in well under a second."""
    rec = {
        "transcript_path": transcript_path,
        "from": from_offset,
        "to": to_offset,
        "reason": reason,
        "session_id": session_id,
        "cwd": cwd,
        "ts": int(time.time()),
    }
    with open(spool_path(), "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(rec) + "\n")
    return rec


def drain():
    """Read and truncate the spool atomically; returns the pending spans."""
    p = spool_path()
    if not os.path.exists(p):
        return []
    with open(p, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        lines = f.readlines()
        f.seek(0)
        f.truncate()
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def requeue(spans):
    if not spans:
        return
    with open(spool_path(), "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        for rec in spans:
            f.write(json.dumps(rec) + "\n")
