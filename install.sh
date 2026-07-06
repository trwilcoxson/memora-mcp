#!/bin/sh
# memora-mcp installer: Memora checkout + venv + backend + Claude registration.
# Usage: ./install.sh [--backend ollama|openai] [--no-register] [--pin <ref>]
# Or:    curl -fsSL https://raw.githubusercontent.com/trwilcoxson/memora-mcp/main/install.sh | sh
# Idempotent: safe to re-run. Everything lives under MEMORA_MCP_HOME (~/.memora-mcp).
set -eu

HOME_DIR="${MEMORA_MCP_HOME:-$HOME/.memora-mcp}"
MEMORA_PIN="${MEMORA_PIN:-dec3f8f}"
BACKEND="${MEMORA_BACKEND:-auto}"
REGISTER=1
REPO_URL="https://github.com/trwilcoxson/memora-mcp"
MEMORA_URL="https://github.com/microsoft/Memora"
CHAT_MODEL="${MEMORA_LLM_MODEL:-}"
EMBED_MODEL="${MEMORA_EMBEDDING_MODEL:-}"
FALLBACK_OLLAMA_MODEL="llama3.2:3b"

while [ $# -gt 0 ]; do
  case "$1" in
    --backend) BACKEND="$2"; shift 2 ;;
    --no-register) REGISTER=0; shift ;;
    --pin) MEMORA_PIN="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

say() { printf '%s\n' "==> $*"; }
die() { printf '%s\n' "error: $*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || die "git is required"
VENV="$HOME_DIR/venv"
mkdir -p "$HOME_DIR"

say "Memora checkout ($MEMORA_PIN) -> $HOME_DIR/Memora"
if [ -d "$HOME_DIR/Memora/.git" ]; then
  git -C "$HOME_DIR/Memora" fetch --quiet origin
else
  git clone --quiet "$MEMORA_URL" "$HOME_DIR/Memora"
fi
git -C "$HOME_DIR/Memora" checkout --quiet "$MEMORA_PIN" 2>/dev/null \
  || git -C "$HOME_DIR/Memora" checkout --quiet "origin/$MEMORA_PIN" \
  || die "cannot check out Memora ref $MEMORA_PIN"

# Where is memora-mcp itself? A repo clone if the script sits in one,
# otherwise install straight from GitHub (curl | sh path).
SELF_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd || true)
if [ -n "$SELF_DIR" ] && [ -f "$SELF_DIR/pyproject.toml" ] && grep -q '^name = "memora-mcp"' "$SELF_DIR/pyproject.toml"; then
  MCP_SRC="$SELF_DIR"
else
  MCP_SRC="git+$REPO_URL"
fi

say "Python environment -> $VENV (torch + chromadb: a few GB, be patient)"
if command -v uv >/dev/null 2>&1; then
  [ -x "$VENV/bin/python" ] || uv venv --quiet --python 3.12 "$VENV"
  uv pip install --quiet --python "$VENV/bin/python" -r "$HOME_DIR/Memora/requirements.txt"
  uv pip install --quiet --python "$VENV/bin/python" "$MCP_SRC"
else
  PYBIN=""
  for c in python3.12 python3.11 python3.10 python3; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' && { PYBIN="$c"; break; }
  done
  [ -n "$PYBIN" ] || die "python >= 3.10 required (or install uv: https://docs.astral.sh/uv/)"
  [ -x "$VENV/bin/python" ] || "$PYBIN" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$HOME_DIR/Memora/requirements.txt"
  "$VENV/bin/pip" install --quiet "$MCP_SRC"
fi

SITE=$("$VENV/bin/python" -c 'import site; print(site.getsitepackages()[0])')
printf '%s\n' "$HOME_DIR/Memora/src" > "$SITE/memora-src.pth"

# Model plane: memory rides whatever already instruments your agents. No new
# backend, key, or daemon is provisioned. Embeddings are in-process (bundled
# MiniLM) by default. The plane is detected again at runtime by the server;
# this is just for the install-time report and any env the server needs.
REG_ENV=""
if command -v claude >/dev/null 2>&1; then
  say "model plane: your Claude subscription (claude CLI) — no API key needed"
elif command -v codex >/dev/null 2>&1; then
  say "model plane: your Codex subscription (codex CLI) — no API key needed"
elif [ -n "${OPENAI_API_KEY:-}" ]; then
  say "model plane: OpenAI-compatible API key"
  REG_ENV="-e OPENAI_API_KEY=$OPENAI_API_KEY ${OPENAI_BASE_URL:+-e OPENAI_BASE_URL=$OPENAI_BASE_URL}"
  [ -n "${MEMORA_LLM_MODEL:-}" ] && REG_ENV="$REG_ENV -e MEMORA_LLM_MODEL=$MEMORA_LLM_MODEL"
else
  say "note: no model plane detected yet. Memory stores and recalls now, but"
  say "distillation waits until a plane exists — log in to claude/codex or set"
  say "OPENAI_API_KEY. (Log in later and it just starts working; nothing to redo.)"
fi
# Opt into a served embedding endpoint only if the user asked for one.
[ -n "${MEMORA_EMBEDDING:-}" ] && REG_ENV="$REG_ENV -e MEMORA_EMBEDDING=$MEMORA_EMBEDDING -e MEMORA_EMBEDDING_MODEL=${MEMORA_EMBEDDING_MODEL:-text-embedding-3-small}"

REG_CMD="claude mcp add --scope user memora $REG_ENV -- $VENV/bin/memora-mcp"

if [ "$REGISTER" -eq 1 ] && command -v claude >/dev/null 2>&1; then
  say "registering the memory tools for Claude Code (and Omnigent-managed sessions)"
  claude mcp remove --scope user memora >/dev/null 2>&1 || true
  # shellcheck disable=SC2086
  eval "$REG_CMD" >/dev/null
  say "turning on automatic memory (capture on stop/compact, recall at session start)"
  "$VENV/bin/memora-mcp" enable >/dev/null || true
elif [ "$REGISTER" -eq 1 ]; then
  say "claude CLI not found — register later with:"
  printf '%s\n' "  $REG_CMD"
  printf '%s\n' "  $VENV/bin/memora-mcp enable   # turn on automatic memory"
fi

if command -v omni >/dev/null 2>&1; then
  say "detected Omnigent — memory works in your 'omni claude' sessions automatically"
  say "(user-scope registration reaches every Omnigent-managed native session)"
fi

say "running doctor"
"$VENV/bin/memora-mcp" doctor || true

say "done. Automatic memory is on. Just work in claude or omni claude —"
say "facts you establish are captured on their own and recalled in later sessions."
say "manage it with: memora-mcp list | why <id> | forget <id> | stats"
say "unattended sessions: add \"mcp__memora__*\" to permissions.allow in ~/.claude/settings.json"
