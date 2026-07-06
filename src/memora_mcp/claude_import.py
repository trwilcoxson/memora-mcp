import glob
import os
import re

from memora_mcp.config import ensure_memora_importable, user_id
from memora_mcp.scrub import redact
from memora_mcp.sidecar import Sidecar

# Import Claude Code's native memory files into Memora. Claude memories are
# already curated one-fact-per-file with frontmatter — description ≈ Memora's
# primary abstraction, the name slug ≈ cue anchors, the body ≈ the value — so
# this is a faithful structural import, no model calls required.

_HOME_SLUG = "-Users-timwilcoxson"  # the catch-all "home" project dir
_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


def _claude_projects_root():
    return os.path.expanduser("~/.claude/projects")


def discover():
    """All Claude memory files worth importing, as (path, project_dir_slug)."""
    out = []
    for path in glob.glob(os.path.join(_claude_projects_root(), "*", "memory", "*.md")):
        base = os.path.basename(path)
        if base == "MEMORY.md":
            continue
        slug = path.split("/projects/", 1)[1].split("/memory/", 1)[0]
        # Skip scratch/test dirs (the fakerepo we created, tmp paths).
        if "scratchpad" in slug or "fakerepo" in slug or slug.startswith("-private-tmp"):
            continue
        out.append((path, slug))
    return out


def _parse(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    m = _FM.match(text)
    fm, body = {}, text
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip('"')
        # type lives under metadata: — but avoid matching node_type:
        tm = re.search(r"(?<![a-z_])type:\s*(\w+)", m.group(1))
        if tm:
            fm["type"] = tm.group(1)
    body = _WIKILINK.sub(r"\1", body).strip()
    return fm, body


_STOP = {
    "the", "and", "for", "via", "with", "project", "feedback", "reference",
    "dont", "not", "one", "how", "what", "use", "using", "into", "per", "our",
    "you", "your", "its", "was", "are", "can", "cant", "should", "must", "when",
}


def _slug_cues(name):
    words = [w for w in re.split(r"[_\-]+", name or "") if len(w) > 2 and w.lower() not in _STOP]
    cues, i = [], 0
    while i < len(words) and len(cues) < 4:
        pair = words[i:i + 2]
        # keep a cue only if it has a substantial token
        if any(len(w) >= 4 for w in pair):
            cues.append(" ".join(pair))
        i += 2
    return cues


def _project_key_for(slug):
    if slug == _HOME_SLUG:
        return None  # home dir: scope by type instead
    key = slug
    if key.startswith(_HOME_SLUG + "-"):
        key = key[len(_HOME_SLUG) + 1:]
    return key.strip("-").lower() or None


def _scope_for(fm, project_key):
    t = (fm.get("type") or "reference").lower()
    if project_key:
        # Memory lives in a specific project dir → scope it there.
        return "project", project_key
    # Home dir: cross-cutting kinds go to user scope; project-kind gets a
    # neutral "home" bucket (still fully searchable, just not injected
    # into unrelated projects).
    if t in ("user", "feedback", "reference"):
        return "user", ""
    return "project", "home"


def run(dry_run=False, limit=None):
    ensure_memora_importable()
    from memora.core.memory_entry import MemoryEntry
    from memora.memora_client import MemoraClient

    from memora_mcp.config import build_cfg

    files = discover()
    if limit:
        files = files[:limit]
    client = None if dry_run else MemoraClient(cfg=build_cfg(), user_id=user_id())
    sc = Sidecar()
    imported_key = "claude_imported_names"
    seen = set((sc.kv_get(imported_key) or "").split("\x00")) - {""}

    summary = {"scanned": len(files), "imported": 0, "skipped_dup": 0, "skipped_empty": 0, "redacted": 0}
    preview = []
    for path, slug in files:
        fm, body = _parse(path)
        name = fm.get("name") or os.path.splitext(os.path.basename(path))[0]
        dedup = f"{slug}:{name}"
        if dedup in seen:
            summary["skipped_dup"] += 1
            continue
        index = (fm.get("description") or body.split("\n", 1)[0])[:110].strip()
        if not body or not index:
            summary["skipped_empty"] += 1
            continue
        value, n = redact(body)
        if n:
            summary["redacted"] += 1
        cues = _slug_cues(name)
        pk = _project_key_for(slug)
        scope, project_key = _scope_for(fm, pk)
        taxonomy = (fm.get("type") or "reference").lower()

        if len(preview) < 6:
            preview.append(f"  [{scope}/{project_key or '-'}] {index}\n      cues: {cues}  ({taxonomy})")

        if not dry_run:
            entry = MemoryEntry(value=value, index=index, memory_type="factual")
            if cues:
                entry.cue_indices = "||".join(cues)
            try:
                client._client._agent_memory.add(entry)
            except AssertionError:
                pass  # index already present — treat as no-op
            sc.register_add(
                index, scope=scope, taxonomy=taxonomy, source_trust="user",
                project_key=project_key, conversation_id="claude-import", harness="claude-memory",
            )
            seen.add(dedup)
        summary["imported"] += 1

    if not dry_run:
        sc.kv_set(imported_key, "\x00".join(sorted(seen)))
    sc.close()
    return summary, preview
