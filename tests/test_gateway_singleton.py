"""Enforce the single-OpenAI-client rule (spec 013 AC 1; AGENTS hard rule #1).

No module except app/services/ai/llm_gateway.py may import `openai`.
"""

from __future__ import annotations

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
ALLOWED = {"services/ai/llm_gateway.py"}
_IMPORT_RE = re.compile(r"^\s*(?:import openai|from openai)", re.MULTILINE)


def test_only_gateway_imports_openai():
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        rel = path.relative_to(APP_DIR).as_posix()
        if rel in ALLOWED:
            continue
        if _IMPORT_RE.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert not offenders, f"openai imported outside the gateway: {offenders}"
