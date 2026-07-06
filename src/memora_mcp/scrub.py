import math
import re

# Deterministic secret redaction, run before any transcript text reaches a
# model or the store. Redact-not-drop: the surrounding fact usually is the
# value; the literal credential never is.

_PATTERNS = [
    ("pem", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("aws", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("bearer", re.compile(r"(?i)\b(bearer|authorization:)\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("assign", re.compile(r"(?i)\b(api[_-]?key|token|secret|passwd|password)\s*[:=]\s*['\"]?[^\s'\"]{8,}")),
]

# High-entropy strings that are usually fine in engineering notes.
_ARTIFACT_CONTEXT = re.compile(r"(?i)\b(sha|digest|commit|hash|uuid|etag|blob|checksum)\b")
_HEX_BLOB = re.compile(r"\b[0-9a-fA-F]{40,}\b")


def _entropy(s):
    if not s:
        return 0.0
    freq = {c: s.count(c) for c in set(s)}
    return -sum(n / len(s) * math.log2(n / len(s)) for n in freq.values())


def redact(text):
    """Return (clean_text, redaction_count)."""
    count = 0
    for name, pat in _PATTERNS:
        text, n = pat.subn(f"[redacted:{name}]", text)
        count += n

    def hex_sub(m):
        nonlocal count
        start = max(0, m.start() - 60)
        if _ARTIFACT_CONTEXT.search(text[start:m.start()]):
            return m.group(0)
        if _entropy(m.group(0)) > 3.2:
            count += 1
            return "[redacted:blob]"
        return m.group(0)

    text = _HEX_BLOB.sub(hex_sub, text)
    return text, count
