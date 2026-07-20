"""Vision-Verified Interaction Loop — Three-Layer Architecture.

Layers:
  BrowserController  – human-like input with Bezier mouse curves, stealth spoofing,
                       post-type verification, JS fallback for React/Vue masked inputs
  IntelligenceLayer  – NVIDIA NIM dual-model (Nemotron text + Llama-3.2 vision)
  CaptchaSolver      – CapSolver with reCAPTCHA Enterprise / pageAction / userAgent sync
"""
from __future__ import annotations

import base64
import json
import logging
import math
import os
import random
import re
import time
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

# ── NVIDIA NIM keys (env vars take priority; fall back to hard-coded defaults) ──
_NIM_TEXT_KEY   = os.environ.get("NVIDIA_NIM_TEXT_KEY",
                  "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")
_NIM_VISION_KEY = os.environ.get("NVIDIA_NIM_VISION_KEY",
                  "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")

_NIM_BASE_URL   = "https://integrate.api.nvidia.com/v1"
_VISION_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

_TEXT_MODEL    = "nvidia/nemotron-3-super-120b-a12b"   # 120B with extended thinking
_VISION_MODEL  = "meta/llama-3.2-11b-vision-instruct"

# ── Stealth user-agent — spoofed as 2021 M1 MacBook Pro / Chrome 120 ──────────
_STEALTH_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_STEALTH_WEBGL_VENDOR   = "Apple Inc."
_STEALTH_WEBGL_RENDERER = "Apple M1"


# ─────────────────────────────────────────────────────────────────────────────
# SoM overlay JS — draws numbered red boxes over every interactable element
# ─────────────────────────────────────────────────────────────────────────────
_SOM_INJECT_JS = """
() => {
    // Remove any previous overlays
    document.querySelectorAll('.__som_overlay__').forEach(e => e.remove());

    // FILTERED: Only mark fillable/actionable elements. Skip labels, paragraphs,
    // spans, list items — these create SoM noise that confuses the vision model.
    const SELECTORS = 'input:not([type=hidden]):not([type=file]), select, textarea, ' +
                      'button[type="submit"], ' +
                      '[role="combobox"], [role="listbox"], [role="checkbox"], [role="radio"]';
    const elements  = document.querySelectorAll(SELECTORS);
    const map       = {};
    let   id        = 1;

    elements.forEach(el => {
        const rect = el.getBoundingClientRect();
        if (rect.width < 2 || rect.height < 2) return;
        if (rect.top < -200 || rect.top > window.innerHeight + 200) return;

        const box = document.createElement('div');
        box.className = '__som_overlay__';
        box.setAttribute('data-som-id', id);
        box.style.cssText = [
            'position:fixed',
            'left:'   + Math.round(rect.left)   + 'px',
            'top:'    + Math.round(rect.top)     + 'px',
            'width:'  + Math.round(rect.width)   + 'px',
            'height:' + Math.round(rect.height)  + 'px',
            'border:2px solid #e00',
            'background:rgba(220,0,0,0.08)',
            'pointer-events:none',
            'z-index:2147483647',
            'box-sizing:border-box',
        ].join(';');

        const badge = document.createElement('span');
        badge.textContent = id;
        badge.style.cssText = [
            'position:absolute',
            'top:-14px',
            'left:0',
            'background:#e00',
            'color:#fff',
            'font:bold 10px/14px monospace',
            'padding:0 3px',
            'border-radius:2px',
            'white-space:nowrap',
        ].join(';');
        box.appendChild(badge);
        document.body.appendChild(box);

        map[id] = {
            tag:         el.tagName.toLowerCase(),
            type:        el.type        || '',
            id:          el.id          || '',
            name:        el.name        || '',
            placeholder: el.placeholder || '',
            ariaLabel:   el.getAttribute('aria-label') || '',
            text:        (el.innerText || el.value || '').trim().slice(0, 60),
            role:        el.getAttribute('role') || '',
        };
        id++;
    });
    return JSON.stringify(map);
}
"""

_SOM_REMOVE_JS = """
() => { document.querySelectorAll('.__som_overlay__').forEach(e => e.remove()); }
"""

# ─────────────────────────────────────────────────────────────────────────────
# Stealth JS — mask navigator.webdriver and spoof WebGL fingerprint
# ─────────────────────────────────────────────────────────────────────────────
_STEALTH_INIT_SCRIPT = f"""
() => {{
    // Mask navigator.webdriver
    try {{
        Object.defineProperty(navigator, 'webdriver', {{
            get: () => undefined,
            configurable: true,
        }});
    }} catch(e) {{}}

    // Spoof WebGL vendor/renderer to M1 MacBook Pro
    try {{
        const origGetParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {{
            if (param === 37445) return '{_STEALTH_WEBGL_VENDOR}';
            if (param === 37446) return '{_STEALTH_WEBGL_RENDERER}';
            return origGetParameter.call(this, param);
        }};
        const origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(param) {{
            if (param === 37445) return '{_STEALTH_WEBGL_VENDOR}';
            if (param === 37446) return '{_STEALTH_WEBGL_RENDERER}';
            return origGetParam2.call(this, param);
        }};
    }} catch(e) {{}}

    // Spoof plugins array (non-empty like real Chrome)
    try {{
        Object.defineProperty(navigator, 'plugins', {{
            get: () => [1, 2, 3, 4, 5],
        }});
    }} catch(e) {{}}

    // Spoof languages
    try {{
        Object.defineProperty(navigator, 'languages', {{
            get: () => ['en-US', 'en'],
        }});
    }} catch(e) {{}}
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Bezier curve helpers for human-like mouse movement
# ─────────────────────────────────────────────────────────────────────────────

def _cubic_bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 25,
) -> list[tuple[float, float]]:
    """Generate points along a cubic Bezier curve."""
    points = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = (mt**3 * p0[0] +
             3 * mt**2 * t * p1[0] +
             3 * mt * t**2 * p2[0] +
             t**3 * p3[0])
        y = (mt**3 * p0[1] +
             3 * mt**2 * t * p1[1] +
             3 * mt * t**2 * p2[1] +
             t**3 * p3[1])
        points.append((x, y))
    return points


def _rand_control_point(
    p0: tuple[float, float],
    p3: tuple[float, float],
    jitter: float = 0.3,
) -> tuple[float, float]:
    """Generate a random control point between p0 and p3 with jitter."""
    dx = p3[0] - p0[0]
    dy = p3[1] - p0[1]
    dist = math.sqrt(dx * dx + dy * dy) or 1.0
    t = random.uniform(0.2, 0.8)
    cx = p0[0] + dx * t + random.uniform(-jitter * dist, jitter * dist)
    cy = p0[1] + dy * t + random.uniform(-jitter * dist, jitter * dist)
    return (cx, cy)


# ─────────────────────────────────────────────────────────────────────────────
# BrowserController
# ─────────────────────────────────────────────────────────────────────────────
class BrowserController:
    """Wraps a Playwright page with human-centric interactions and vision fallback.

    Features:
    - human_click: Bezier-curve mouse path with random jitter and speed variation
    - type_with_verification: keyboard.type → verify → JS-fallback for React/Vue masks
    - Stealth init: masks navigator.webdriver, spoofs WebGL to M1 MacBook Pro
    - SoM overlay: numbered red boxes for vision model navigation
    """

    def __init__(self, page, apply_stealth: bool = True):
        self.page = page
        self._som_map: dict[int, dict] = {}
        self._current_mouse: tuple[float, float] = (
            random.uniform(400, 600),
            random.uniform(300, 500),
        )
        if apply_stealth:
            self._apply_stealth()

    # ── Stealth init ─────────────────────────────────────────────────────────

    def _apply_stealth(self) -> None:
        """Inject stealth overrides into the current page context."""
        try:
            self.page.add_init_script(_STEALTH_INIT_SCRIPT)
            log.debug("[BrowserController] Stealth init script registered")
        except Exception as exc:
            log.debug("[BrowserController] Stealth init warning: %s", exc)

        # Override user-agent at the CDP level if possible
        try:
            self.page.set_extra_http_headers({"User-Agent": _STEALTH_UA})
        except Exception:
            pass

    # ── Human-like mouse movement ────────────────────────────────────────────

    def human_move_to(
        self,
        x: float,
        y: float,
        steps: int | None = None,
    ) -> None:
        """Move the mouse to (x, y) along a Bezier curve with random jitter.

        Args:
            x, y:  Target coordinates.
            steps: Number of intermediate mouse positions (default: random 20-35).
        """
        steps = steps or random.randint(20, 35)
        p0 = self._current_mouse
        p3 = (x + random.uniform(-2, 2), y + random.uniform(-2, 2))
        p1 = _rand_control_point(p0, p3, jitter=0.25)
        p2 = _rand_control_point(p0, p3, jitter=0.25)

        curve = _cubic_bezier(p0, p1, p2, p3, steps=steps)

        for px, py in curve:
            # Add micro-jitter to each step
            jx = px + random.gauss(0, 0.4)
            jy = py + random.gauss(0, 0.4)
            self.page.mouse.move(jx, jy)
            # Variable speed: slow near start/end, faster in the middle
            t_norm = curve.index((px, py)) / max(len(curve) - 1, 1)
            pause = random.uniform(0.001, 0.012) * (1 + abs(t_norm - 0.5))
            time.sleep(pause)

        self._current_mouse = (x, y)

    def human_click(
        self,
        selector: str | None = None,
        element=None,
        x: float | None = None,
        y: float | None = None,
        button: str = "left",
        delay_after: float | None = None,
    ) -> bool:
        """Click an element via human-like Bezier mouse curve.

        Pass one of: selector (CSS/Playwright selector), element (ElementHandle),
        or (x, y) screen coordinates.

        Returns True if the click succeeded.
        """
        page = self.page
        try:
            if x is not None and y is not None:
                self.human_move_to(x, y)
                time.sleep(random.uniform(0.05, 0.12))
                page.mouse.down(button=button)
                time.sleep(random.uniform(0.04, 0.09))
                page.mouse.up(button=button)
                log.debug("[BrowserController] human_click at (%.0f, %.0f)", x, y)
                time.sleep(delay_after or random.uniform(0.1, 0.3))
                return True

            if element is not None:
                try:
                    bb = element.bounding_box()
                    if bb:
                        cx = bb["x"] + bb["width"]  / 2 + random.uniform(-3, 3)
                        cy = bb["y"] + bb["height"] / 2 + random.uniform(-3, 3)
                        self.human_move_to(cx, cy)
                        time.sleep(random.uniform(0.05, 0.12))
                        page.mouse.down(button=button)
                        time.sleep(random.uniform(0.04, 0.09))
                        page.mouse.up(button=button)
                        self._current_mouse = (cx, cy)
                        time.sleep(delay_after or random.uniform(0.1, 0.3))
                        log.debug("[BrowserController] human_click element (%.0f,%.0f)", cx, cy)
                        return True
                except Exception:
                    pass
                # Fallback to Playwright click if BB unavailable
                element.click(timeout=5000)
                return True

            if selector is not None:
                loc = page.locator(selector).first
                if not loc.is_visible(timeout=2000):
                    return False
                bb = loc.bounding_box()
                if bb:
                    cx = bb["x"] + bb["width"]  / 2 + random.uniform(-3, 3)
                    cy = bb["y"] + bb["height"] / 2 + random.uniform(-3, 3)
                    self.human_move_to(cx, cy)
                    time.sleep(random.uniform(0.05, 0.12))
                    page.mouse.down(button=button)
                    time.sleep(random.uniform(0.04, 0.09))
                    page.mouse.up(button=button)
                    self._current_mouse = (cx, cy)
                    time.sleep(delay_after or random.uniform(0.1, 0.3))
                    log.debug("[BrowserController] human_click selector: %s", selector[:50])
                    return True
                else:
                    loc.click(timeout=5000)
                    return True

        except Exception as exc:
            log.debug("[BrowserController] human_click error: %s", exc)
        return False

    # ── Core: type with verification ────────────────────────────────────────

    def type_with_verification(self, element, text: str, retries: int = 2) -> bool:
        """Click → keyboard.type → verify → JS-fallback if empty.

        For React/Vue masked inputs where keyboard events are intercepted,
        falls back to native property setter + synthetic events.

        Args:
            element: Playwright ElementHandle or Locator (.first is called for Locators).
            text:    The string to type.
            retries: Number of keyboard.type retries before JS fallback.

        Returns True if the field has the expected value, False if all attempts fail.
        """
        page = self.page

        # Normalise: if it's a Locator, unwrap to ElementHandle
        try:
            if hasattr(element, "first"):
                element = element.first
        except Exception:
            pass

        dropdown_option_clicked = False
        for attempt in range(retries + 1):
            try:
                # 1. Human-like move + click via bounding box
                try:
                    element.scroll_into_view_if_needed(timeout=2000)
                    bb = element.bounding_box()
                    if bb:
                        cx = bb["x"] + bb["width"]  / 2 + random.uniform(-2, 2)
                        cy = bb["y"] + bb["height"] / 2 + random.uniform(-2, 2)
                        self.human_move_to(cx, cy)
                        time.sleep(random.uniform(0.04, 0.10))
                        page.mouse.down()
                        time.sleep(random.uniform(0.03, 0.07))
                        page.mouse.up()
                        self._current_mouse = (cx, cy)
                    else:
                        element.click(timeout=3000)
                except Exception:
                    element.click(timeout=3000)

                time.sleep(random.uniform(0.05, 0.15))

                # 2. Clear existing content — triple-click selects all text in
                # the input on both macOS and Windows without going through an
                # intermediate empty state that triggers React required-field
                # validation (Control+a on macOS moves cursor, not select-all).
                try:
                    element.select_all()
                except Exception:
                    try:
                        element.click(click_count=3)  # triple-click = select all
                    except Exception:
                        pass

                # 3. Type with human-like per-key delay
                delay_ms = random.uniform(50, 150)
                page.keyboard.type(text, delay=delay_ms)
                time.sleep(random.uniform(0.15, 0.25))

                # 4a. Dropdown option click — for React comboboxes, typing filters the list
                #     but does NOT select; we must click the matching [role="option"].
                #     If successful, skip verify and JS fallback (React Select clears input
                #     after selection so el.value will be empty — not an error).
                try:
                    page.wait_for_selector("[role='option']:visible", timeout=1000)
                    opts = page.locator("[role='option']:visible").all()
                    best_opt = None
                    for opt in opts[:15]:
                        try:
                            ot = (opt.inner_text() or "").strip()
                            if text.lower() in ot.lower() or ot.lower() in text.lower():
                                best_opt = opt
                                break
                        except Exception:
                            pass
                    if best_opt is None and opts:
                        best_opt = opts[0]  # fallback: first option
                    if best_opt is not None:
                        best_opt.scroll_into_view_if_needed()
                        time.sleep(random.uniform(0.05, 0.12))
                        # Human-Select sequence for React/Vue controlled dropdowns:
                        # dispatch_event registers React's synthetic event system,
                        # then mouse.click at coordinates confirms the selection.
                        try:
                            bb_opt = best_opt.bounding_box()
                            if bb_opt:
                                ox = bb_opt["x"] + bb_opt["width"]  / 2
                                oy = bb_opt["y"] + bb_opt["height"] / 2
                                page.dispatch_event(best_opt, "mousedown")
                                best_opt.focus()
                                time.sleep(random.uniform(0.03, 0.07))
                                page.mouse.click(ox, oy)
                                time.sleep(random.uniform(0.05, 0.10))
                                page.keyboard.press("Enter")
                            else:
                                page.dispatch_event(best_opt, "mousedown")
                                best_opt.focus()
                                best_opt.click(timeout=2000)
                                page.keyboard.press("Enter")
                        except Exception:
                            best_opt.click(timeout=2000)
                        time.sleep(random.uniform(0.20, 0.35))
                        dropdown_option_clicked = True
                        log.debug("[BrowserController] dropdown option selected for '%s'", text[:40])
                        return True  # selection done — React clears input; don't re-verify
                except Exception:
                    pass  # no dropdown appeared — normal text input

                # 4b. Verify: read back value or innerText (only for non-dropdown inputs)
                actual = element.evaluate(
                    "el => (el.value !== undefined ? el.value : el.innerText || '').trim()"
                )
                if actual:
                    log.debug("[BrowserController] type_verify OK (attempt %d): '%s'",
                              attempt, text[:40])
                    return True

                log.debug("[BrowserController] type_verify empty (attempt %d) — retrying", attempt)

            except Exception as exc:
                log.debug("[BrowserController] type attempt %d error: %s", attempt, exc)

        # 5. JS fallback — only for plain text inputs, never override a successful dropdown pick
        if dropdown_option_clicked:
            return True
        # JS fallback: React-compatible native property setter + synthetic events
        log.debug("[BrowserController] JS fallback injection for '%s'", text[:40])
        try:
            safe_text = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            injected = element.evaluate(f"""el => {{
                // Try native input prototype setter (React synthetic events need this)
                const inputProto    = window.HTMLInputElement.prototype;
                const textareaProto = window.HTMLTextAreaElement.prototype;
                const desc = (
                    Object.getOwnPropertyDescriptor(inputProto, 'value') ||
                    Object.getOwnPropertyDescriptor(textareaProto, 'value')
                );
                if (desc && desc.set) {{
                    desc.set.call(el, '{safe_text}');
                }} else {{
                    el.value = '{safe_text}';
                }}
                // Fire all necessary synthetic events for React/Vue to register the change
                ['input', 'change', 'blur'].forEach(evtName => {{
                    el.dispatchEvent(new Event(evtName, {{ bubbles: true, cancelable: true }}));
                    el.dispatchEvent(new InputEvent(evtName, {{
                        bubbles: true, cancelable: true,
                        data: '{safe_text}', inputType: 'insertText',
                    }}));
                }});
                return (el.value || el.innerText || '').trim();
            }}""")
            if injected:
                log.info("[BrowserController] JS injection succeeded: '%s'", text[:40])
                return True
        except Exception as exc:
            log.warning("[BrowserController] JS fallback failed: %s", exc)

        return False

    # ── SoM helpers ─────────────────────────────────────────────────────────

    def inject_som_overlay(self) -> dict[int, dict]:
        """Overlay numbered red boxes on all interactable elements.

        Returns a dict mapping SoM ID → element metadata.
        """
        try:
            raw = self.page.evaluate(_SOM_INJECT_JS)
            self._som_map = {int(k): v for k, v in json.loads(raw).items()}
            log.debug("[BrowserController] SoM: %d elements annotated", len(self._som_map))
        except Exception as exc:
            log.warning("[BrowserController] SoM inject error: %s", exc)
            self._som_map = {}
        return self._som_map

    def remove_som_overlay(self) -> None:
        """Remove all SoM overlays from the page."""
        try:
            self.page.evaluate(_SOM_REMOVE_JS)
        except Exception:
            pass

    def take_annotated_screenshot(self, path: str | Path) -> str:
        """Inject SoM, take screenshot, remove SoM. Returns base64-encoded PNG."""
        self.inject_som_overlay()
        time.sleep(0.3)  # let overlay render
        try:
            self.page.screenshot(path=str(path), full_page=False)
        finally:
            self.remove_som_overlay()
        with open(str(path), "rb") as f:
            return base64.b64encode(f.read()).decode()

    # ── Vision-fallback click ────────────────────────────────────────────────

    def try_click_vision_fallback(
        self,
        selector: str,
        description: str,
        intelligence: "IntelligenceLayer | None" = None,
        screenshot_path: str | Path | None = None,
    ) -> bool:
        """Try page.locator(selector). On failure, use vision model + SoM to find & click.

        Returns True if the element was clicked.
        """
        page = self.page

        # ── Path 1: Normal selector ──────────────────────────────────────────
        try:
            loc = page.locator(selector).first
            if loc.is_visible(timeout=2000):
                self.human_click(element=loc)
                log.debug("[BrowserController] click OK via selector: %s", selector[:60])
                return True
        except Exception as exc:
            log.debug("[BrowserController] selector click failed (%s): %s", selector[:40], exc)

        if intelligence is None:
            return False

        # ── Path 2: Vision model + SoM fallback ─────────────────────────────
        tmp_path = Path(screenshot_path or f"/tmp/som_fallback_{int(time.time())}.png")
        try:
            b64 = self.take_annotated_screenshot(tmp_path)
            som_id = intelligence.find_element_id(b64, description, self._som_map)
            if som_id is None:
                log.debug("[BrowserController] vision fallback: '%s' not found", description)
                return False

            meta = self._som_map.get(som_id, {})
            clicked = False
            for attr_sel in _meta_to_selectors(meta):
                try:
                    el = page.locator(attr_sel).first
                    if el.is_visible(timeout=800):
                        self.human_click(element=el)
                        log.info("[BrowserController] vision fallback clicked SoM#%d (%s): %s",
                                 som_id, description[:30], attr_sel[:50])
                        clicked = True
                        break
                except Exception:
                    pass

            if not clicked:
                # Last resort: click by screen coordinates from bounding box
                try:
                    bb_result = page.evaluate(f"""
                        () => {{
                            const box = document.querySelector('[data-som-id="{som_id}"]');
                            if (!box) return null;
                            const r = box.getBoundingClientRect();
                            return {{ x: r.left + r.width/2, y: r.top + r.height/2 }};
                        }}
                    """)
                    if bb_result:
                        self.human_click(x=bb_result["x"], y=bb_result["y"])
                        log.info("[BrowserController] vision fallback coordinate-click SoM#%d", som_id)
                        clicked = True
                except Exception as exc:
                    log.warning("[BrowserController] coordinate click error: %s", exc)

            return clicked

        except Exception as exc:
            log.warning("[BrowserController] vision fallback error: %s", exc)
            return False


def _meta_to_selectors(meta: dict) -> list[str]:
    """Build candidate CSS selectors from SoM element metadata."""
    sels = []
    tag  = meta.get("tag", "")
    eid  = meta.get("id", "")
    name = meta.get("name", "")
    ph   = meta.get("placeholder", "")
    al   = meta.get("ariaLabel", "")
    role = meta.get("role", "")

    if eid:
        sels.append(f"#{eid}")
    if name:
        sels.append(f"{tag}[name='{name}']" if tag else f"[name='{name}']")
    if al:
        sels.append(f"[aria-label='{al}']")
    if ph:
        sels.append(f"[placeholder='{ph}']")
    if role:
        sels.append(f"[role='{role}']")
    return sels


# ─────────────────────────────────────────────────────────────────────────────
# IntelligenceLayer
# ─────────────────────────────────────────────────────────────────────────────
class IntelligenceLayer:
    """NVIDIA NIM dual-model layer.

    Text model  (Nemotron / llama-3.1-70b)  → field mapping from accessibility tree.
    Vision model (Llama-3.2-11b)            → SoM navigation + red-line error scan.
    """

    def __init__(
        self,
        text_api_key: str  = _NIM_TEXT_KEY,
        vision_api_key: str = _NIM_VISION_KEY,
    ):
        self._text_key   = text_api_key
        self._vision_key = vision_api_key

    # ── Text model: field mapping via Nemotron ───────────────────────────────

    def map_fields(
        self,
        form_fields: list[dict],
        profile_data: dict,
    ) -> dict[str, str]:
        """Use text model to map profile_data onto form_fields.

        Args:
            form_fields:  List of dicts with keys: label, type, options (optional), required.
            profile_data: Flat dict of candidate data.

        Returns dict mapping field_label → value_to_fill.
        """
        if not form_fields:
            return {}

        # Extract identity anchors from flat profile for explicit system-prompt injection
        _name      = profile_data.get("full_name", "Gunakarthik Naidu Lanka")
        # Hard-coded: always use profile.personal.first_name ("Gunakarthik Naidu"), never preferred_name
        _first     = profile_data.get("first_name", "Gunakarthik Naidu")
        _last      = profile_data.get("last_name", "Lanka")
        _company   = profile_data.get("current_company", "") or "Velocity Tech"
        _email     = profile_data.get("email", "")
        _phone     = profile_data.get("phone", "")
        _school    = profile_data.get("school", "Arizona State University")

        # ── Inject Learning Buffer (past failures) into system prompt ────────
        _learning_buf = ""
        try:
            from hireagent.apply.saas_observer import read_learning_buffer
            _learning_buf = read_learning_buffer(max_chars=2000)
        except Exception:
            pass

        _past_mistakes_section = ""
        if _learning_buf.strip():
            _past_mistakes_section = (
                "══ PAST MISTAKES TO AVOID (self-correction log) ══\n"
                + _learning_buf.strip()
                + "\n\n"
            )

        _gender_anchor = profile_data.get("gender", "Male")

        system_prompt = (
            "You are a job-application form-filling assistant. "
            "Given a list of form fields and a candidate profile, return ONLY a valid JSON object "
            "mapping each field label to the best matching value from the profile.\n\n"

            "══ CANDIDATE IDENTITY (MEMORIZE — DO NOT CONFUSE) ══\n"
            f"  FULL NAME : {_name!r}\n"
            f"  FIRST NAME: {_first!r}  ← ONLY for 'First Name' / 'Given Name' fields — HARD-CODED, do not derive\n"
            f"  LAST NAME : {_last!r}   ← ONLY for 'Last Name' / 'Family Name' fields\n"
            f"  EMPLOYER  : {_company!r} ← use for ANY 'Current Company', 'Employer', 'Organization', 'Firm' field\n"
            f"  EMAIL     : {_email!r}\n"
            f"  PHONE     : {_phone!r}\n"
            f"  SCHOOL    : {_school!r}\n"
            f"  GENDER    : {_gender_anchor!r}  ← LOCKED — NEVER select 'Decline to Self-Identify'\n\n"

            "══ CRITICAL RULES ══\n"
            f"  ✗ NEVER put {_name!r} into a Company/Employer/Organization/Firm field.\n"
            f"  ✓ For any 'Company'/'Employer'/'Organization' field → use {_company!r}.\n"
            f"  ✓ For 'First Name' / 'Given Name' fields → ALWAYS use {_first!r} exactly.\n"
            f"  ✓ For 'Gender' / 'Sex' fields → ALWAYS select the option containing {_gender_anchor!r}. "
            "NEVER select 'Decline to Self-Identify', 'Prefer not to say', or any similar opt-out.\n"
            "  ✓ For 'Degree' / 'Education Level' fields → prefer 'Master of Science' or closest alias "
            "('Masters', 'M.S.', 'Graduate Degree'). NEVER return a bare degree name if options are listed.\n"
            "  ✓ For select/dropdown fields: return the EXACT text of one of the listed options.\n"
            "  ✓ 'Are you authorized to work in the US?' → 'Yes'\n"
            "  ✓ 'Will you require sponsorship now?' → 'No'\n"
            "  ✓ 'Will you require sponsorship in future?' → 'Yes'\n"
            "  ✓ 'Are you located in the US or Canada?' / 'Are you in the US or Canada?' → 'Yes'\n"
            "  ✓ State of residency / current state → 'Arizona'\n"
            "  ✓ Salary / compensation / expected salary → '90000'\n"
            "  ✓ Currency → 'USD'\n"
            "  ✓ Pronouns → 'He/Him'\n"
            "  ✓ Yes/No questions → 'Yes' or 'No' (exact case, matching an option if given)\n"
            "  ✓ If a field has options listed, your value MUST be one of those exact strings.\n"
            "  ✓ FUZZY DROPDOWN: If answer intent is 'No', pick the most negative/declining option "
            "(e.g. 'No, I do not have a disability'). NEVER select 'I prefer not to answer' / 'Decline' / 'I don't wish to answer'. "
            "If intent is 'Yes', pick the most affirming option. NEVER return bare 'Yes'/'No' when options exist.\n"
            "  ✗ Never fabricate data. If no match exists, omit the field.\n\n"

            + _past_mistakes_section

            + "RESPONSE FORMAT: {\"fields\": {\"Field Label\": \"value\", ...}}\n"
            "Return ONLY the JSON object, nothing else."
        )
        log.info("[IntelligenceLayer] Sending %d fields to 120B model | name=%s | company=%s | school=%s",
                 len(form_fields), _name, _company, _school)

        # ── DOM Simplification: strip <div>, <span>, <a> noise from labels ──────
        # The 120B model can get overwhelmed by HTML noise in label strings, leading
        # to truncated JSON responses and early incorrect action selection.
        _HTML_TAG_RE = re.compile(r"<(?:div|span|a|p|strong|em|b|i|u|br|script|style)[^>]*>|</(?:div|span|a|p|strong|em|b|i|u|br|script|style)>", re.IGNORECASE)

        def _strip_html_noise(text: str) -> str:
            """Remove div/span/a and other non-semantic tags; keep label/input/select."""
            cleaned = _HTML_TAG_RE.sub("", text)
            return re.sub(r"\s+", " ", cleaned).strip()

        _clean_fields = [
            {
                "label":    _strip_html_noise(f.get("label", "")),
                "type":     f.get("type", "text"),
                "required": f.get("required", False),
                "options":  f.get("options", []),
            }
            for f in form_fields
        ]

        user_msg = (
            f"Form fields:\n{json.dumps(_clean_fields, indent=2)}\n\n"
            f"Candidate profile:\n{json.dumps(profile_data, indent=2)}"
        )

        raw = self._call_text_model(system_prompt, user_msg, max_tokens=2048)
        if not raw:
            return {}

        # Strip markdown fences if present
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw.strip())
        raw = re.sub(r"\n?```$", "", raw).strip()

        # Build a lookup: field_label → list of valid options (for fuzzy matching)
        _field_options: dict[str, list[str]] = {
            f["label"]: f.get("options", [])
            for f in form_fields
            if f.get("options")
        }

        def _fuzzy_match_option(value: str, options: list[str]) -> str:
            """If value doesn't exactly match an option, fuzzy-match boolean-style answers."""
            if not options:
                return value
            # Exact match wins
            if value in options:
                return value
            # Case-insensitive exact
            val_lower = value.lower().strip()
            for opt in options:
                if opt.lower().strip() == val_lower:
                    return opt
            # Fuzzy: "No" → most negative/declining option
            _NO_SIGNALS  = ("no", "not", "none", "decline", "prefer not", "i do not",
                             "do not wish", "not a protected", "not applicable", "n/a")
            _YES_SIGNALS = ("yes", "i am", "i have", "authorized", "affirm")
            if val_lower in ("no", "false", "0"):
                # Find the option that most strongly signals "no"
                best = None
                for opt in options:
                    opt_l = opt.lower()
                    if any(s in opt_l for s in _NO_SIGNALS):
                        best = opt
                        break
                if best:
                    log.info("[IntelligenceLayer] fuzzy 'No' → '%s'", best)
                    return best
            elif val_lower in ("yes", "true", "1"):
                for opt in options:
                    opt_l = opt.lower()
                    if any(s in opt_l for s in _YES_SIGNALS):
                        log.info("[IntelligenceLayer] fuzzy 'Yes' → '%s'", opt)
                        return opt
            # Substring: value contained in an option
            for opt in options:
                if val_lower in opt.lower():
                    return opt
            # No match found — return original (LLM may have hallucinated)
            log.warning("[IntelligenceLayer] No option match for '%s' in %s", value, options[:5])
            return value

        _DECLINE_SIGNALS = (
            "decline", "prefer not", "i do not wish", "do not wish to",
            "not specified", "no response", "choose not", "opt out",
        )

        def _validate_mapping(raw_result: dict) -> dict:
            """Post-mapping validation: fix identity/company/EEO fields and fuzzy-match dropdowns."""
            name_lower = _name.lower()
            _COMPANY_KWS = {"company", "employer", "organization", "organisation", "firm", "current employer"}
            _FIRST_KWS   = {"first name", "given name", "firstname", "preferred name"}
            _GENDER_KWS  = {"gender", "sex"}
            validated: dict[str, str] = {}
            for field_label, value in raw_result.items():
                label_lower = field_label.lower()

                # Hard-code guard: first name fields always use profile first name
                if any(kw in label_lower for kw in _FIRST_KWS):
                    if value != _first:
                        log.warning(
                            "[IntelligenceLayer] ✗ First name guard: '%s' → override '%s' → '%s'",
                            field_label, value, _first,
                        )
                    validated[field_label] = _first
                    continue

                # EEO Gender anchor: NEVER "Decline to Self-Identify" or any opt-out
                if any(kw in label_lower for kw in _GENDER_KWS):
                    val_lower = value.lower()
                    opts = _field_options.get(field_label, [])
                    # Always prefer the option that matches the profile gender anchor
                    # Try: exact gender → "Man" → first non-decline option
                    _gender_candidates = [_gender_anchor, "Male", "Man", "M"]
                    corrected = None
                    if opts:
                        for _gc in _gender_candidates:
                            for opt in opts:
                                if _gc.lower() in opt.lower():
                                    corrected = opt
                                    break
                            if corrected:
                                break
                        if not corrected:
                            # Pick first non-decline option
                            for opt in opts:
                                if not any(sig in opt.lower() for sig in _DECLINE_SIGNALS):
                                    corrected = opt
                                    break
                    corrected = corrected or _gender_anchor
                    if any(sig in val_lower for sig in _DECLINE_SIGNALS) or corrected != value:
                        log.warning(
                            "[IntelligenceLayer] ✗ Gender guard: '%s' → '%s' → corrected to '%s'",
                            field_label, value, corrected,
                        )
                    validated[field_label] = corrected
                    continue

                # EEO Disability guard: ALWAYS "No" — NEVER "I don't wish to answer" or any opt-out
                if "disability" in label_lower:
                    val_lower = value.lower()
                    opts = _field_options.get(field_label, [])
                    _dis_candidates = ["No", "No, I Don't Have a Disability",
                                       "No, I do not have a disability",
                                       "I don't have a disability",
                                       "I do not have a disability", "No disability"]
                    corrected = None
                    if opts:
                        for _dc in _dis_candidates:
                            for opt in opts:
                                if _dc.lower() in opt.lower():
                                    corrected = opt
                                    break
                            if corrected:
                                break
                        if not corrected:
                            # Pick first non-decline option
                            for opt in opts:
                                if not any(sig in opt.lower() for sig in _DECLINE_SIGNALS):
                                    corrected = opt
                                    break
                    corrected = corrected or "No"
                    if any(sig in val_lower for sig in _DECLINE_SIGNALS) or corrected != value:
                        log.warning(
                            "[IntelligenceLayer] ✗ Disability guard: '%s' → '%s' → corrected to '%s'",
                            field_label, value, corrected,
                        )
                    validated[field_label] = corrected
                    continue

                # EEO Race guard: ALWAYS use profile value
                if "race" in label_lower or "ethnicity" in label_lower:
                    val_lower = value.lower()
                    opts = _field_options.get(field_label, [])
                    _race_candidates = [_race_anchor, "Asian", "Asian (Not Hispanic or Latino)",
                                        "Asian or Pacific Islander"] if hasattr(type(self), '_race_anchor') or True else ["Asian"]
                    corrected = None
                    if opts:
                        for _rc in ["Asian", "Asian (Not Hispanic or Latino)", "Asian or Pacific Islander"]:
                            for opt in opts:
                                if _rc.lower() in opt.lower():
                                    corrected = opt
                                    break
                            if corrected:
                                break
                        if not corrected:
                            for opt in opts:
                                if not any(sig in opt.lower() for sig in _DECLINE_SIGNALS):
                                    corrected = opt
                                    break
                    corrected = corrected or "Asian"
                    if any(sig in val_lower for sig in _DECLINE_SIGNALS) or corrected != value:
                        log.warning(
                            "[IntelligenceLayer] ✗ Race guard: '%s' → '%s' → corrected to '%s'",
                            field_label, value, corrected,
                        )
                    validated[field_label] = corrected
                    continue

                if any(kw in label_lower for kw in _COMPANY_KWS):
                    # Reject if mapped value IS the user's name
                    if value.lower() == name_lower or name_lower.startswith(value.lower().rstrip()):
                        log.warning(
                            "[IntelligenceLayer] ✗ Rejected hallucination: '%s' → '%s' "
                            "(user name put in company field). Correcting to '%s'.",
                            field_label, value, _company,
                        )
                        if _company:
                            validated[field_label] = _company
                        # else omit — better empty than wrong
                    else:
                        validated[field_label] = value
                else:
                    # Fuzzy option matching for dropdown fields
                    opts = _field_options.get(field_label, [])
                    validated[field_label] = _fuzzy_match_option(value, opts)

            return validated

        # ── Greedy JSON extraction: strip "Thinking" preamble from 120B model ──
        _fb = raw.find('{')
        _lb = raw.rfind('}')
        if _fb != -1 and _lb > _fb:
            raw = raw[_fb:_lb + 1]

        try:
            # raw_decode handles trailing text/comments the model appends
            decoder = json.JSONDecoder()
            parsed, _ = decoder.raw_decode(raw)
            result = parsed.get("fields", parsed)
            clean = {str(k): str(v) for k, v in result.items() if v not in (None, "", "null")}
            clean = _validate_mapping(clean)
            log.info("[IntelligenceLayer] Nemotron mapped %d field(s)", len(clean))
            return clean
        except Exception as exc:
            log.warning("[IntelligenceLayer] map_fields JSON parse error: %s | raw=%s",
                        exc, raw[:200])
            # ── Partial JSON recovery — extract completed "key": "value" pairs ──
            # Handles 120B streaming truncation mid-response
            try:
                pairs = re.findall(r'"([^"]+)"\s*:\s*"([^"]*)"', raw)
                if pairs:
                    recovered = {k: v for k, v in pairs
                                 if v not in ("", "null", "none", "n/a")}
                    # Strip structural keys like "fields"
                    recovered.pop("fields", None)
                    if recovered:
                        recovered = _validate_mapping(recovered)
                        log.info("[IntelligenceLayer] Partial JSON recovery: %d fields", len(recovered))
                        return recovered
            except Exception:
                pass
            return {}

    # ── Vision model: find SoM element ID ───────────────────────────────────

    def find_element_id(
        self,
        screenshot_b64: str,
        description: str,
        som_map: dict[int, dict] | None = None,
    ) -> int | None:
        """Look at the SoM-annotated screenshot and return the ID of the described element.

        Args:
            screenshot_b64: Base64-encoded PNG of the annotated screenshot.
            description:    e.g. "the Submit button" or "First Name input"
            som_map:        Optional SoM map to include element hints in the prompt.

        Returns integer SoM ID or None if not found.
        """
        hint = ""
        if som_map:
            summaries = []
            for sid, meta in list(som_map.items())[:60]:
                label = (meta.get("ariaLabel") or meta.get("placeholder") or
                         meta.get("text") or meta.get("name") or "")
                if label:
                    summaries.append(f"#{sid}:{meta.get('tag','')} \"{label[:30]}\"")
            if summaries:
                hint = "\n\nVisible elements:\n" + ", ".join(summaries[:40])

        prompt = (
            f"Look at this annotated screenshot. Each interactive element has a red box with a number.\n"
            f"Find: {description}{hint}\n\n"
            f"Reply with ONLY the integer ID number of that element, nothing else. "
            f"If you cannot find it, reply with 0."
        )

        raw = self._call_vision_model(prompt, screenshot_b64)
        if not raw:
            return None

        match = re.search(r"\b(\d+)\b", raw.strip())
        if match:
            val = int(match.group(1))
            return val if val > 0 else None
        return None

    # ── Vision model: red-line error scan ───────────────────────────────────

    def scan_for_errors(self, screenshot_b64: str) -> list[str]:
        """Use vision model to find red validation error text on the page.

        Returns a list of error message strings (empty list if none found).
        Specially detects degree/education field errors and provides recovery hints.
        """
        prompt = (
            "Look at this screenshot of a job application form.\n"
            "Task 1: Identify any red-colored validation error messages or field-level error text. "
            "List each error message exactly as it appears, one per line.\n"
            "Task 2: If you see 'Degree is required', 'Education is required', or a red border "
            "on a Degree/Education dropdown, add a line: "
            "DEGREE_ERROR: <name of the field with the red border>.\n"
            "Task 3: If you see any red error text at all, add a line: HAS_ERRORS.\n"
            "If there are NO error messages and NO red borders, reply with only: NO_ERRORS"
        )
        raw = self._call_vision_model(prompt, screenshot_b64)
        if not raw or "NO_ERRORS" in raw.upper():
            return []
        lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
        return [ln for ln in lines if len(ln) < 300]

    def scan_for_errors_with_field_ids(self, screenshot_b64: str) -> list[dict]:
        """Use Llama 3.2 Vision + SoM screenshot to identify fields with validation errors.

        Returns list of dicts: [{"field_id": int|None, "label": str, "error": str}]
        where field_id is the SoM overlay number visible in the screenshot.
        Returns [] when the form is clean.
        """
        prompt = (
            "Look at this annotated job application form screenshot. "
            "Numbered red boxes mark each interactive element.\n\n"
            "Find ALL of the following problems:\n"
            "1. Red validation error messages visible below any field\n"
            "2. Dropdowns or selects still showing 'Select...' or 'Choose...'\n"
            "3. Required fields that are visibly empty\n\n"
            "For EACH problem output exactly one JSON object per line (no extra text):\n"
            "{\"field_id\": <SoM number or null>, \"label\": \"<field label>\", \"error\": \"<what is wrong>\"}\n\n"
            "If there are NO problems at all, respond with exactly: NO_ERRORS"
        )
        raw = self._call_vision_model(prompt, screenshot_b64)
        if not raw or "NO_ERRORS" in raw.upper():
            return []

        results: list[dict] = []
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "error" in obj:
                    results.append({
                        "field_id": obj.get("field_id"),
                        "label":    str(obj.get("label", "")),
                        "error":    str(obj.get("error", "")),
                    })
            except Exception:
                # Non-JSON line: extract as plain error if it contains useful keywords
                lw = line.lower()
                if any(k in lw for k in ("select", "required", "error", "empty", "choose")):
                    results.append({"field_id": None, "label": "", "error": line[:200]})
        return results

    # ── Senior QA Auditor ────────────────────────────────────────────────────

    _AUDITOR_SYSTEM = (
        "You are a Senior QA Auditor for an automated job application bot. "
        "Your ONLY job is to verify form correctness against ground truth data.\n\n"
        "GROUND TRUTH:\n"
        "  FULL NAME  : Gunakarthik Naidu Lanka\n"
        "  FIRST NAME : Gunakarthik Naidu  (NEVER just 'Guna')\n"
        "  LAST NAME  : Lanka\n"
        "  EDUCATION  : Master of Science  (or Master's Degree)\n"
        "  GENDER     : Male\n"
        "  RACE       : Asian\n"
        "  DISABILITY : No  (NEVER 'Decline' or 'I don\\'t wish to answer')\n"
        "  CITIZENSHIP: F1 OPT\n\n"
        "AUDIT RULES:\n"
        "1. RED SEA  — any red text / red border on a field = FAIL\n"
        "2. FIRST NAME contains only 'Guna' (not the full name) = FAIL\n"
        "3. Any dropdown showing 'Select...', 'Choose...', or placeholder = FAIL\n"
        "4. Gender is 'Decline' or 'Prefer not to say' = FAIL\n"
        "5. Disability is 'I don\\'t wish to answer' or 'Decline' = FAIL\n\n"
        "OUTPUT: respond with STRICT JSON only — no markdown, no explanation:\n"
        "{\"status\": \"PASS\" | \"FAIL\", \"detected_blunder\": \"<description or empty>\", "
        "\"offending_element_id\": <SoM integer or null>, "
        "\"fix_instruction\": \"<exactly what to type or click, or empty>\"}"
    )

    def audit_screen(self, screenshot_b64: str, som_map: dict | None = None) -> dict:
        """Run the Senior QA Auditor vision check on the current form screenshot.

        Returns a dict with keys: status, detected_blunder, offending_element_id, fix_instruction.
        status is 'PASS' or 'FAIL'.
        """
        hint = ""
        if som_map:
            hint = "\n\nSoM element map (id → metadata):\n"
            for sid, meta in list(som_map.items())[:40]:
                hint += f"  #{sid}: tag={meta.get('tag','')} role={meta.get('role','')} text={meta.get('text','')[:40]!r}\n"

        user_msg = (
            "Audit this job application form screenshot against the ground truth rules.\n"
            + hint
        )

        # Use vision model with QA auditor system prompt
        raw = self._call_vision_model(
            prompt=user_msg,
            image_b64=screenshot_b64,
            max_tokens=300,
            system_prompt=self._AUDITOR_SYSTEM,
        )

        # Parse the JSON response
        try:
            raw_clean = raw.strip()
            # Strip markdown fences if model wrapped it
            if raw_clean.startswith("```"):
                raw_clean = raw_clean.split("```")[1]
                if raw_clean.startswith("json"):
                    raw_clean = raw_clean[4:]
            result = json.loads(raw_clean)
            # Normalise keys
            return {
                "status":               str(result.get("status", "PASS")).upper(),
                "detected_blunder":     str(result.get("detected_blunder", "")),
                "offending_element_id": result.get("offending_element_id"),
                "fix_instruction":      str(result.get("fix_instruction", "")),
            }
        except Exception as exc:
            log.warning("[Auditor] JSON parse error: %s | raw: %s", exc, raw[:200])
            # If model said FAIL anywhere, treat as fail-safe
            if "FAIL" in (raw or "").upper():
                return {
                    "status": "FAIL",
                    "detected_blunder": raw[:200],
                    "offending_element_id": None,
                    "fix_instruction": "",
                }
            return {"status": "PASS", "detected_blunder": "", "offending_element_id": None, "fix_instruction": ""}

    # ── Internal: call text model ────────────────────────────────────────────

    _FALLBACK_TEXT_MODEL = "meta/llama-3.1-70b-instruct"
    _TEXT_TIMEOUT_S      = 45  # seconds before falling back to 70B
    _FALLBACK_TIMEOUT_S  = 30  # seconds before giving up on 70B fallback

    def _call_text_model(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        """Stream text model response with 45s timeout and 70B fallback.

        Heartbeat: logs 'Brain is thinking...' every 5s so we know it hasn't hung.
        On timeout → retries with meta/llama-3.1-70b-instruct (no thinking tokens).
        """
        import threading

        def _stream_model(model: str, use_thinking: bool) -> str:
            from openai import OpenAI
            client = OpenAI(base_url=_NIM_BASE_URL, api_key=self._text_key, timeout=60.0)
            kwargs: dict = dict(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                temperature=temperature,
                top_p=0.95,
                max_tokens=max_tokens,
                stream=True,
            )
            if use_thinking:
                kwargs["extra_body"] = {
                    "chat_template_kwargs": {"enable_thinking": True},
                    "reasoning_budget": 16384,
                }
            completion = client.chat.completions.create(**kwargs)
            parts: list[str] = []
            for chunk in completion:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if getattr(delta, "reasoning_content", None):
                    continue
                if delta.content:
                    parts.append(delta.content)
            raw = "".join(parts).strip()
            # Strip <think>...</think> blocks (Nemotron 3 Super may include them in content)
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            # If response starts with reasoning text (not JSON), find first {
            if raw and not raw.startswith("{") and "{" in raw:
                raw = raw[raw.index("{"):]
            return raw

        # ── Heartbeat thread ────────────────────────────────────────────────────
        _stop = threading.Event()
        def _heartbeat():
            count = 0
            while not _stop.wait(5):
                count += 1
                log.info("[IntelligenceLayer] Brain is thinking... (%ds)", count * 5)
        _hb = threading.Thread(target=_heartbeat, daemon=True)
        _hb.start()

        try:
            # ── Try 120B with timeout ───────────────────────────────────────────
            _result: list[str] = [""]
            _exc: list[Exception | None] = [None]

            def _run_primary():
                try:
                    _result[0] = _stream_model(_TEXT_MODEL, use_thinking=True)
                except Exception as e:
                    _exc[0] = e

            t = threading.Thread(target=_run_primary, daemon=True)
            t.start()
            t.join(timeout=self._TEXT_TIMEOUT_S)

            def _run_fallback() -> str:
                """Call the 70B fallback model with its own timeout."""
                _fb_result: list[str] = [""]
                _fb_exc: list[Exception | None] = [None]

                def _do_fb():
                    try:
                        _fb_result[0] = _stream_model(self._FALLBACK_TEXT_MODEL, use_thinking=False)
                    except Exception as e:
                        _fb_exc[0] = e

                fb = threading.Thread(target=_do_fb, daemon=True)
                fb.start()
                fb.join(timeout=self._FALLBACK_TIMEOUT_S)
                if fb.is_alive():
                    log.warning("[IntelligenceLayer] 70B fallback timed out after %ds — giving up",
                                self._FALLBACK_TIMEOUT_S)
                    return ""
                if _fb_exc[0]:
                    log.warning("[IntelligenceLayer] 70B fallback error: %s", _fb_exc[0])
                    return ""
                return _fb_result[0]

            if t.is_alive():
                log.warning(
                    "[IntelligenceLayer] 120B timed out after %ds — falling back to 70B",
                    self._TEXT_TIMEOUT_S,
                )
                return _run_fallback()

            if _exc[0]:
                log.warning("[IntelligenceLayer] 120B error: %s — falling back to 70B", _exc[0])
                return _run_fallback()

            return _result[0]

        except Exception as exc:
            log.warning("[IntelligenceLayer] text model error: %s", exc)
            return ""
        finally:
            _stop.set()

    # ── Internal: call vision model ──────────────────────────────────────────

    def _call_vision_model(
        self,
        prompt: str,
        image_b64: str,
        max_tokens: int = 512,
        system_prompt: str | None = None,
    ) -> str:
        """Send prompt + base64 image to Llama-3.2-vision via NVIDIA NIM."""
        headers = {
            "Authorization": f"Bearer {self._vision_key}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_b64}",
                    },
                },
            ],
        })
        payload = {
            "model": _VISION_MODEL,
            "messages": messages,
            "max_tokens":        max_tokens,
            "temperature":       0.2,
            "top_p":             1.0,
            "frequency_penalty": 0.0,
            "presence_penalty":  0.0,
            "stream":            True,
        }
        try:
            resp = requests.post(_VISION_API_URL, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            parts: list[str] = []
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace")
                if line.startswith("data: "):
                    line = line[6:]
                if line.strip() in ("[DONE]", ""):
                    continue
                try:
                    obj = json.loads(line)
                    delta = obj.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        parts.append(content)
                except Exception:
                    pass
            return "".join(parts).strip()
        except Exception as exc:
            log.warning("[IntelligenceLayer] vision model error: %s", exc)
            return ""


# ─────────────────────────────────────────────────────────────────────────────
# CaptchaSolver — Enterprise-Aware with pageAction extraction + session sync
# ─────────────────────────────────────────────────────────────────────────────
class CaptchaSolver:
    """CapSolver-backed CAPTCHA solver.

    Supports:
    - hCaptcha (div / iframe / inline-script)
    - reCAPTCHA v2 / v2 Enterprise (div, iframe, inline-script)
    - reCAPTCHA v3 Enterprise (grecaptcha.enterprise.execute extraction)
    - Cloudflare Turnstile
    - Arkose FunCaptcha

    Enterprise features:
    - Extracts websiteKey AND pageAction from grecaptcha.enterprise.execute calls
    - Passes navigator.userAgent from the live Playwright session to CapSolver
      so the token fingerprint matches the browser
    - After token injection, searches ___grecaptcha_cfg for onSuccess callbacks
      and fires them to unlock disabled Submit buttons
    """

    MAX_BALANCE_ATTEMPTS = 2   # Hard cap to conserve CapSolver balance

    def __init__(self, api_key: str | None = None):
        self._key = api_key or os.environ.get("CAPSOLVER_API_KEY", "")

    def solve(self, page, page_url: str, max_attempts: int | None = None) -> bool:
        """Detect and solve the CAPTCHA on `page`.

        Returns True if solved and token injected, False otherwise.
        max_attempts defaults to MAX_BALANCE_ATTEMPTS (2) to conserve balance.
        """
        if not self._key:
            log.warning("[CaptchaSolver] CAPSOLVER_API_KEY not set — skipping")
            return False

        max_attempts = max_attempts or self.MAX_BALANCE_ATTEMPTS

        info = self._detect(page)
        if not info:
            log.warning("[CaptchaSolver] No CAPTCHA detected / sitekey not found")
            return False

        ctype   = info["type"]
        sitekey = info["sitekey"]
        log.info("[CaptchaSolver] ┌─ CAPTCHA detected ──────────────────────────────────")
        log.info("[CaptchaSolver] │  type       = %s", ctype)
        log.info("[CaptchaSolver] │  sitekey    = %s…%s", sitekey[:8], sitekey[-4:] if len(sitekey) > 12 else "")
        log.info("[CaptchaSolver] │  pageAction = %s", info.get("pageAction", ""))
        log.info("[CaptchaSolver] │  invisible  = %s", info.get("isInvisible", False))
        log.info("[CaptchaSolver] └────────────────────────────────────────────────────")

        for attempt in range(1, max_attempts + 1):
            log.info("[CaptchaSolver] Attempt %d/%d → requesting token…", attempt, max_attempts)
            token = self._request_token(page, page_url, ctype, sitekey, info)
            if token:
                log.info("[CaptchaSolver] ✓ Token received (%d chars) — injecting", len(token))
                self._inject_token(page, ctype, token)
                return True
            log.warning("[CaptchaSolver] Attempt %d failed — %s",
                        attempt, "balance check" if attempt == max_attempts else "retrying in 3s")
            if attempt < max_attempts:
                time.sleep(3)

        log.warning("[CaptchaSolver] All %d attempt(s) exhausted for %s", max_attempts, ctype)
        return False

    # ── Detection ────────────────────────────────────────────────────────────

    def _detect(self, page) -> dict | None:
        """Retry up to 3 times (CAPTCHAs can appear with a delay in modals)."""
        for _attempt in range(3):
            result = self._detect_once(page)
            if result:
                return result
            if _attempt < 2:
                time.sleep(2)
        return None

    def _detect_once(self, page) -> dict | None:
        """Single detection pass across all supported CAPTCHA types."""
        try:
            return page.evaluate("""() => {
                // ── hCaptcha (div container) ─────────────────────────────────
                const hcDiv = document.querySelector(
                    '.h-captcha[data-sitekey], [data-hcaptcha-widget-id], div[data-sitekey*="hcaptcha"]'
                );
                if (hcDiv) {
                    const sk = hcDiv.getAttribute('data-sitekey') || '';
                    if (sk) return { type: 'hcaptcha', sitekey: sk, pageAction: '', isInvisible: false };
                }
                // ── hCaptcha (iframe) ─────────────────────────────────────────
                const hcFrame = document.querySelector('iframe[src*="hcaptcha.com"]');
                if (hcFrame) {
                    try {
                        const u  = new URL(hcFrame.src);
                        const sk = u.searchParams.get('sitekey') || '';
                        if (sk) return { type: 'hcaptcha', sitekey: sk, pageAction: '', isInvisible: false };
                    } catch(e) {}
                    const parent = hcFrame.closest('[data-sitekey]');
                    if (parent) {
                        const sk = parent.getAttribute('data-sitekey') || '';
                        if (sk) return { type: 'hcaptcha', sitekey: sk, pageAction: '', isInvisible: false };
                    }
                    for (const s of document.querySelectorAll('script:not([src])')) {
                        const m = s.textContent.match(/hcaptcha[\\s\\S]{0,200}sitekey[\\s]*[=:\\s]+['"]([a-f0-9-]{36})['"]/);
                        if (m) return { type: 'hcaptcha', sitekey: m[1], pageAction: '', isInvisible: false };
                    }
                }

                // ── reCAPTCHA Enterprise: grecaptcha.enterprise.execute() ─────
                // Highest-priority extraction — used by Greenhouse/LinkedIn
                for (const s of document.querySelectorAll('script:not([src])')) {
                    const txt = s.textContent || '';
                    // Match: grecaptcha.enterprise.execute('SITEKEY', {action: 'ACTION'})
                    const m = txt.match(
                        /grecaptcha[.]enterprise[.]execute\\s*\\(\\s*['"]([0-9A-Za-z_-]{20,80})['"]/
                    );
                    if (m) {
                        const actionM = txt.match(/action[\\s]*:[\\s]*['"]([a-zA-Z0-9/_-]{1,80})['"]/);
                        return {
                            type:        'recaptchav3enterprise',
                            sitekey:     m[1],
                            pageAction:  actionM ? actionM[1] : 'submit',
                            isInvisible: true,
                        };
                    }
                    // Also catch sitekey in external <script src> tag configs
                    const m2 = txt.match(
                        /['"]siteKey['"]\\s*:\\s*['"]([0-9A-Za-z_-]{20,80})['"]/
                    );
                    if (m2) {
                        const actionM2 = txt.match(/['"]action['"]\\s*:\\s*['"]([a-zA-Z0-9/_-]{1,80})['"]/);
                        return {
                            type:        'recaptchav3enterprise',
                            sitekey:     m2[1],
                            pageAction:  actionM2 ? actionM2[1] : '',
                            isInvisible: true,
                        };
                    }
                }

                // ── reCAPTCHA v2 / Enterprise (visible div) ───────────────────
                const rcDiv = document.querySelector('.g-recaptcha[data-sitekey]');
                if (rcDiv) {
                    const sk        = rcDiv.getAttribute('data-sitekey') || '';
                    const action    = rcDiv.getAttribute('data-action')  || '';
                    const invisible = rcDiv.getAttribute('data-size') === 'invisible';
                    return { type: 'recaptchav2', sitekey: sk, pageAction: action, isInvisible: invisible };
                }

                // ── reCAPTCHA (iframe-based detection) ────────────────────────
                const rcFrameSels = [
                    'iframe[src*="recaptcha/api2"]',
                    'iframe[src*="recaptcha/enterprise"]',
                    'iframe[src*="google.com/recaptcha"]',
                ];
                for (const fSel of rcFrameSels) {
                    const rcFrame = document.querySelector(fSel);
                    if (!rcFrame) continue;
                    try {
                        const u          = new URL(rcFrame.src);
                        const sk         = u.searchParams.get('k') || u.searchParams.get('sitekey') || '';
                        const action     = u.searchParams.get('action') || '';
                        const isEnterprise = rcFrame.src.includes('enterprise');
                        const invisible  = u.searchParams.get('size') === 'invisible';
                        if (sk) return {
                            type:        isEnterprise ? 'recaptchav2enterprise' : 'recaptchav2',
                            sitekey:     sk,
                            pageAction:  action,
                            isInvisible: invisible,
                        };
                    } catch(e) {}
                }

                // ── reCAPTCHA Enterprise — generic script-tag extraction ───────
                const scripts = Array.from(document.querySelectorAll('script:not([src])'));
                for (const s of scripts) {
                    const m1 = s.textContent.match(/["']sitekey["']\\s*:\\s*["']([0-9A-Za-z_-]{20,80})["']/);
                    if (m1) {
                        const m2 = s.textContent.match(/action\\s*:\\s*["']([a-zA-Z0-9/_-]{1,80})["']/);
                        return {
                            type:        'recaptchav2enterprise',
                            sitekey:     m1[1],
                            pageAction:  m2 ? m2[1] : '',
                            isInvisible: true,
                        };
                    }
                    const m3 = s.textContent.match(/grecaptcha[.]execute\\s*\\(["']([0-9A-Za-z_-]{20,80})["']/);
                    if (m3) {
                        const m4 = s.textContent.match(/action\\s*:\\s*["']([a-zA-Z0-9/_-]{1,80})["']/);
                        return {
                            type:        'recaptchav2enterprise',
                            sitekey:     m3[1],
                            pageAction:  m4 ? m4[1] : '',
                            isInvisible: true,
                        };
                    }
                }

                // ── Cloudflare Turnstile (div) ────────────────────────────────
                const cfDiv = document.querySelector(
                    '.cf-turnstile[data-sitekey], [data-cf-turnstile-sitekey], [data-sitekey*="0x"]'
                );
                if (cfDiv) return {
                    type:        'turnstile',
                    sitekey:     cfDiv.getAttribute('data-sitekey') || cfDiv.getAttribute('data-cf-turnstile-sitekey') || '',
                    pageAction:  cfDiv.getAttribute('data-action')  || '',
                    isInvisible: false,
                };

                // ── Turnstile (iframe-based) ──────────────────────────────────
                for (const f of document.querySelectorAll('iframe')) {
                    const src = (f.src || '').toLowerCase();
                    if (src.includes('challenges.cloudflare.com') || (src.includes('turnstile') && src.includes('sitekey'))) {
                        try {
                            const u = new URL(f.src);
                            const sk = u.searchParams.get('sitekey') || u.searchParams.get('k') || '';
                            if (sk) return { type: 'turnstile', sitekey: sk, pageAction: '', isInvisible: false };
                        } catch(e) {}
                    }
                }

                // ── Turnstile (script-rendered) ───────────────────────────────
                for (const s of document.querySelectorAll('script:not([src])')) {
                    const m1 = s.textContent.match(/turnstile[^)]*sitekey['":\\s]+['"](0x[0-9A-Fa-f]{8,})['"]/);
                    if (m1) return { type: 'turnstile', sitekey: m1[1], pageAction: '', isInvisible: false };
                    const m2 = s.textContent.match(/['"]sitekey['"]\\s*[=:,]\\s*['"]( 0x[0-9A-Fa-f]{8,})['"]/);
                    if (m2) return { type: 'turnstile', sitekey: m2[1].trim(), pageAction: '', isInvisible: false };
                }

                // ── Arkose FunCaptcha ─────────────────────────────────────────
                const arkoseFrame = document.querySelector('iframe[src*="arkoselabs"], iframe[src*="funcaptcha"]');
                if (arkoseFrame) {
                    try {
                        const u = new URL(arkoseFrame.src);
                        const pk = u.searchParams.get('pk') || u.searchParams.get('muid') || '';
                        if (pk) return { type: 'funcaptcha', sitekey: pk, pageAction: '', isInvisible: false };
                    } catch(e) {}
                }

                return null;
            }""")
        except Exception as exc:
            log.warning("[CaptchaSolver] detect error: %s", exc)
            return None

    # ── Token request ─────────────────────────────────────────────────────────

    def _request_token(
        self,
        page,
        page_url: str,
        ctype: str,
        sitekey: str,
        info: dict,
    ) -> str | None:
        """Submit task to CapSolver and poll for the token.

        Key enterprise features:
        - Passes navigator.userAgent from the live browser session so the token
          fingerprint matches the browser (critical for Greenhouse Enterprise v3)
        - Maps recaptchav3enterprise → ReCaptchaV3EnterpriseTaskProxyLess
        - Includes pageAction extracted from grecaptcha.enterprise.execute()
        """
        import urllib.request as _req
        import urllib.error   as _uerr

        # Match the browser's exact UA so CapSolver token is bound to same session
        try:
            user_agent = page.evaluate("() => navigator.userAgent")
        except Exception:
            user_agent = _STEALTH_UA

        page_action  = info.get("pageAction", "") or ""
        is_invisible = info.get("isInvisible", False)

        # CapSolver task type mapping
        type_map = {
            "hcaptcha":              "HCaptchaTaskProxyless",
            "recaptchav2":           "ReCaptchaV2TaskProxyless",
            "recaptchav2enterprise": "ReCaptchaV2EnterpriseTaskProxyless",
            "recaptchav3":           "ReCaptchaV3TaskProxyless",
            "recaptchav3enterprise": "ReCaptchaV3EnterpriseTaskProxyLess",
            "turnstile":             "AntiTurnstileTaskProxyless",
            "funcaptcha":            "FunCaptchaTaskProxyless",
        }

        task: dict[str, Any] = {
            "type":       type_map.get(ctype, "HCaptchaTaskProxyless"),
            "websiteURL": page_url,
            "websiteKey": sitekey,
        }

        # Session sync: pass the live browser's UA for fingerprint matching
        if user_agent:
            task["userAgent"] = user_agent

        if is_invisible:
            task["isInvisible"] = True

        # Enterprise v3 requires pageAction to match what the site sends
        if ctype in ("recaptchav2enterprise", "recaptchav3", "recaptchav3enterprise"):
            if page_action:
                task["pageAction"] = page_action
            else:
                task["pageAction"] = "submit"   # safe default

        log.info("[CaptchaSolver] Task payload → type=%s sitekey=%s… action=%s ua=%s…",
                 task["type"], sitekey[:12], task.get("pageAction", ""), user_agent[:40])

        def _post(url: str, body: dict) -> dict:
            data = json.dumps(body).encode()
            req  = _req.Request(url, data=data, headers={"Content-Type": "application/json"})
            return json.loads(_req.urlopen(req, timeout=25).read())

        try:
            resp = _post("https://api.capsolver.com/createTask",
                         {"clientKey": self._key, "task": task})
            if resp.get("errorId", 0) != 0:
                err = resp.get("errorDescription", str(resp))
                # Auto-retry with isInvisible if CapSolver advises it
                if "invisible" in err.lower() and not task.get("isInvisible"):
                    log.info("[CaptchaSolver] Retrying with isInvisible=True per CapSolver hint")
                    task["isInvisible"] = True
                    resp = _post("https://api.capsolver.com/createTask",
                                 {"clientKey": self._key, "task": task})
                    if resp.get("errorId", 0) != 0:
                        log.warning("[CaptchaSolver] createTask error: %s",
                                    resp.get("errorDescription", resp))
                        return None
                else:
                    log.warning("[CaptchaSolver] createTask error: %s", err)
                    return None

            task_id = resp["taskId"]
            log.info("[CaptchaSolver] Task %s created — polling (max 180s)…", task_id)

            for poll_n in range(36):   # 36 × 5s = 180s max
                time.sleep(5)
                result = _post("https://api.capsolver.com/getTaskResult",
                               {"clientKey": self._key, "taskId": task_id})
                if result.get("errorId", 0) != 0:
                    log.warning("[CaptchaSolver] poll error: %s",
                                result.get("errorDescription", result))
                    return None
                status = result.get("status", "")
                if status == "ready":
                    sol = result.get("solution", {})
                    token = (sol.get("gRecaptchaResponse") or sol.get("token") or
                             sol.get("userAgent") or "")
                    if token:
                        log.info("[CaptchaSolver] ✓ Solution ready after %ds", (poll_n + 1) * 5)
                    return token or None
                log.debug("[CaptchaSolver] poll %d: status=%s", poll_n + 1, status)

            log.warning("[CaptchaSolver] Timeout waiting for task %s", task_id)
            return None

        except (_uerr.URLError, Exception) as exc:
            log.warning("[CaptchaSolver] request error: %s", exc)
            return None

    # ── Token injection ───────────────────────────────────────────────────────

    def _inject_token(self, page, ctype: str, token: str) -> None:
        """Inject the solved token and trigger all registered callbacks.

        For Enterprise reCAPTCHA this means:
        1. Setting g-recaptcha-response hidden textarea
        2. Searching ___grecaptcha_cfg.clients for onSuccess / callback functions
        3. Triggering grecaptcha.enterprise callbacks directly
        4. Firing the visible Submit button click if still needed
        """
        try:
            page.evaluate("""([token, ctype]) => {
                // ── hCaptcha ──────────────────────────────────────────────────
                if (ctype === 'hcaptcha') {
                    const ta = document.querySelector('textarea[name="h-captcha-response"]');
                    if (ta) {
                        ta.value = token;
                        ta.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    try {
                        if (window.hcaptcha && window.hcaptcha.submit) window.hcaptcha.submit();
                    } catch(e) {}
                    return;
                }

                // ── reCAPTCHA v2 / Enterprise / v3 ───────────────────────────
                if (['recaptchav2','recaptchav2enterprise','recaptchav3','recaptchav3enterprise'].includes(ctype)) {
                    // 1. Set the hidden textarea
                    const textarea = document.getElementById('g-recaptcha-response') ||
                                     document.querySelector('[name="g-recaptcha-response"]');
                    if (textarea) {
                        const orig = textarea.style.display;
                        textarea.style.display = 'block';
                        textarea.innerHTML = token;
                        textarea.value = token;
                        textarea.dispatchEvent(new Event('change', { bubbles: true }));
                        textarea.style.display = orig;
                    }

                    // 2. Fire data-callback on visible widget (v2)
                    try {
                        const widget = document.querySelector('.g-recaptcha');
                        if (widget) {
                            const cb = widget.getAttribute('data-callback');
                            if (cb && typeof window[cb] === 'function') window[cb](token);
                        }
                    } catch(e) {}

                    // 3. Search ___grecaptcha_cfg.clients for all registered callbacks
                    //    (covers Enterprise invisible v2 and v3 flows)
                    try {
                        if (typeof ___grecaptcha_cfg !== 'undefined') {
                            const clients = ___grecaptcha_cfg.clients || {};
                            Object.values(clients).forEach(client => {
                                // Walk all nested values looking for callback/onSuccess functions
                                function walkAndFire(obj, depth) {
                                    if (!obj || depth > 8 || typeof obj !== 'object') return;
                                    for (const key of Object.keys(obj)) {
                                        const val = obj[key];
                                        if (['callback','onSuccess','successCallback','verifyCallback'].includes(key)) {
                                            if (typeof val === 'function') {
                                                try { val(token); } catch(e) {}
                                            } else if (typeof val === 'string' && typeof window[val] === 'function') {
                                                try { window[val](token); } catch(e) {}
                                            }
                                        }
                                        walkAndFire(val, depth + 1);
                                    }
                                }
                                walkAndFire(client, 0);
                            });
                        }
                    } catch(e) {}

                    // 4. Try window.grecaptcha / window.grecaptcha.enterprise promises
                    try {
                        if (window.__grecaptcha_enterprise_resolve__) {
                            window.__grecaptcha_enterprise_resolve__(token);
                        }
                    } catch(e) {}

                    // 5. Delayed submit fallback — if nothing fires the form, click Submit
                    setTimeout(() => {
                        try {
                            const btn = document.querySelector(
                                'button[type="submit"]:not([disabled]), input[type="submit"]:not([disabled])'
                            );
                            if (btn) btn.click();
                        } catch(e) {}
                    }, 1500);
                    return;
                }

                // ── Cloudflare Turnstile ──────────────────────────────────────
                if (ctype === 'turnstile') {
                    const inp = document.querySelector('[name="cf-turnstile-response"]');
                    if (inp) {
                        inp.value = token;
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    try {
                        const cfDiv = document.querySelector('.cf-turnstile');
                        if (cfDiv) {
                            const cb = cfDiv.getAttribute('data-callback');
                            if (cb && typeof window[cb] === 'function') window[cb](token);
                        }
                    } catch(e) {}
                    setTimeout(() => {
                        try {
                            const btn = document.querySelector('button[type="submit"]:not([disabled])');
                            if (btn) btn.click();
                        } catch(e) {}
                    }, 1000);
                }
            }""", [token, ctype])
            log.info("[CaptchaSolver] Token injection complete for type=%s", ctype)
        except Exception as exc:
            log.warning("[CaptchaSolver] inject error: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Vision-verified form fill (integrates all three layers)
# ─────────────────────────────────────────────────────────────────────────────

def vision_verified_fill(
    page,
    flat_profile: dict,
    intelligence: IntelligenceLayer,
    browser: BrowserController,
    captcha: CaptchaSolver,
    page_url: str,
) -> tuple[int, list[str]]:
    """One form-fill pass using the vision-verified interaction loop.

    Strategy:
      1. Collect all visible inputs via accessibility tree + label walk.
      2. Use Nemotron to map labels → values (primary path).
      3. Fill each field with type_with_verification (human mouse + JS fallback).
      4. After filling, take a screenshot and run red-line scan for validation errors.
      5. Return (fields_filled, error_messages).
    """
    filled  = 0
    errors: list[str] = []

    # ── Step 1: Collect visible input metadata from the page ─────────────────
    try:
        raw_fields = page.evaluate("""() => {
            const SELS = 'input:not([type=hidden]):not([type=file]):not([type=submit]):not([type=button]),' +
                         'select, textarea';
            const results = [];
            document.querySelectorAll(SELS).forEach(el => {
                if (!el.offsetParent) return;
                const rect = el.getBoundingClientRect();
                if (rect.width < 2 || rect.height < 2) return;

                // Label resolution: aria-label > label[for] > DOM-walk > placeholder
                let label = el.getAttribute('aria-label') || '';
                if (!label && el.id) {
                    const lbl = document.querySelector('label[for="' + el.id + '"]');
                    if (lbl) {
                        const clone = lbl.cloneNode(true);
                        clone.querySelectorAll('input,select,textarea,button').forEach(n => n.remove());
                        label = (clone.innerText || clone.textContent || '').trim();
                    }
                }
                if (!label) {
                    let node = el.parentElement;
                    for (let i=0; i<8 && node; i++, node=node.parentElement) {
                        for (const child of Array.from(node.children)) {
                            if (child.contains(el)) continue;
                            const tag = child.tagName.toLowerCase();
                            if (['p','span','div','h1','h2','h3','h4','label','legend','strong','b'].includes(tag)) {
                                const t = (child.innerText || child.textContent || '').replace(/\\s+/g,' ').trim();
                                if (t.length > 5 && t.length < 200 && !t.includes('{') && !t.includes('function(')) {
                                    label = t; break;
                                }
                            }
                        }
                        if (label) break;
                    }
                }
                if (!label) label = el.placeholder || el.name || el.id || '';

                const options = [];
                if (el.tagName === 'SELECT') {
                    el.querySelectorAll('option').forEach(o => {
                        const t = (o.innerText||'').trim();
                        if (t && t.toLowerCase() !== 'select' && t !== '--') options.push(t);
                    });
                }

                results.push({
                    label:    label.slice(0, 80),
                    type:     el.type || el.tagName.toLowerCase(),
                    required: el.required || el.getAttribute('aria-required') === 'true',
                    options:  options.slice(0, 30),
                    current:  (el.value || '').trim(),
                    y:        Math.round(rect.top + window.scrollY),
                    x:        Math.round(rect.left),
                });
            });
            // Sort top-to-bottom so we fill First Name → Last Name → Email in order
            results.sort((a, b) => a.y !== b.y ? a.y - b.y : a.x - b.x);
            return results;
        }""")
    except Exception as exc:
        log.warning("[vision_verified_fill] field scan error: %s", exc)
        raw_fields = []

    visible_fields = [f for f in (raw_fields or []) if f.get("label")]
    if not visible_fields:
        log.debug("[vision_verified_fill] no labelled fields found on page")
        return 0, []

    log.info("[vision_verified_fill] Found %d labelled fields — calling Nemotron…",
             len(visible_fields))

    # ── Step 2: Nemotron maps labels → values ─────────────────────────────────
    nim_map = intelligence.map_fields(visible_fields, flat_profile)
    log.info("[vision_verified_fill] Nemotron mapped %d/%d fields",
             len(nim_map), len(visible_fields))

    # ── Step 2b: Simplified DOM fallback if 120B returned 0 fields ────────────
    # The full DOM can truncate the model's JSON response. Retry with only the
    # essential label/type/options stripped down to save tokens.
    if len(nim_map) == 0 and visible_fields:
        log.warning("[vision_verified_fill] 0 fields mapped — retrying with simplified DOM")
        simplified_fields = [
            {
                "label":    f["label"],
                "type":     f.get("type", "text"),
                "options":  f.get("options", [])[:10],  # cap options to 10
                "required": f.get("required", False),
            }
            for f in visible_fields
        ]
        nim_map = intelligence.map_fields(simplified_fields, flat_profile)
        log.info("[vision_verified_fill] Simplified DOM retry mapped %d/%d fields",
                 len(nim_map), len(simplified_fields))

    # ── Step 2c: HARD-CODED identity override — model CANNOT be trusted ────────
    # The 120B/70B models keep hallucinating "Guna" for First Name. We override
    # identity-critical fields in nim_map AFTER the model returns, using the
    # profile anchors directly. This is non-negotiable.
    _first_anchor = flat_profile.get("first_name") or flat_profile.get("legal_first_name", "")
    _last_anchor  = flat_profile.get("last_name", "")
    _email_anchor = flat_profile.get("email", "")
    _identity_overrides = {
        "first name": _first_anchor, "first_name": _first_anchor,
        "given name": _first_anchor, "fname": _first_anchor,
        "last name":  _last_anchor,  "last_name": _last_anchor,
        "family name": _last_anchor, "surname": _last_anchor,
        "email": _email_anchor, "email address": _email_anchor,
    }
    for _label_key in list(nim_map.keys()):
        _lk = _label_key.lower().strip()
        if _lk in _identity_overrides and _identity_overrides[_lk]:
            _old_val = nim_map[_label_key]
            _new_val = _identity_overrides[_lk]
            if _old_val != _new_val:
                log.warning("[identity-override] '%s': model returned %r → forced to %r",
                            _label_key, _old_val, _new_val)
                nim_map[_label_key] = _new_val

    # Also inject identity fields if the model omitted them entirely
    for _vf in visible_fields:
        _vl = _vf["label"].lower().strip()
        if _vl in _identity_overrides and _identity_overrides[_vl]:
            if _vf["label"] not in nim_map:
                nim_map[_vf["label"]] = _identity_overrides[_vl]
                log.info("[identity-override] Injected missing '%s' → %r", _vf["label"], _identity_overrides[_vl])

    # ── Step 3: Fill each field ───────────────────────────────────────────────
    # Identity anchors for the red-text guard re-type logic
    _identity_anchors = {
        # Use first_name ("Gunakarthik"), NOT legal_first_name ("Gunakarthik Naidu")
        # for "First Name" fields — legal_first_name belongs in legal/document fields only.
        "first name":      flat_profile.get("first_name", ""),
        "given name":      flat_profile.get("first_name", ""),
        "last name":       flat_profile.get("last_name", ""),
        "family name":     flat_profile.get("last_name", ""),
        "email":           flat_profile.get("email", ""),
        "email address":   flat_profile.get("email", ""),
    }

    def _has_red_text_below(pg, field_label: str) -> bool:
        """JS check: is there red-coloured text adjacent to the given labelled field?
        Checks elements within 80px below the field's bounding box for red-ish CSS color.
        Returns True if red text is detected (indicating a validation error).
        """
        try:
            return pg.evaluate("""(label) => {
                // Find the input associated with this label
                let inp = null;
                for (const lbl of Array.from(document.querySelectorAll('label'))) {
                    if ((lbl.innerText || lbl.textContent || '').toLowerCase().includes(label.toLowerCase())) {
                        const forId = lbl.getAttribute('for');
                        inp = forId ? document.getElementById(forId) : lbl.querySelector('input,select,textarea');
                        if (!inp) inp = lbl.closest('div,fieldset')?.querySelector('input,select,textarea');
                        if (inp) break;
                    }
                }
                if (!inp) return false;
                const rect = inp.getBoundingClientRect();
                if (rect.width < 1) return false;
                // Check all elements in a 200x80 window below the input
                const SEARCH_ZONE = { top: rect.bottom, bottom: rect.bottom + 80,
                                      left: rect.left - 20, right: rect.right + 20 };
                for (const el of Array.from(document.querySelectorAll('*'))) {
                    const r = el.getBoundingClientRect();
                    if (r.top < SEARCH_ZONE.top || r.bottom > SEARCH_ZONE.bottom) continue;
                    if (r.right < SEARCH_ZONE.left || r.left > SEARCH_ZONE.right) continue;
                    const txt = (el.innerText || el.textContent || '').trim();
                    if (!txt || txt.length < 2) continue;
                    const style = window.getComputedStyle(el);
                    const color = style.color;  // e.g. "rgb(255, 0, 0)"
                    const m = color.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/);
                    if (m) {
                        const [r2, g2, b2] = [+m[1], +m[2], +m[3]];
                        // Red-ish: r > 180, g < 100, b < 100
                        if (r2 > 180 && g2 < 100 && b2 < 100) return true;
                    }
                }
                return false;
            }""", field_label)
        except Exception:
            return False

    for field_info in visible_fields:
        label   = field_info["label"]
        current = field_info.get("current", "")
        ftype   = field_info.get("type", "text").lower()

        value = nim_map.get(label) or nim_map.get(label.lower())
        if not value:
            continue
        if current and current.lower() == str(value).lower():
            log.debug("[fill] '%s' already has correct value — skip", label[:40])
            continue

        # ── Red-Text Vision Guard: check for existing error before interacting ──
        if _has_red_text_below(page, label):
            log.warning("[red-guard] Red text below '%s' — clearing and re-typing anchor", label[:40])
            # Determine re-type value: use identity anchor if available, else mapped value
            label_lower = label.lower().strip()
            anchor_value = next(
                (v for k, v in _identity_anchors.items() if k in label_lower and v),
                None
            )
            _retype_value = anchor_value or str(value)
            try:
                _loc_rg = page.get_by_label(re.compile(re.escape(label), re.IGNORECASE)).first
                # Triple-click selects all text (macOS + Windows compatible).
                # Avoids Ctrl+A which on macOS moves cursor to start, not select-all.
                _loc_rg.click(click_count=3)
                page.wait_for_timeout(200)
                browser.type_with_verification(_loc_rg, _retype_value)
                log.info("[red-guard] Re-typed '%s' → '%s'", label[:40], _retype_value[:30])
            except Exception as _rg_exc:
                log.debug("[red-guard] Re-type failed for '%s': %s", label[:40], _rg_exc)

        try:
            loc = page.get_by_label(re.compile(re.escape(label), re.IGNORECASE)).first

            if ftype in ("select", "combobox"):
                try:
                    loc.select_option(label=value, timeout=1000)
                    filled += 1
                    log.info("[fill] ✓ select '%s' → '%s'", label[:40], value[:30])
                except Exception:
                    if browser.type_with_verification(loc, value):
                        filled += 1
                        log.info("[fill] ✓ custom-select '%s' → '%s'", label[:40], value[:30])
            else:
                if browser.type_with_verification(loc, str(value)):
                    filled += 1
                    log.info("[fill] ✓ '%s' → '%s'", label[:40], str(value)[:30])
                else:
                    log.warning("[fill] ✗ could not fill '%s'", label[:40])
        except Exception as exc:
            log.debug("[fill] error for '%s': %s", label[:40], exc)

    log.info("[vision_verified_fill] Filled %d field(s)", filled)

    # ── Step 4: Red-line error scan (vision) ────────────────────────────────
    try:
        ss_path = Path(f"/tmp/hireagent_redline_{int(time.time())}.png")
        page.screenshot(path=str(ss_path), full_page=False)
        with open(str(ss_path), "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        errors = intelligence.scan_for_errors(b64)
        if errors:
            log.warning("[vision_verified_fill] Red-line scan found %d error(s): %s",
                        len(errors), errors[:5])
        else:
            log.info("[vision_verified_fill] Red-line scan: no errors")
    except Exception as exc:
        log.debug("[vision_verified_fill] red-line scan error: %s", exc)

    return filled, errors


def find_submit_button_vision(
    page,
    browser: BrowserController,
    intelligence: IntelligenceLayer,
) -> bool:
    """Find and click the Submit button via selector-first, then vision fallback.

    If Submit is disabled after filling, triggers a red-line scan to report the
    specific field validation error that is preventing submission.

    Returns True if Submit was clicked.
    """
    submit_selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button:text-matches('submit application', 'i')",
        "button:text-matches('submit', 'i')",
        "button:text-matches('apply now', 'i')",
        "button:text-matches('apply', 'i')",
        "button:text-matches('send application', 'i')",
        "[data-automation-id='bottom-navigation-finish-button']",
        "[data-automation-id='wd-CommandButton_uic_submitAction']",
    ]

    disabled_sels: list[str] = []

    for sel in submit_selectors:
        try:
            loc = page.locator(sel).first
            if not loc.is_visible(timeout=1000):
                continue
            disabled = loc.get_attribute("disabled")
            aria_dis = loc.get_attribute("aria-disabled")
            if disabled is not None or aria_dis == "true":
                log.warning("[find_submit] Submit button DISABLED: %s", sel[:50])
                disabled_sels.append(sel)
                # Red-line scan to identify the blocking field
                try:
                    ss_path = Path(f"/tmp/hireagent_disabled_{int(time.time())}.png")
                    page.screenshot(path=str(ss_path), full_page=False)
                    with open(str(ss_path), "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    errs = intelligence.scan_for_errors(b64)
                    if errs:
                        log.warning("[find_submit] ↳ Blocking validation errors: %s", errs)
                    else:
                        log.warning("[find_submit] ↳ No visible errors — may be missing required field")
                except Exception:
                    pass
                continue
            # Enabled — human click it
            browser.human_click(element=loc)
            log.info("[find_submit] ✓ Submit clicked via selector: %s", sel[:50])
            return True
        except Exception:
            pass

    if disabled_sels:
        log.warning("[find_submit] Submit exists but disabled — form has validation errors")
        return False

    # ── Vision fallback: SoM screenshot → Llama-3.2 finds the button ─────────
    log.info("[find_submit] Using vision fallback to locate Submit button")
    return browser.try_click_vision_fallback(
        selector="button[type='submit'], input[type='submit']",
        description="the Submit / Apply Now button that will send the application",
        intelligence=intelligence,
        screenshot_path=Path(f"/tmp/hireagent_submit_som_{int(time.time())}.png"),
    )
