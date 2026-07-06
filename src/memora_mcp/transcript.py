import json

# Render a byte span of a Claude Code transcript JSONL into a compact
# dialogue string for the distiller. Tool outputs are collapsed to head/tail
# excerpts so a long build log can't dominate the token budget.

_MAX_TOOL_CHARS = 600


def _text_from_content(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for b in content:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text" and b.get("text"):
            parts.append(b["text"])
        elif t == "tool_use":
            parts.append(f"[tool_use {b.get('name','')}: {json.dumps(b.get('input',{}))[:200]}]")
        elif t == "tool_result":
            c = b.get("content")
            s = c if isinstance(c, str) else json.dumps(c)
            if len(s) > _MAX_TOOL_CHARS:
                s = s[: _MAX_TOOL_CHARS // 2] + " …[truncated]… " + s[-_MAX_TOOL_CHARS // 2 :]
            parts.append(f"[tool_result: {s}]")
    return "\n".join(parts)


def render_span(transcript_path, from_offset, to_offset):
    """Return (rendered_text, new_offset, turn_count). Reads [from, to) bytes,
    aligns to line boundaries, and extracts user/assistant turns."""
    with open(transcript_path, "rb") as f:
        f.seek(from_offset)
        raw = f.read(max(0, to_offset - from_offset))
        end_offset = f.tell()
    # Drop a trailing partial line so we never split a JSON record.
    if raw and not raw.endswith(b"\n"):
        nl = raw.rfind(b"\n")
        if nl == -1:
            return "", from_offset, 0
        end_offset = from_offset + nl + 1
        raw = raw[: nl + 1]

    lines = []
    turns = 0
    for line in raw.splitlines():
        try:
            d = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        t = d.get("type")
        if t not in ("user", "assistant"):
            continue
        msg = d.get("message")
        if not isinstance(msg, dict):
            continue
        text = _text_from_content(msg.get("content"))
        if not text.strip():
            continue
        role = msg.get("role", t)
        lines.append(f"{role.upper()}: {text}")
        turns += 1
    return "\n\n".join(lines), end_offset, turns


def file_size(path):
    import os

    try:
        return os.path.getsize(path)
    except OSError:
        return 0
