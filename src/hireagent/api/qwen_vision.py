"""Qwen-VL vision integration for form-field detection.

Uses the local Qwen2.5-VL model served by Ollama (zero cost, ~1-2 s/call).
Falls back gracefully when Ollama is not running — callers should handle
``None`` return values.

Setup (one-time)::

    brew install ollama          # macOS
    ollama serve                 # keep running in background
    ollama pull qwen2.5vl:7b     # ~4 GB download

Environment variables (all optional):

  ``OLLAMA_BASE_URL``   – Ollama base URL (default: http://localhost:11434)
  ``VISION_LLM_MODEL``  – Model tag to use (default: qwen2.5vl:7b)

These env vars are the same ones used by ``free_agent.py`` so a single
``.env`` file configures both.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import NamedTuple

logger = logging.getLogger(__name__)

_OLLAMA_BASE  = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
_VISION_MODEL = os.environ.get("VISION_LLM_MODEL", "qwen2.5vl:7b")


# ---------------------------------------------------------------------------
# Low-level Ollama client
# ---------------------------------------------------------------------------

def _ollama_generate(prompt: str, image_bytes: bytes, model: str = _VISION_MODEL,
                     timeout: float = 30.0) -> str | None:
    """Send *image_bytes* + *prompt* to Ollama and return the response text.

    Returns:
        Response string, or ``None`` on error / Ollama not available.
    """
    try:
        import urllib.request
        import json

        image_b64 = base64.b64encode(image_bytes).decode()
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
        }).encode()

        req = urllib.request.Request(
            f"{_OLLAMA_BASE}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return (data.get("response") or "").strip()

    except OSError:
        # Ollama not running — silent fail so callers degrade gracefully
        logger.debug("[qwen_vision] Ollama not reachable at %s", _OLLAMA_BASE)
        return None
    except Exception as exc:
        logger.debug("[qwen_vision] Ollama error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_field_selector(screenshot_bytes: bytes, field_label: str,
                        model: str = _VISION_MODEL) -> str | None:
    """Ask Qwen-VL to locate the CSS selector for *field_label* in *screenshot_bytes*.

    Returns a CSS selector string (e.g. ``input[name='email']``), or ``None``
    if the field was not found or Ollama is unavailable.

    Example::

        screenshot = page.screenshot(type="png")
        selector = find_field_selector(screenshot, "Email address")
        if selector:
            page.locator(selector).fill("user@example.com")
    """
    prompt = (
        f"Look at this web form screenshot. Find the input field for '{field_label}'.\n\n"
        "Return ONLY the CSS selector to use with Playwright. Examples:\n"
        "  input[name='email']\n"
        "  input[placeholder='Email address']\n"
        "  [aria-label='Email']\n"
        "  textarea[name='cover_letter']\n\n"
        "If the field is not visible, return: NOT_FOUND\n\n"
        "Return ONLY the selector — no explanation, no markdown."
    )
    response = _ollama_generate(prompt, screenshot_bytes, model=model)
    if not response or response.strip().upper() == "NOT_FOUND":
        return None
    selector = response.strip().strip("`").strip("'").strip('"')
    logger.debug("[qwen_vision] '%s' → selector=%s", field_label, selector)
    return selector or None


class FieldDetection(NamedTuple):
    label: str
    selector: str


def find_unfilled_fields_with_vision(screenshot_bytes: bytes,
                                     model: str = _VISION_MODEL) -> list[FieldDetection]:
    """Ask Qwen-VL to list ALL visible unfilled form fields in the screenshot.

    Returns a list of ``(label, selector)`` named tuples.
    Returns an empty list if Ollama is unavailable or no fields are found.

    Example::

        fields = find_unfilled_fields_with_vision(page.screenshot())
        for label, selector in fields:
            value = match_field_to_profile(label, profile_data)
            if value:
                page.locator(selector).fill(value)
    """
    prompt = (
        "Look at this web application form. List ALL visible, empty input fields.\n\n"
        "For each field, output one line in this exact format:\n"
        "  FIELD: <human label> | SELECTOR: <css selector>\n\n"
        "Example:\n"
        "  FIELD: First name | SELECTOR: input[name='first_name']\n"
        "  FIELD: Email | SELECTOR: input[type='email']\n\n"
        "Rules:\n"
        "- Only list empty/unfilled fields\n"
        "- Use the most specific selector possible\n"
        "- If no empty fields exist, output: NONE\n"
        "- No extra text, no markdown"
    )
    response = _ollama_generate(prompt, screenshot_bytes, model=model)
    if not response or response.strip().upper() == "NONE":
        return []

    results: list[FieldDetection] = []
    for line in response.splitlines():
        line = line.strip()
        if not line.startswith("FIELD:"):
            continue
        try:
            # "FIELD: First name | SELECTOR: input[name='first_name']"
            parts = line.split("|", 1)
            label    = parts[0].replace("FIELD:", "").strip()
            selector = parts[1].replace("SELECTOR:", "").strip() if len(parts) > 1 else ""
            if label and selector:
                results.append(FieldDetection(label=label, selector=selector))
        except Exception:
            continue

    logger.debug("[qwen_vision] found %d unfilled fields", len(results))
    return results


def describe_page(screenshot_bytes: bytes, model: str = _VISION_MODEL) -> str:
    """Return a brief description of what's on the page (for debugging / logging)."""
    prompt = (
        "Describe this web page in 1-2 sentences. "
        "Focus on: what type of form it is, which ATS platform it looks like, "
        "and roughly how many fields are visible. "
        "Be concise — under 50 words."
    )
    return _ollama_generate(prompt, screenshot_bytes, model=model) or ""


def is_available(model: str = _VISION_MODEL) -> bool:
    """Return True if Ollama is running and the vision model is loaded."""
    try:
        import urllib.request
        import json
        with urllib.request.urlopen(f"{_OLLAMA_BASE}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read())
            loaded = [m.get("name", "") for m in data.get("models", [])]
            return any(model in name for name in loaded)
    except Exception:
        return False
