import argparse
import json
import os
import sys

from memora_mcp.config import ensure_memora_importable, memora_home, user_id
from memora_mcp.sidecar import Sidecar


def _client():
    ensure_memora_importable()
    from memora_mcp.config import build_cfg
    from memora.memora_client import MemoraClient

    return MemoraClient(cfg=build_cfg(), user_id=user_id())


def cmd_list(args):
    sc = Sidecar()
    rows = sc.list_active(scope=args.scope, limit=args.limit)
    for r in rows:
        print(f"{r['ulid'][:8]}  [{r['scope']:7}]  {r['index_key']}")
    if not rows:
        print("(no memories)")
    sc.close()


def cmd_show(args):
    sc = Sidecar()
    row = sc.resolve(args.id)
    if not row:
        print(f"not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    rec = _client().get(row["index_key"])
    print(json.dumps({"sidecar": dict(row), "memory": rec}, indent=2, default=str))
    sc.close()


def cmd_why(args):
    sc = Sidecar()
    row = sc.resolve(args.id)
    if not row:
        print(f"not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    print(f"index:        {row['index_key']}")
    print(f"scope:        {row['scope']}  project: {row['project_key'] or '-'}")
    print(f"taxonomy:     {row['taxonomy']}   trust: {row['source_trust']}")
    print(f"learned via:  {row['harness'] or '?'}  conversation: {row['conversation_id'] or '?'}")
    import time
    print(f"created:      {time.strftime('%Y-%m-%d %H:%M', time.localtime(row['created_at']))}")
    print(f"usage:        shown {row['usage_shown']}, fetched {row['usage_fetched']}")
    sc.close()


def cmd_forget(args):
    sc = Sidecar()
    row = sc.resolve(args.id)
    if not row:
        print(f"not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    try:
        _client().delete(row["index_key"])
    except Exception as e:
        print(f"warn: store delete failed ({e}); tombstoning anyway", file=sys.stderr)
    sc.tombstone(row["index_key"], summary=row["index_key"], ulid=row["ulid"], reason=args.reason or "user")
    print(f"forgotten and tombstoned: {row['index_key']}")
    sc.close()


def cmd_stats(args):
    sc = Sidecar()
    s = sc.stats()
    from memora_mcp import planes

    plane = planes.detect()
    print(f"store:        {memora_home()}")
    print(f"model plane:  {plane['kind']}")
    print(f"active:       {s['active']}   tombstoned: {s['tombstoned']}")
    print(f"by scope:     {s['by_scope']}")
    import time
    ld = s.get("last_distill")
    print(f"last distill: {time.strftime('%Y-%m-%d %H:%M', time.localtime(int(ld))) if ld else 'never'}")
    print(f"distills today: {s.get('distills_today', '0')}")
    from memora_mcp import spool
    p = spool.spool_path()
    depth = sum(1 for _ in open(p)) if os.path.exists(p) else 0
    print(f"spool depth:  {depth}")
    sc.close()


def cmd_export(args):
    sc = Sidecar()
    rows = sc.list_active(limit=100000)
    client = _client()
    out = []
    for r in rows:
        rec = client.get(r["index_key"])
        out.append({"sidecar": dict(r), "memory": rec})
    dest = args.out or "-"
    text = "\n".join(json.dumps(o, default=str) for o in out)
    if dest == "-":
        print(text)
    else:
        open(dest, "w").write(text + "\n")
        print(f"exported {len(out)} memories -> {dest}", file=sys.stderr)
    sc.close()


def cmd_config(args):
    from memora_mcp import planes
    from memora_mcp.settings import as_table

    plane = planes.detect()
    print(f"active model plane: {plane['kind']}\n")
    w = max(len(k) for k, _, _ in as_table())
    for key, val, note in as_table():
        print(f"  {key:<{w}}  {val}")
        print(f"  {'':<{w}}  \033[2m{note}\033[0m")
    print("\nset any of these as an environment variable (or via the MCP `env` block).")


def cmd_import_claude(args):
    from memora_mcp.claude_import import run

    summary, preview = run(dry_run=args.dry_run, limit=args.limit)
    if preview:
        print("sample of what will be imported:" if args.dry_run else "imported (sample):")
        print("\n".join(preview))
        print()
    print(json.dumps(summary, indent=2))
    if args.dry_run:
        print("\n(dry run — nothing written. re-run without --dry-run to import.)")


def cmd_distill(args):
    from memora_mcp.distiller import run_once

    print(json.dumps(run_once(), indent=2))


def cmd_doctor(args):
    from memora_mcp.doctor import run

    sys.exit(run())


def cmd_enable(args):
    from memora_mcp.enable import enable

    enable(disable=False)


def cmd_disable(args):
    from memora_mcp.enable import enable

    enable(disable=True)


def main(argv=None):
    p = argparse.ArgumentParser(prog="memora-mcp", description="automemory management")
    sub = p.add_subparsers(dest="cmd", required=True)

    lp = sub.add_parser("list", help="list stored memories")
    lp.add_argument("--scope", choices=["user", "project", "session"])
    lp.add_argument("--limit", type=int, default=30)
    lp.set_defaults(fn=cmd_list)

    sp = sub.add_parser("show", help="show one memory's full record")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_show)

    wp = sub.add_parser("why", help="provenance of a memory")
    wp.add_argument("id")
    wp.set_defaults(fn=cmd_why)

    fp = sub.add_parser("forget", help="delete + tombstone a memory")
    fp.add_argument("id")
    fp.add_argument("--reason", default="")
    fp.set_defaults(fn=cmd_forget)

    sub.add_parser("stats", help="store + capture health").set_defaults(fn=cmd_stats)

    ep = sub.add_parser("export", help="export memories as jsonl")
    ep.add_argument("--out")
    ep.set_defaults(fn=cmd_export)

    ic = sub.add_parser("import-claude", help="import Claude Code's native memory files into Memora")
    ic.add_argument("--dry-run", action="store_true", help="preview without writing")
    ic.add_argument("--limit", type=int, help="cap number of files (for testing)")
    ic.set_defaults(fn=cmd_import_claude)

    sub.add_parser("config", help="show the active memory-engine configuration").set_defaults(fn=cmd_config)
    sub.add_parser("distill", help="run the distiller now (drains the spool)").set_defaults(fn=cmd_distill)
    sub.add_parser("doctor", help="health check").set_defaults(fn=cmd_doctor)
    sub.add_parser("enable", help="register automemory hooks in ~/.claude/settings.json").set_defaults(fn=cmd_enable)
    sub.add_parser("disable", help="remove automemory hooks").set_defaults(fn=cmd_disable)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
