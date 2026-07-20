"""SaaS Observer — self-monitoring loop for HireAgent.

Records every field interaction step to run_log.json.
On failure, captures a DOM snippet and appends it to Learning_Buffer.txt.
The Learning Buffer is fed back into subsequent LLM calls as 'Past Mistakes'.
Logs degree tier-match decisions to matching_audit.json.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BASE_DIR = Path.home() / ".hireagent"
_RUN_LOG_PATH      = _BASE_DIR / "run_log.json"
_LEARNING_BUF_PATH = _BASE_DIR / "Learning_Buffer.txt"
_AUDIT_PATH        = _BASE_DIR / "matching_audit.json"


def _ensure_dir() -> None:
    _BASE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# run_log.json helpers
# ---------------------------------------------------------------------------

def log_step(
    field: str,
    value_source: str,
    result: str,
    detail: str = "",
    dom_snippet: str = "",
) -> None:
    """Append one interaction record to run_log.json.

    result: 'Success' | 'Failure' | 'Skipped'
    """
    _ensure_dir()
    entry: dict[str, Any] = {
        "ts":           time.strftime("%Y-%m-%dT%H:%M:%S"),
        "field":        field,
        "value_source": value_source,
        "result":       result,
    }
    if detail:
        entry["detail"] = detail
    if dom_snippet:
        entry["dom_snippet"] = dom_snippet[:2000]

    # Append to JSONL (one JSON object per line)
    try:
        with _RUN_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception as exc:
        log.debug("[SaasObserver] run_log write error: %s", exc)

    # On failure: append DOM snippet to Learning_Buffer
    if result == "Failure" and dom_snippet:
        _append_learning_buffer(field=field, dom_snippet=dom_snippet, detail=detail)


def _append_learning_buffer(field: str, dom_snippet: str, detail: str = "") -> None:
    """Append a failure record to Learning_Buffer.txt for future LLM injection."""
    _ensure_dir()
    entry_lines = [
        f"\n--- FAILURE: {time.strftime('%Y-%m-%dT%H:%M:%S')} ---",
        f"Field   : {field}",
        f"Reason  : {detail or 'Unknown'}",
        f"DOM Hint: {dom_snippet[:1500]}",
        "---",
    ]
    try:
        with _LEARNING_BUF_PATH.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(entry_lines) + "\n")
    except Exception as exc:
        log.debug("[SaasObserver] learning_buffer write error: %s", exc)


def read_learning_buffer(max_chars: int = 3000) -> str:
    """Return the last max_chars of Learning_Buffer.txt for LLM injection."""
    try:
        if _LEARNING_BUF_PATH.exists():
            text = _LEARNING_BUF_PATH.read_text(encoding="utf-8")
            return text[-max_chars:] if len(text) > max_chars else text
    except Exception as exc:
        log.debug("[SaasObserver] learning_buffer read error: %s", exc)
    return ""


# ---------------------------------------------------------------------------
# matching_audit.json helpers
# ---------------------------------------------------------------------------

def log_degree_match(
    field: str,
    target: str,
    selected: str,
    tier: int,
    confidence: float,
) -> None:
    """Append one degree-match audit record to matching_audit.json (JSONL)."""
    _ensure_dir()
    entry = {
        "ts":         time.strftime("%Y-%m-%dT%H:%M:%S"),
        "field":      field,
        "target":     target,
        "selected":   selected,
        "tier":       tier,
        "confidence": round(confidence, 4),
    }
    try:
        with _AUDIT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception as exc:
        log.debug("[SaasObserver] matching_audit write error: %s", exc)
