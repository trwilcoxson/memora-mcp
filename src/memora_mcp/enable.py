import json
import os
import sys

# Register (or remove) automemory's Claude Code hooks in user settings.
# SessionStart -> recall block; Stop/PreCompact/SessionEnd -> spool + distill.
# Idempotent: keyed by a stable marker on each hook command.

_SETTINGS = os.path.expanduser("~/.claude/settings.json")
_MARKER = "memora_mcp.hooks"
_EVENTS = ["SessionStart", "Stop", "PreCompact", "SessionEnd"]


def _hook_command():
    # Use this interpreter so the venv with memora is on the path.
    return f"{sys.executable} -m memora_mcp.hooks"


def _load():
    if not os.path.exists(_SETTINGS):
        return {}
    try:
        return json.load(open(_SETTINGS))
    except (json.JSONDecodeError, ValueError):
        return {}


def _strip_ours(hook_list):
    out = []
    for group in hook_list or []:
        hooks = [h for h in group.get("hooks", []) if _MARKER not in h.get("command", "")]
        if hooks:
            out.append({**group, "hooks": hooks})
    return out


def enable(disable=False):
    settings = _load()
    hooks = settings.setdefault("hooks", {})
    cmd = _hook_command()

    for event in _EVENTS:
        hooks[event] = _strip_ours(hooks.get(event))
        if not disable:
            entry = {"type": "command", "command": cmd}
            if event in ("Stop", "PreCompact", "SessionEnd"):
                entry["timeout"] = 5
            else:
                entry["timeout"] = 5
            hooks[event].append({"hooks": [entry]})
        if not hooks[event]:
            del hooks[event]

    os.makedirs(os.path.dirname(_SETTINGS), exist_ok=True)
    if os.path.exists(_SETTINGS):
        import shutil

        shutil.copy(_SETTINGS, _SETTINGS + ".memora-bak")
    json.dump(settings, open(_SETTINGS, "w"), indent=2)
    action = "removed from" if disable else "registered in"
    print(f"automemory hooks {action} {_SETTINGS}")
    if not disable:
        print("automemory is on: sessions now capture on stop/compact and recall at start.")
        print("add \"mcp__memora__*\" to permissions.allow if you don't run bypassed.")
