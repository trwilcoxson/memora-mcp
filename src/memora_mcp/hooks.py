import json
import os
import subprocess
import sys

# Claude Code hook entrypoint for automemory. One process, dispatched by the
# hook_event_name in the JSON payload on stdin. Every path must be fast and
# fail silent: hooks that error or hang degrade the user's session.
#
# Registered in ~/.claude/settings.json (see `memora-mcp enable`). Because
# Omnigent does not pass --strict-mcp-config, these user-scope hooks also fire
# in Omnigent-managed native Claude sessions.


def _emit(obj):
    if obj:
        sys.stdout.write(json.dumps(obj))
    sys.exit(0)


def _spawn_distill():
    """Detach a background distill job. Never blocks the hook."""
    try:
        subprocess.Popen(
            [sys.executable, "-m", "memora_mcp.hooks", "__distill__"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def _ignored(cwd):
    try:
        return os.path.exists(os.path.join(cwd or ".", ".memora-ignore"))
    except OSError:
        return False


def _spool_since_watermark(payload, reason):
    from memora_mcp import spool
    from memora_mcp.sidecar import Sidecar
    from memora_mcp.transcript import file_size

    tp = payload.get("transcript_path")
    if not tp or not os.path.exists(tp):
        return
    cwd = payload.get("cwd") or os.getcwd()
    if _ignored(cwd):
        return
    sc = Sidecar()
    try:
        frm = sc.watermark(tp)
        size = file_size(tp)
        if size <= frm:
            return
        spool.append(tp, frm, size, reason=reason,
                     session_id=payload.get("session_id", ""), cwd=cwd)
    finally:
        sc.close()
    _spawn_distill()


def handle(payload):
    event = payload.get("hook_event_name", "")

    if event == "SessionStart":
        # Recall: print the memory block to stdout (Claude renders it into
        # context). On /clear (source=compact) we still re-prime.
        try:
            from memora_mcp.recall import build_block, record_shown

            text, shown = build_block(payload.get("cwd") or os.getcwd())
            if text:
                record_shown(shown)
                _emit({"hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": text,
                }})
        except Exception:
            pass
        _emit(None)

    if event in ("Stop", "StopFailure", "PreCompact", "SessionEnd"):
        try:
            _spool_since_watermark(payload, reason=event)
        except Exception:
            pass
        _emit(None)

    _emit(None)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] == "__distill__":
        try:
            from memora_mcp.distiller import run_once

            run_once()
        except Exception:
            pass
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)
    try:
        handle(payload)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
