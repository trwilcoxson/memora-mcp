import json
import os
import re
import shutil
import subprocess

# Model-plane detection and dispatch. Memory rides whatever instrumentation
# the person already has for their agents; it never brings its own.
#
# Order of preference: explicit MEMORA_PLANE, then a logged-in agent CLI
# (that IS how subscription users instrument agents), then API-key env.
# This inverts the doc's api-before-subscription order deliberately: leftover
# OPENAI_* env pointed at a scratch endpoint should not outrank the
# subscription the person actually works on.


def detect():
    forced = os.environ.get("MEMORA_PLANE")
    if forced:
        return {"kind": forced}
    if shutil.which("claude"):
        return {"kind": "subscription-claude"}
    if shutil.which("codex"):
        return {"kind": "subscription-codex"}
    if os.environ.get("OPENAI_API_KEY"):
        return {
            "kind": "api",
            "model": os.environ.get("MEMORA_LLM_MODEL", "gpt-4.1-mini"),
            "base_url": os.environ.get("OPENAI_BASE_URL"),
        }
    return {"kind": "none"}


_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def _extract_json(text):
    m = _JSON_BLOCK.search(text or "")
    if not m:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    return json.loads(m.group(0))


def complete_json(plane, prompt, timeout=600):
    """One model turn on the deployment's plane; returns the parsed JSON object."""
    kind = plane["kind"]
    if kind == "subscription-claude":
        r = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json",
             "--disallowedTools", "*", "--max-turns", "1"],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode != 0:
            raise RuntimeError(f"claude plane failed: {r.stderr[:300]}")
        payload = json.loads(r.stdout)
        return _extract_json(payload.get("result", ""))
    if kind == "subscription-codex":
        r = subprocess.run(
            ["codex", "exec", "--json", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode != 0:
            raise RuntimeError(f"codex plane failed: {r.stderr[:300]}")
        text = ""
        for line in r.stdout.splitlines():
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = evt.get("msg", {}).get("message", text) or text
        return _extract_json(text)
    if kind == "api":
        from openai import OpenAI

        client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", "unused"),
            base_url=plane.get("base_url") or os.environ.get("OPENAI_BASE_URL"),
        )
        r = client.chat.completions.create(
            model=plane.get("model") or os.environ.get("MEMORA_LLM_MODEL", "gpt-4.1-mini"),
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_json(r.choices[0].message.content)
    raise RuntimeError(
        "no model plane available: log in to claude or codex, or set OPENAI_API_KEY"
    )
