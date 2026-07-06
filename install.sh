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

if [ "$BACKEND" = "auto" ]; then
  if [ -n "${OPENAI_API_KEY:-}" ]; then BACKEND=openai; elif command -v ollama >/dev/null 2>&1; then BACKEND=ollama; else
    die "no backend: set OPENAI_API_KEY (any OpenAI-compatible endpoint via OPENAI_BASE_URL), or install Ollama (https://ollama.com), then re-run"
  fi
fi

case "$BACKEND" in
  ollama)
    command -v ollama >/dev/null 2>&1 || die "ollama not found (https://ollama.com)"
    if ! curl -fsS -m 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
      say "starting ollama"
      if [ -d /Applications/Ollama.app ]; then open -a Ollama; else (ollama serve >/dev/null 2>&1 &); fi
      sleep 4
      curl -fsS -m 5 http://localhost:11434/api/tags >/dev/null 2>&1 || die "ollama is installed but not serving on :11434"
    fi
    CHAT_MODEL="${CHAT_MODEL:-gpt-4-local}"
    EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
    ollama list | awk '{print $1}' | grep -qx "$EMBED_MODEL:latest" || { say "pulling $EMBED_MODEL"; ollama pull "$EMBED_MODEL"; }
    if ! ollama list | awk '{print $1}' | grep -qx "$CHAT_MODEL:latest"; then
      # Memora only uses the OpenAI client for GPT-looking model names, so
      # local models get served under a gpt-* alias.
      say "pulling $FALLBACK_OLLAMA_MODEL and aliasing it to $CHAT_MODEL"
      ollama pull "$FALLBACK_OLLAMA_MODEL"
      ollama cp "$FALLBACK_OLLAMA_MODEL" "$CHAT_MODEL"
    fi
    ENV_API_TYPE=openai ENV_API_KEY=ollama ENV_BASE_URL=http://localhost:11434/v1
    ;;
  openai)
    [ -n "${OPENAI_API_KEY:-}" ] || die "--backend openai needs OPENAI_API_KEY exported"
    CHAT_MODEL="${CHAT_MODEL:-gpt-4.1-mini}"
    EMBED_MODEL="${EMBED_MODEL:-text-embedding-3-small}"
    ENV_API_TYPE=openai ENV_API_KEY="$OPENAI_API_KEY" ENV_BASE_URL="${OPENAI_BASE_URL:-}"
    ;;
  *) die "unknown backend: $BACKEND" ;;
esac

REG_CMD="claude mcp add --scope user memora \
  -e OPENAI_API_TYPE=$ENV_API_TYPE -e OPENAI_API_KEY=$ENV_API_KEY \
  ${ENV_BASE_URL:+-e OPENAI_BASE_URL=$ENV_BASE_URL} \
  -e MEMORA_LLM_MODEL=$CHAT_MODEL -e MEMORA_EMBEDDING_MODEL=$EMBED_MODEL \
  -- $VENV/bin/memora-mcp"

if [ "$REGISTER" -eq 1 ] && command -v claude >/dev/null 2>&1; then
  say "registering user-scope MCP server for Claude Code (and Omnigent-managed sessions)"
  claude mcp remove --scope user memora >/dev/null 2>&1 || true
  # shellcheck disable=SC2086
  eval "$REG_CMD" >/dev/null
elif [ "$REGISTER" -eq 1 ]; then
  say "claude CLI not found — register later with:"
  printf '%s\n' "  $REG_CMD"
fi

say "running doctor"
env OPENAI_API_TYPE="$ENV_API_TYPE" OPENAI_API_KEY="$ENV_API_KEY" \
  ${ENV_BASE_URL:+OPENAI_BASE_URL="$ENV_BASE_URL"} \
  MEMORA_LLM_MODEL="$CHAT_MODEL" MEMORA_EMBEDDING_MODEL="$EMBED_MODEL" \
  "$VENV/bin/memora-mcp" doctor

say "done. Try it: open a new claude (or omni claude) session and say"
say '  "save to memory: <a fact>"  then, in a later session,  "search memory for <a paraphrase>"'
say "unattended sessions: add \"mcp__memora__*\" to permissions.allow in ~/.claude/settings.json"
