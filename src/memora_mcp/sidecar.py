import json
import os
import sqlite3
import time
import uuid

from memora_mcp.config import memora_home

_SCHEMA = """
create table if not exists memories (
  ulid text primary key,
  index_key text not null,
  scope text not null default 'project',
  taxonomy text default '',
  source_trust text default 'assistant',
  project_key text default '',
  conversation_id text default '',
  harness text default '',
  created_at integer not null,
  status text not null default 'active',
  usage_shown integer not null default 0,
  usage_fetched integer not null default 0,
  last_confirmed_at integer,
  before_image text
);
create index if not exists idx_mem_index on memories(index_key);
create index if not exists idx_mem_scope on memories(scope, status);
create table if not exists tombstones (
  index_key text not null,
  summary text default '',
  ulid text,
  ts integer not null,
  reason text default ''
);
create table if not exists audit (
  id integer primary key autoincrement,
  ts integer not null,
  op text not null,
  ulid text,
  detail text
);
create table if not exists watermarks (
  transcript_path text primary key,
  byte_offset integer not null default 0,
  updated_at integer not null
);
create table if not exists kv (key text primary key, value text);
"""


def _ulid() -> str:
    # Time-sortable but collision-free in the display prefix: 6 hex of
    # coarse time + 10 hex of uuid entropy, so no two share the first 8.
    return f"{int(time.time()) & 0xFFFFFF:06x}{uuid.uuid4().hex[:10]}"


class Sidecar:
    def __init__(self, path=None):
        self.path = path or memora_home() / "sidecar.db"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()

    def close(self):
        self.db.close()

    def audit(self, op, ulid=None, **detail):
        self.db.execute(
            "insert into audit (ts, op, ulid, detail) values (?,?,?,?)",
            (int(time.time()), op, ulid, json.dumps(detail) if detail else None),
        )
        self.db.commit()

    def register_add(self, index_key, *, scope, taxonomy, source_trust, project_key,
                     conversation_id, harness, before_image=None):
        ulid = _ulid()
        self.db.execute(
            "insert into memories (ulid, index_key, scope, taxonomy, source_trust,"
            " project_key, conversation_id, harness, created_at, before_image)"
            " values (?,?,?,?,?,?,?,?,?,?)",
            (ulid, index_key, scope, taxonomy, source_trust, project_key,
             conversation_id, harness, int(time.time()),
             json.dumps(before_image) if before_image else None),
        )
        self.audit("add", ulid, index=index_key, scope=scope)
        return ulid

    def resolve(self, ref):
        """Accept a full ULID, a ULID prefix (as shown in the recall block),
        or an index string; return the row or None."""
        row = self.db.execute(
            "select * from memories where ulid = ? and status = 'active'", (ref,)
        ).fetchone()
        if row:
            return row
        if len(ref) >= 6:
            hits = self.db.execute(
                "select * from memories where ulid like ? and status = 'active' limit 2",
                (ref + "%",),
            ).fetchall()
            if len(hits) == 1:
                return hits[0]
        return self.db.execute(
            "select * from memories where index_key = ? and status = 'active'"
            " order by created_at desc limit 1", (ref,)
        ).fetchone()

    def mark(self, ulid, status, before_image=None):
        if before_image is not None:
            self.db.execute(
                "update memories set status = ?, before_image = ? where ulid = ?",
                (status, json.dumps(before_image), ulid),
            )
        else:
            self.db.execute("update memories set status = ? where ulid = ?", (status, ulid))
        self.audit(status, ulid)

    def tombstone(self, index_key, summary="", ulid=None, reason=""):
        self.db.execute(
            "insert into tombstones (index_key, summary, ulid, ts, reason) values (?,?,?,?,?)",
            (index_key, summary, ulid, int(time.time()), reason),
        )
        if ulid:
            self.mark(ulid, "tombstoned")
        self.db.commit()

    def tombstone_list(self, limit=50):
        return [dict(r) for r in self.db.execute(
            "select index_key, summary from tombstones order by ts desc limit ?", (limit,)
        ).fetchall()]

    def list_active(self, *, scope=None, project_key=None, limit=20):
        q = ("select *, (usage_shown + 3*usage_fetched + 1) *"
             " (1.0 / (1 + (strftime('%s','now') - created_at) / 604800.0)) as rank"
             " from memories where status = 'active'")
        args = []
        if scope:
            q += " and scope = ?"
            args.append(scope)
        if project_key:
            q += " and project_key = ?"
            args.append(project_key)
        q += " order by rank desc limit ?"
        args.append(limit)
        return [dict(r) for r in self.db.execute(q, args).fetchall()]

    def record_usage(self, ulids, kind):
        col = "usage_shown" if kind == "shown" else "usage_fetched"
        for u in ulids:
            self.db.execute(f"update memories set {col} = {col} + 1 where ulid = ?", (u,))
        self.db.commit()

    def watermark(self, transcript_path):
        row = self.db.execute(
            "select byte_offset from watermarks where transcript_path = ?", (transcript_path,)
        ).fetchone()
        return row["byte_offset"] if row else 0

    def set_watermark(self, transcript_path, offset):
        self.db.execute(
            "insert into watermarks (transcript_path, byte_offset, updated_at)"
            " values (?,?,?) on conflict(transcript_path)"
            " do update set byte_offset = excluded.byte_offset, updated_at = excluded.updated_at",
            (transcript_path, offset, int(time.time())),
        )
        self.db.commit()

    def kv_get(self, key, default=None):
        row = self.db.execute("select value from kv where key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def kv_set(self, key, value):
        self.db.execute(
            "insert into kv (key, value) values (?,?)"
            " on conflict(key) do update set value = excluded.value", (key, value)
        )
        self.db.commit()

    def stats(self):
        out = {}
        for k, q in {
            "active": "select count(*) from memories where status='active'",
            "tombstoned": "select count(*) from tombstones",
            "by_scope": "select scope, count(*) from memories where status='active' group by scope",
        }.items():
            rows = self.db.execute(q).fetchall()
            out[k] = rows[0][0] if k != "by_scope" else {r[0]: r[1] for r in rows}
        out["last_distill"] = self.kv_get("last_distill_at")
        out["distills_today"] = self.kv_get(f"distills_{time.strftime('%Y%m%d')}", "0")
        return out
