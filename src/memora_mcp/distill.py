import contextlib
import fcntl
import fnmatch
import json
import os
import sys
import time

from memora_mcp import planes, scrub, spool
from memora_mcp.config import load_snapshot, memora_home
from memora_mcp.sidecar import Sidecar

SENTINEL_OPEN = "<automemory>"
SENTINEL_CLOSE = "</automemory>"

_MAX_SEGMENT_CHARS = 90_000
_TOOL_OUTPUT_HEAD = 400
_TOOL_OUTPUT_TAIL = 200
_MIN_ITEMS = 6
_DAILY_CAP = 40

_TAXONOMY = "decision | env_discovery | failure_fix | preference | convention"

_PROMPT = """You maintain the persistent memory of a software engineer's coding agents. \
Below is a transcript segment from one session. Extract ONLY durable facts worth \
recalling weeks later, and emit memory operations.

SAVE (taxonomy: {taxonomy}):
- decisions made and their rationale
- environment/config discoveries (ports, versions, flags, quirks)
- failure -> fix pairs (what broke and what resolved it)
- the user's stated preferences and conventions

IGNORE: transient state, restated code, unvalidated plans, secrets, pleasantries, \
anything already