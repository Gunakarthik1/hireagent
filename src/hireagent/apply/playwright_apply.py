"""Local Playwright-based job application filler.

Replaces Claude Code CLI with direct browser automation.
Connects to an already-launched Chrome instance via CDP.
No Claude account required.

Architecture (Vision-Verified Interaction Loop):
  - BrowserController  : type_with_verification replaces page.fill()
  - IntelligenceLayer  : NVIDIA NIM Nemotron (text) + Llama-3.2-11b (vision)
  - CaptchaSolver      : CapSolver with reCAPTCHA Enterprise support
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from hireagent import config
from hireagent.apply.saas_observer import (
    log_degree_match,
    log_step,
    read_learning_buffer,
)
from hireagent.apply.vision_loop import (
    BrowserController,
    CaptchaSolver,
    IntelligenceLayer,
    find_submit_button_vision,
    vision_verified_fill,
)

logger = logging.getLogger(__name__)

# Module-level singletons — created once per process to avoid repeated init overhead
_intelligence: IntelligenceLayer | None = None
_captcha_solver: CaptchaSolver | None = None


def _get_intelligence() -> IntelligenceLayer:
    global _intelligence
    if _intelligence is None:
        _intelligence = IntelligenceLayer()
    return _intelligence


def _get_captcha() -> CaptchaSolver:
    global _captcha_solver
    if _captcha_solver is None:
        _captcha_solver = CaptchaSolver()
    return _captcha_solver

_CUSTOM_ANSWERS_PATH = Path.home() / ".hireagent" / "custom_answers.json"
_custom_answers_cache: dict | None = None


def _load_custom_answers() -> dict:
    """Load ~/.hireagent/custom_answers.json (cached). Returns empty dict on error."""
    global _custom_answers_cache
    if _custom_answers_cache is not None:
        return _custom_answers_cache
    try:
        if _CUSTOM_ANSWERS_PATH.exists():
            data = json.loads(_CUSTOM_ANSWERS_PATH.read_text(encoding="utf-8"))
            _custom_answers_cache = {
                "select": data.get("select", {}),
                "text": data.get("text", {}),
                "radio": data.get("radio", {}),
            }
        else:
            _custom_answers_cache = {"select": {}, "text": {}, "radio": {}}
    except Exception as e:
        logger.debug("custom_answers.json load error: %s", e)
        _custom_answers_cache = {"select": {}, "text": {}, "radio": {}}
    return _custom_answers_cache


def _match_custom(section: str, label: str) -> str | None:
    """Check if label matches any pattern in custom_answers[section]. Returns value or None."""
    answers = _load_custom_answers().get(section, {})
    label_lower = label.lower()
    for pattern, value in answers.items():
        if pattern.lower() in label_lower:
            return value
    return None


# ---------------------------------------------------------------------------
# Profile data extraction
# ---------------------------------------------------------------------------

def _resolve_salary(job: dict, default: str = "90000") -> str:
    """Return mid-range annual salary from job description, else default.

    Handles:
    - Annual: $80,000 - $120,000 / $80k-$120k / 80000-120000 USD
    - Hourly:  $20/hr - $40/hr  → converted to annual (x 2080 hrs/year)
    - Appends nothing (caller decides formatting); returns plain integer string.
    """
    desc = (job.get("full_description") or "") + " " + (job.get("title") or "")

    # Hourly range: $20 - $40/hr  or  20-40 per hour
    hourly_pattern = re.compile(
        r'\$\s*(\d[\d,]*\.?\d*)\s*[kK]?\s*(?:to|[-–—])\s*\$?\s*(\d[\d,]*\.?\d*)\s*[kK]?'
        r'\s*(?:per hour|\/hour|\/hr|an hour|per hr)',
        re.IGNORECASE
    )
    # Annual range: $80,000 - $120,000 or $80k-$120k or 80000-120000 USD
    annual_pattern = re.compile(
        r'\$\s*(\d[\d,]*)\s*[kK]?\s*(?:to|[-–—])\s*\$?\s*(\d[\d,]*)\s*[kK]?'
        r'(?:\s*(?:USD|per year|\/yr|\/year|annually|a year))?'
        r'|(\d[\d,]+)\s*[kK]?\s*(?:to|[-–—])\s*(\d[\d,]+)\s*[kK]?\s*(?:USD|per year|\/yr|\/year|annually)',
        re.IGNORECASE
    )

    def _parse_pair(low_str: str, high_str: str, multiplier: float = 1.0) -> str | None:
        try:
            low  = float(low_str.replace(",", ""))
            high = float(high_str.replace(",", ""))
            if low < 1000:
                low *= 1000
            if high < 1000:
                high *= 1000
            mid = int(((low + high) / 2) * multiplier)
            return str(mid)
        except ValueError:
            return None

    # Check hourly first (more specific)
    m = hourly_pattern.search(desc)
    if m:
        result = _parse_pair(m.group(1), m.group(2), multiplier=2080)
        if result:
            return result

    # Then annual
    m = annual_pattern.search(desc)
    if m:
        g = m.groups()
        low_str  = (g[0] or g[2] or "").replace(",", "")
        high_str = (g[1] or g[3] or "").replace(",", "")
        if low_str and high_str:
            result = _parse_pair(low_str, high_str)
            if result:
                return result

    return default


def _build_field_data(profile: dict, job: dict | None = None) -> dict:
    """Flatten profile dict into simple key→value lookup for form filling."""
    p   = profile.get("personal", {})
    wa  = profile.get("work_authorization", {})
    comp = profile.get("compensation", {})
    exp  = profile.get("experience", {})
    eeo  = profile.get("eeo_voluntary", {})
    edu  = profile.get("education", {})
    masters = edu.get("masters", {})

    full_name = p.get("full_name", "")

    # ── Identity Anchor: use profile.personal.first_name directly — never split full_name ──
    first_name = p.get("first_name") or (full_name.split(None, 1)[0] if full_name else "")
    last_name  = p.get("last_name") or (full_name.split(None, 1)[1] if len(full_name.split(None, 1)) > 1 else "")

    authorized = str(wa.get("legally_authorized_to_work", "yes")).lower()
    auth_yes = authorized not in ("no", "false", "0", "")
    sponsorship = str(wa.get("require_sponsorship", "no")).lower()
    needs_sponsor = sponsorship in ("yes", "true", "1")
    avail = profile.get("availability", {})
    relocate = str(avail.get("willing_to_relocate", "yes")).lower()
    willing_to_relocate = relocate not in ("no", "false", "0", "")

    # ── EEO Anchor: NEVER "Decline to Self-Identify" — always use profile value ──
    raw_gender = eeo.get("gender", "")
    gender = raw_gender if raw_gender else "Male"  # Hard rule: profile gender or Male, never Decline

    raw_race = eeo.get("race_ethnicity", "")
    race = raw_race if raw_race else "Asian"

    # ── Current company: empty → "N/A" (caller passes this only when field is required) ──
    current_company = exp.get("current_company", "") or ""

    return {
        "full_name":        full_name,
        "first_name":       first_name,
        "last_name":        last_name,
        "email":            p.get("email", ""),
        "phone":            (lambda d: d[1:] if len(d) == 11 and d.startswith("1") else d)(re.sub(r"\D", "", p.get("phone", ""))),
        "linkedin_url":     p.get("linkedin_url", ""),
        "github_url":       p.get("github_url", ""),
        "portfolio_url":    p.get("portfolio_url") or p.get("website_url", ""),
        "address":          p.get("address", ""),
        "city":             p.get("city", ""),
        "state":            p.get("province_state", ""),
        "zip_code":         p.get("postal_code", ""),
        "country":          p.get("country", "United States"),
        "salary":           _resolve_salary(job or {}, default=str(comp.get("salary_expectation", "90000"))),
        "years_experience": str(exp.get("years_of_experience_total", "0")),
        "education":        exp.get("education_level", ""),
        # Degree pulled directly from education.masters — used for tiered degree matching
        "degree":           masters.get("degree", "Master of Science"),
        "school":           masters.get("school", "Arizona State University"),
        # GPA — undergrad GPA for "GPA" text fields
        "gpa":              profile.get("education", {}).get("bachelors", {}).get("gpa", "4.0"),
        "gender":           gender,
        "race":             race,
        "veteran":          eeo.get("veteran_status", "I am not a protected veteran"),
        "disability":       eeo.get("disability_status", "No"),
        "current_company":  current_company,
        "auth_yes":         auth_yes,
        "needs_sponsor":    needs_sponsor,
        "willing_to_relocate": willing_to_relocate,
    }


# ---------------------------------------------------------------------------
# Field label → profile key mapping
# ---------------------------------------------------------------------------

TEXT_PATTERNS: list[tuple[list[str], str]] = [
    (["first name", "first_name", "firstname", "fname", "given name", "given_name"], "first_name"),
    (["last name", "last_name", "lastname", "lname", "surname", "family name", "family_name"], "last_name"),
    (["full name", "fullname", "applicant name", "legal name", "your name", "candidate name", "your full name", "systemfield name"], "full_name"),
    (["email"], "email"),
    (["phone", "mobile", "telephone", "cell"], "phone"),
    (["linkedin"], "linkedin_url"),
    (["github"], "github_url"),
    (["portfolio", "personal website", "website"], "portfolio_url"),
    (["street address", "address line 1", "address line1", "address1"], "address"),
    (["city"], "city"),
    (["state", "province"], "state"),
    (["zip", "postal"], "zip_code"),
    (["country"], "country"),
    (["salary", "compensation", "desired salary", "expected salary", "expected compensation", "salary expectation", "pay expectation", "desired pay", "hourly rate", "hourly wage", "desired hourly", "wage", "usd", "annual salary", "base salary"], "salary"),
    (["current company", "current employer", "current organization", "employer name", "company name", "where do you work", "place of employment"], "current_company"),
    (["gpa", "grade point", "cumulative gpa", "undergraduate gpa", "overall gpa"], "gpa"),
]


# ---------------------------------------------------------------------------
# Field detection helpers
# ---------------------------------------------------------------------------

def _get_label_text(page, element) -> str:
    """Get label text for an input via multiple strategies.

    Priority: aria-label > label[for=id] > DOM-walking > name attr > placeholder.
    Placeholder is last because many sites use generic text like "Type here...".
    """
    try:
        aria = element.get_attribute("aria-label") or ""
        if aria.strip():
            return aria.lower().strip()

        # label[for=id] is most reliable — check before placeholder
        elem_id = element.get_attribute("id") or ""
        if elem_id:
            label = page.query_selector(f"label[for='{elem_id}']")
            if label:
                return (label.inner_text() or "").lower().strip()

        name = element.get_attribute("name") or ""
        if name.strip():
            return name.lower().replace("_", " ").replace("-", " ").strip()

        placeholder = element.get_attribute("placeholder") or ""
        if placeholder.strip():
            return placeholder.lower().strip()

        # Try to find label text from surrounding DOM
        label_text = element.evaluate("""el => {
            // Walk up to find a label parent or sibling label
            let node = el;
            for (let i = 0; i < 5; i++) {
                node = node.parentElement;
                if (!node) break;
                if (node.tagName === 'LABEL') {
                    const clone = node.cloneNode(true);
                    clone.querySelectorAll('input,select,textarea,button').forEach(n => n.remove());
                    return (clone.innerText || clone.textContent || '').trim();
                }
                // Look for preceding sibling label
                const label = node.querySelector('label');
                if (label) {
                    return (label.innerText || label.textContent || '').trim();
                }
            }
            return '';
        }""")
        if label_text and label_text.strip():
            return label_text.lower().strip()
    except Exception:
        pass
    return ""


def _match_text_field(label_text: str) -> Optional[str]:
    """Match a label to a profile field key."""
    lt = label_text.lower().strip()
    for keywords, field_key in TEXT_PATTERNS:
        for kw in keywords:
            if kw in lt:
                return field_key
    # Exact-match fallbacks for short generic labels (e.g. Ashby uses just "Name")
    if lt == "name":
        return "full_name"
    if lt in ("email address", "e-mail"):
        return "email"
    return None


# ---------------------------------------------------------------------------
# Form filling
# ---------------------------------------------------------------------------

# Diagnostic messages from _fill_workday_fields — cleared + read by main loop
_wd_fill_diag: list[str] = []

_US_STATE_NAME_MAP = {
    "al": "Alabama", "ak": "Alaska", "az": "Arizona", "ar": "Arkansas",
    "ca": "California", "co": "Colorado", "ct": "Connecticut", "de": "Delaware",
    "dc": "District of Columbia", "fl": "Florida", "ga": "Georgia", "hi": "Hawaii",
    "id": "Idaho", "il": "Illinois", "in": "Indiana", "ia": "Iowa",
    "ks": "Kansas", "ky": "Kentucky", "la": "Louisiana", "me": "Maine",
    "md": "Maryland", "ma": "Massachusetts", "mi": "Michigan", "mn": "Minnesota",
    "ms": "Mississippi", "mo": "Missouri", "mt": "Montana", "ne": "Nebraska",
    "nv": "Nevada", "nh": "New Hampshire", "nj": "New Jersey", "nm": "New Mexico",
    "ny": "New York", "nc": "North Carolina", "nd": "North Dakota", "oh": "Ohio",
    "ok": "Oklahoma", "or": "Oregon", "pa": "Pennsylvania", "ri": "Rhode Island",
    "sc": "South Carolina", "sd": "South Dakota", "tn": "Tennessee", "tx": "Texas",
    "ut": "Utah", "vt": "Vermont", "va": "Virginia", "wa": "Washington",
    "wv": "West Virginia", "wi": "Wisconsin", "wy": "Wyoming",
}


def _workday_select_dropdown(page, btn, target_value: "str | list[str]") -> bool:
    """Click a Workday custom dropdown button and pick the best-matching option.
    target_value may be a string or list of strings tried in order."""
    targets = [target_value] if isinstance(target_value, str) else list(target_value)
    target_lowers = [t.lower().strip() for t in targets]
    try:
        # Scroll into view first so click isn't clipped
        try:
            btn.scroll_into_view_if_needed(timeout=1000)
        except Exception:
            pass
        btn.click(force=True, timeout=3000)
        page.wait_for_timeout(1200)
        # Workday renders options in a listbox / popover
        option_locs = [
            page.locator("[data-automation-id='promptOption']"),
            page.locator("[role='option']"),
            page.locator("[role='listbox'] li"),
            page.locator("[role='listbox'] [role='option']"),
            page.locator("ul[role='listbox'] li"),
            page.locator("[aria-haspopup='listbox'] ~ * [role='option']"),
        ]
        for opt_loc in option_locs:
            try:
                count = opt_loc.count()
                if count == 0:
                    continue
                # Collect all option texts for debugging
                all_texts: list[str] = []
                for i in range(min(count, 20)):
                    try:
                        t = (opt_loc.nth(i).inner_text(timeout=500) or "").strip()
                        if t:
                            all_texts.append(t)
                    except Exception:
                        pass
                if all_texts:
                    _wd_fill_diag.append(f"[dropdown-opts] {all_texts[:8]}")
                # Try each target in priority order
                for tl in target_lowers:
                    best = None
                    for i in range(count):
                        opt = opt_loc.nth(i)
                        try:
                            txt = (opt.inner_text(timeout=500) or "").lower().strip()
                            if tl in txt or txt in tl or txt == tl:
                                best = opt
                                break
                        except Exception:
                            pass
                    if best:
                        best.click(force=True, timeout=2000)
                        page.wait_for_timeout(400)
                        return True
            except Exception:
                pass
        # Nothing matched — dismiss
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
    except Exception as e:
        logger.debug("Workday dropdown click error: %s", e)
    return False


def _fill_workday_fields(page, field_data: dict) -> int:
    """Fill Workday-specific form fields using data-automation-id attributes."""
    global _wd_fill_diag
    _wd_fill_diag.clear()
    filled = 0
    # Workday uses data-automation-id on inputs
    workday_map = {
        "legalNameSection_firstName": "first_name",
        "legalNameSection_lastName": "last_name",
        "addressSection_addressLine1": "address",
        "addressSection_city": "city",
        "addressSection_postalCode": "zip_code",
        "phone-number": "phone",
        "email": "email",
        "linkedin": "linkedin_url",
        "github": "github_url",
    }
    for automation_id, field_key in workday_map.items():
        value = field_data.get(field_key, "")
        if not value:
            continue
        try:
            inp = page.query_selector(f"[data-automation-id='{automation_id}'] input, "
                                       f"input[data-automation-id='{automation_id}']")
            if inp and inp.is_visible() and not inp.is_disabled():
                _bc = BrowserController(page)
                if _bc.type_with_verification(inp, str(value)):
                    filled += 1
                else:
                    try:
                        inp.fill(str(value))
                        filled += 1
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("Workday field %s error: %s", automation_id, e)

    # ── Workday custom dropdown buttons (type=button showing "Select One") ──
    # These are NOT native <select> elements — they need click → listbox → option.
    state_code = (field_data.get("state") or "").lower()
    state_full = _US_STATE_NAME_MAP.get(state_code, field_data.get("state", ""))

    # Map label keywords → target value (may be list for priority fallbacks)
    _mobile_opts = ["Mobile", "Cell Phone", "Cell", "Cellular", "Mobile Phone"]
    dropdown_targets = {
        "state": state_full,
        "province": state_full,
        "phone device": _mobile_opts,
        "phone type": _mobile_opts,
        "device type": _mobile_opts,
        "country phone": ["+1", "United States", "USA", "1"],
        "country code": ["+1", "United States", "USA", "1"],
        "hear about": _load_custom_answers().get("select", {}).get("where did you hear", "LinkedIn"),
        "how did you hear": _load_custom_answers().get("select", {}).get("how did you hear", "LinkedIn"),
    }

    try:
        # Find all visible buttons that show a placeholder-style text
        placeholder_btns = page.query_selector_all("button[type='button'], [role='button']")
        positional_unfilled = []  # (y_pos, btn) for buttons whose label we couldn't detect
        for btn in placeholder_btns:
            try:
                if not btn.is_visible():
                    continue
                btn_text = (btn.inner_text() or "").strip().lower()
                # Match "select one", "select...", etc. — allow trailing icon chars
                if not ("select" in btn_text and len(btn_text) < 25):
                    continue
                # Find label for this button by walking up the DOM (up to 10 levels)
                label_text = page.evaluate("""(btn) => {
                    // Try aria-labelledby first
                    const lby = btn.getAttribute('aria-labelledby');
                    if (lby) {
                        const el = document.getElementById(lby);
                        if (el) return (el.textContent || '').trim().toLowerCase();
                    }
                    // Try aria-label on button itself
                    const al = btn.getAttribute('aria-label');
                    if (al) return al.toLowerCase();
                    // Walk up DOM
                    let el = btn;
                    for (let i = 0; i < 10; i++) {
                        el = el.parentElement;
                        if (!el) break;
                        const lbl = el.querySelector('label, [data-automation-id*="label"], [class*="label"], [class*="Label"]');
                        if (lbl && lbl !== btn) return (lbl.textContent || '').trim().toLowerCase();
                        const aria = el.getAttribute('aria-label');
                        if (aria) return aria.toLowerCase();
                        const alby = el.getAttribute('aria-labelledby');
                        if (alby) {
                            const ref = document.getElementById(alby);
                            if (ref) return (ref.textContent || '').trim().toLowerCase();
                        }
                    }
                    return '';
                }""", btn)
                matched = False
                if label_text:
                    for kw, target_val in dropdown_targets.items():
                        if kw in label_text and target_val:
                            if _workday_select_dropdown(page, btn, target_val):
                                filled += 1
                                _wd_fill_diag.append(f"[wd-dropdown] label='{label_text[:40]}' → '{target_val}' OK")
                            else:
                                _wd_fill_diag.append(f"[wd-dropdown] label='{label_text[:40]}' → '{target_val}' FAILED")
                            matched = True
                            break
                if not matched:
                    try:
                        bb = btn.bounding_box()
                        y_pos = int(bb["y"]) if bb else 9999
                    except Exception:
                        y_pos = 9999
                    positional_unfilled.append((y_pos, btn, label_text))
                    _wd_fill_diag.append(f"[wd-dropdown] no-label btn y={y_pos} text='{btn_text[:20]}' label='{label_text[:40]}'")
            except Exception as e:
                logger.debug("Workday dropdown btn error: %s", e)

        # Positional fallback: first unfilled "Select One" → state, second → phone type
        positional_unfilled.sort(key=lambda x: x[0])
        fallback_order = [
            ("state", state_full),
            ("phone type", _mobile_opts),
        ]
        for i, (y_pos, btn, lbl) in enumerate(positional_unfilled):
            if i < len(fallback_order):
                kw, target_val = fallback_order[i]
                if target_val:
                    if _workday_select_dropdown(page, btn, target_val):
                        filled += 1
                        _wd_fill_diag.append(f"[wd-dropdown-fallback] pos={i} '{kw}' → '{target_val}' OK")
                    else:
                        _wd_fill_diag.append(f"[wd-dropdown-fallback] pos={i} '{kw}' → '{target_val}' FAILED")
    except Exception as e:
        logger.debug("Workday dropdown scan error: %s", e)

    return filled


def _fill_text_inputs(page, field_data: dict) -> int:
    """Fill visible text/email/tel/url inputs. Returns count filled."""
    filled = 0
    # Also try Workday-specific fields
    filled += _fill_workday_fields(page, field_data)

    selectors = (
        "input[type='text'], input[type='email'], input[type='tel'], "
        "input[type='url'], input:not([type]), input[type='number']"
    )
    inputs = page.query_selector_all(selectors)

    # ── Sort inputs by y-coordinate (top-to-bottom) to fill sequentially ────
    def _y_sort_key(el):
        try:
            bb = el.bounding_box()
            return bb["y"] if bb else 99999
        except Exception:
            return 99999
    inputs = sorted(inputs, key=_y_sort_key)

    for inp in inputs:
        try:
            if not inp.is_visible() or inp.is_disabled():
                continue
            label = _get_label_text(page, inp)
            if not label:
                continue
            # Check custom_answers.json first, then profile-based matching
            custom_val = _match_custom("text", label)
            field_key = _match_text_field(label)

            # ── HARD-CODED IDENTITY ANCHORS (No LLM) ────────────────────────
            # These are FORBIDDEN from LLM mapping. Always use profile directly.
            if field_key == "first_name":
                value = field_data.get("first_name", "")
                # Double-check: never use "Guna" or any shortened form
                if value and len(value) < 6:
                    value = field_data.get("full_name", "").rsplit(None, 1)[0] if field_data.get("full_name") else value
                custom_val = None  # Override any custom_answers
            elif field_key == "last_name":
                value = field_data.get("last_name", "")
                custom_val = None
            elif field_key == "email":
                value = field_data.get("email", "")
                custom_val = None

            # ── current_company: if empty and field requires it, type "N/A" ──
            if field_key == "current_company" and not custom_val:
                raw_company = field_data.get("current_company", "")
                if not raw_company:
                    # Only fill N/A if field is marked required
                    required_attr = inp.get_attribute("required")
                    aria_req = inp.get_attribute("aria-required")
                    if required_attr is not None or aria_req == "true":
                        value = "N/A"
                    else:
                        continue  # Leave blank if not required
                else:
                    value = raw_company
            elif field_key not in ("first_name", "last_name", "email"):
                # Generic path — identity fields already handled above
                value = custom_val or (field_data.get(field_key) if field_key else None)

            if not value:
                continue
            # Check current value — skip only if it already matches what we'd fill.
            # Do NOT skip if ATS pre-filled the wrong value (bad resume parse).
            current = (inp.input_value() or "").strip()
            if current and current.lower() == str(value).lower():
                continue  # Already correct

            # ── Click-Wait-Type: scroll → click → 400ms → type → Tab ──────────
            ok = False
            try:
                inp.scroll_into_view_if_needed(timeout=2000)
                inp.click(timeout=2000)
                page.wait_for_timeout(400)
                inp.fill("")          # clear any pre-filled value
                page.keyboard.type(str(value), delay=30)
                page.wait_for_timeout(150)
                page.keyboard.press("Tab")
                ok = True
            except Exception as _cwt_e:
                logger.debug("[fill] Click-Wait-Type failed for '%s': %s", label[:30], _cwt_e)
                # Fallback: plain fill()
                try:
                    inp.fill(str(value))
                    ok = True
                except Exception:
                    pass

            # ── First Name PII guard: never allow "Guna" alone ───────────────
            if ok and field_key == "first_name":
                try:
                    _actual = (inp.input_value() or "").strip()
                    if _actual and len(_actual) < 8 and "naidu" not in _actual.lower():
                        logger.warning("[PII] First name typed as '%s' — correcting to '%s'", _actual, value)
                        inp.fill("")
                        page.keyboard.type(str(value), delay=30)
                        page.keyboard.press("Tab")
                except Exception:
                    pass
            source = "Custom" if custom_val else "Profile"
            if ok:
                filled += 1
                log_step(field=label, value_source=source, result="Success",
                         detail=f"{field_key} → '{str(value)[:40]}'")
                # ── Natural delay: let React state catch up before next field ──
                page.wait_for_timeout(400)
                # ── Visibility guard: check for red error on this field ────────
                _red_retries = 0
                while _red_retries < 3:
                    try:
                        _has_red = inp.evaluate("""el => {
                            const parent = el.closest('.field') || el.closest('.form-group') ||
                                           el.closest('[class*="field"]') || el.parentElement;
                            if (!parent) return false;
                            const errs = parent.querySelectorAll(
                                '[class*="error"], [class*="invalid"], [class*="Error"], [role="alert"]'
                            );
                            for (const e of errs) {
                                const r = e.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0 && (e.innerText || '').trim().length > 1) return true;
                            }
                            return false;
                        }""")
                        if not _has_red:
                            break
                        _red_retries += 1
                        logger.info("[fill] Red error on '%s' — retry %d/3", label[:30], _red_retries)
                        # Re-try the fill
                        inp.fill(str(value))
                        page.wait_for_timeout(500)
                    except Exception:
                        break
            else:
                try:
                    dom_snip = inp.evaluate("el => el.outerHTML")
                except Exception:
                    dom_snip = ""
                log_step(field=label, value_source=source, result="Failure",
                         detail=f"type_with_verification failed for {field_key}",
                         dom_snippet=dom_snip)
            logger.debug("[fill] %s → %s (label='%s', was='%s')", field_key, str(value)[:30], label[:40], current[:20])
        except Exception as e:
            logger.debug("Text fill error: %s", e)
    return filled


def _fill_selects(page, field_data: dict, intelligence=None) -> int:
    """Fill visible select dropdowns. Returns count filled."""
    filled = 0
    selects = page.query_selector_all("select")

    # ── Sort selects by y-coordinate (top-to-bottom) ────────────────────────
    def _y_sort_key(el):
        try:
            bb = el.bounding_box()
            return bb["y"] if bb else 99999
        except Exception:
            return 99999
    selects = sorted(selects, key=_y_sort_key)

    for sel in selects:
        try:
            if not sel.is_visible() or sel.is_disabled():
                continue
            label = _get_label_text(page, sel)
            lt = label.lower()

            # ── Degree fields: use tiered matching ───────────────────────────
            if any(kw in lt for kw in ["degree", "education level", "highest education",
                                        "highest level", "level of education"]):
                ok = _click_matching_option(page, sel, label, field_data, intelligence)
                if ok:
                    filled += 1
                    log_step(field=label, value_source="Profile", result="Success",
                             detail="Degree tiered match")
                else:
                    # Degree-error recovery: force click, type "Master", press Enter
                    try:
                        sel.click(force=True)
                        page.wait_for_timeout(300)
                        page.keyboard.type("Master")
                        page.wait_for_timeout(400)
                        # Try clicking first visible option that contains "master"
                        _clicked_opt = page.evaluate("""() => {
                            const opts = document.querySelectorAll(
                                '[role="option"], li[role="option"], .select-option, option'
                            );
                            for (const o of opts) {
                                const r = o.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0 &&
                                    (o.innerText || o.textContent || '').toLowerCase().includes('master')) {
                                    o.click(); return (o.innerText || o.textContent || '').trim().slice(0,40);
                                }
                            }
                            return null;
                        }""")
                        if _clicked_opt:
                            filled += 1
                            log_step(field=label, value_source="Profile", result="Success",
                                     detail=f"Degree recovery click: {_clicked_opt}")
                        else:
                            page.keyboard.press("Enter")
                            page.wait_for_timeout(200)
                            # Blur to commit
                            page.evaluate("document.activeElement && document.activeElement.blur()")
                            filled += 1
                            log_step(field=label, value_source="Profile", result="Success",
                                     detail="Degree recovery: typed Master + Enter")
                    except Exception as _deg_rec_e:
                        dom_snip = ""
                        try:
                            dom_snip = sel.evaluate("el => el.outerHTML")
                        except Exception:
                            pass
                        log_step(field=label, value_source="Profile", result="Failure",
                                 detail=f"All degree tiers + recovery failed: {_deg_rec_e}",
                                 dom_snippet=dom_snip)
                continue

            target_value = _match_custom("select", label)
            if target_value is None and any(kw in lt for kw in ["authorized to work", "legally authorized", "work auth", "work authorization"]):
                target_value = "Yes" if field_data["auth_yes"] else "No"
            elif any(kw in lt for kw in ["sponsorship", "visa sponsor", "require sponsor", "need sponsor"]):
                target_value = "Yes" if field_data["needs_sponsor"] else "No"
            elif "country" in lt:
                target_value = "United States"
            elif ("state" in lt or "province" in lt) and field_data.get("state"):
                target_value = field_data["state"]
            elif "gender" in lt:
                # ABSOLUTE OVERRIDE: ALWAYS "Male" — FORBIDDEN from selecting "Decline"
                # Try "Male" first, then "Man" as fuzzy fallback
                _gender_set = False
                for _g_candidate in ["Male", "Man", "M"]:
                    if _try_select_value(sel, _g_candidate):
                        # PII guard: verify the selected value is not a decline variant
                        _chosen = sel.evaluate(
                            "el => { const o = el.options[el.selectedIndex]; return o ? o.text.trim() : ''; }"
                        )
                        if any(x in (_chosen or "").lower() for x in ("decline", "prefer not", "wish to answer")):
                            logger.error("[PII VIOLATION] Gender landed on '%s' — forcing Male", _chosen)
                            # Try again from top of candidate list
                            for _retry in ["Male", "Man"]:
                                if _try_select_value(sel, _retry):
                                    break
                        filled += 1
                        log_step(field=label, value_source="Profile", result="Success",
                                 detail=f"gender → '{_g_candidate}'")
                        _gender_set = True
                        break
                if _gender_set:
                    continue
                target_value = "Male"  # Fallback for generic path
            elif "race" in lt or "ethnicity" in lt:
                # ABSOLUTE OVERRIDE: ALWAYS "Asian"
                _race_set = False
                for _r_candidate in ["Asian", "Asian (Not Hispanic or Latino)",
                                      "Asian or Pacific Islander", "South Asian"]:
                    if _try_select_value(sel, _r_candidate):
                        filled += 1
                        log_step(field=label, value_source="Profile", result="Success",
                                 detail=f"race → '{_r_candidate}'")
                        _race_set = True
                        break
                if _race_set:
                    continue
                target_value = "Asian"  # Fallback
            elif "veteran" in lt:
                target_value = field_data.get("veteran", "I am not a protected veteran")
            elif "disability" in lt:
                # ABSOLUTE OVERRIDE: ALWAYS "No" — FORBIDDEN from selecting any decline/opt-out
                for candidate in ["No, I do not have a disability",
                                   "No, I Don't Have a Disability",
                                   "I don't have a disability", "I do not have a disability",
                                   "No, I don't have a disability", "No disability",
                                   "No, I don't have a disability (or history of)",
                                   "No"]:
                    if _try_select_value(sel, candidate):
                        filled += 1
                        log_step(field=label, value_source="Profile", result="Success",
                                 detail=f"disability → '{candidate}'")
                        break
                continue
            elif any(kw in lt for kw in ["relocat", "willing to travel", "willing to commute",
                                          "in-person", "in person", "on-site", "onsite", "transport"]):
                # Always Yes for any relocation/travel/in-person question
                for candidate in ["Yes", "Willing to relocate", "Open to relocation", "Yes, I am willing"]:
                    if _try_select_value(sel, candidate):
                        filled += 1
                        log_step(field=label, value_source="Profile", result="Success",
                                 detail=f"relocate → '{candidate}'")
                        break
                continue
            elif any(kw in lt for kw in ["citizenship", "visa status", "work status", "work permit",
                                          "immigration status", "right to work"]):
                # Prefer OPT/F-1 options; fall back to Other
                for candidate in ["F1 OPT", "OPT", "F-1 OPT", "F1", "Optional Practical Training",
                                   "Student Visa", "Visa", "Other"]:
                    if _try_select_value(sel, candidate):
                        filled += 1
                        log_step(field=label, value_source="Profile", result="Success",
                                 detail=f"visa → '{candidate}'")
                        # If "Other" selected, try to type F1 OPT in a companion text box
                        if candidate == "Other":
                            try:
                                page.wait_for_timeout(400)
                                for _inp in page.query_selector_all("input[type='text']:visible"):
                                    _inp_lbl = _get_label_text(page, _inp)
                                    if any(k in _inp_lbl.lower() for k in ["visa", "status", "citizenship", "specify"]):
                                        _inp.fill("F1 OPT")
                                        break
                            except Exception:
                                pass
                        break
                continue
            elif any(kw in lt for kw in ["how did you hear", "how did you find", "how did you learn",
                                          "where did you hear", "referral source", "hear about us"]):
                # Always prefer LinkedIn, then Company Website
                for candidate in ["LinkedIn", "Company Website", "Job Board", "Indeed", "Other"]:
                    if _try_select_value(sel, candidate):
                        filled += 1
                        log_step(field=label, value_source="Profile", result="Success",
                                 detail=f"hear-about → '{candidate}'")
                        logger.debug("[select] hear-about → '%s'", candidate)
                        break
                continue  # handled above, skip generic target_value path

            if target_value:
                ok = _try_select_value(sel, target_value)
                if ok:
                    filled += 1
                    log_step(field=label, value_source="Profile", result="Success",
                             detail=f"select → '{target_value}'")
                    logger.debug("[select] label='%s' → '%s'", label[:40], target_value)
                else:
                    try:
                        dom_snip = sel.evaluate("el => el.outerHTML")
                    except Exception:
                        dom_snip = ""
                    log_step(field=label, value_source="Profile", result="Failure",
                             detail=f"No match for '{target_value}'", dom_snippet=dom_snip)
            # ── Natural delay + visibility guard after each select fill ────────
            if filled > 0:
                page.wait_for_timeout(400)
                # Check for red error on this select's container
                _red_retries_sel = 0
                while _red_retries_sel < 3:
                    try:
                        _has_red_sel = sel.evaluate("""el => {
                            const parent = el.closest('.field') || el.closest('.form-group') ||
                                           el.closest('[class*="field"]') || el.parentElement;
                            if (!parent) return false;
                            const errs = parent.querySelectorAll(
                                '[class*="error"], [class*="invalid"], [class*="Error"], [role="alert"]'
                            );
                            for (const e of errs) {
                                const r = e.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0 && (e.innerText || '').trim().length > 1) return true;
                            }
                            return false;
                        }""")
                        if not _has_red_sel:
                            break
                        _red_retries_sel += 1
                        logger.info("[select] Red error on '%s' — retry %d/3", label[:30], _red_retries_sel)
                        # Force-type fallback for selects with errors
                        sel.click(force=True)
                        page.wait_for_timeout(300)
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(500)
                    except Exception:
                        break
        except Exception as e:
            logger.debug("Select fill error: %s", e)
    return filled


def _try_select_value(select_el, target_value: str) -> bool:
    """Select the option best matching target_value (fuzzy). Returns True if found."""
    target = target_value.lower().strip()
    options = select_el.query_selector_all("option")
    best_opt_value = None
    for opt in options:
        opt_text = (opt.inner_text() or "").lower().strip()
        opt_val = (opt.get_attribute("value") or "").lower().strip()
        # Skip placeholder options
        if opt_val in ("", "placeholder", "select", "select one", "--select--"):
            continue
        if opt_text in ("select...", "select one", "-- select --", "", "--"):
            continue
        if target in opt_text or opt_text in target:
            best_opt_value = opt.get_attribute("value")
            break
        if target in opt_val or opt_val in target:
            best_opt_value = opt.get_attribute("value")
    if best_opt_value is not None:
        try:
            select_el.select_option(value=best_opt_value)
            return True
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Recursive Force-Select: re-check dropdowns that remain at placeholder
# ---------------------------------------------------------------------------

def _recursive_force_select(page, field_data: dict, intelligence=None) -> int:
    """Second-pass: find ANY dropdown (native <select> or React combobox) still at placeholder.

    Greenhouse uses React Select (<div class="select"> with <input role="combobox">),
    NOT native <select> elements.  We must handle both.

    For Degree: open → type "Master" → click matching option or press Enter.
    For Citizenship/Visa: try F1 OPT options, fall back to "Other" + text input.
    For EEO (Gender/Race/Disability): use hard-coded profile values.
    Returns count of fields fixed.
    """
    fixed = 0

    # ── Part A: Greenhouse React comboboxes (.select__placeholder visible) ────
    # Find ALL React-Select containers that still show a placeholder or "Select..."
    try:
        stuck_react = page.evaluate("""() => {
            const results = [];
            // Greenhouse pattern: <label id="degree--0-label">, <input id="degree--0" role="combobox">
            const combos = document.querySelectorAll('input[role="combobox"]');
            for (const inp of combos) {
                const r = inp.getBoundingClientRect();
                if (r.width < 1) continue;
                // Check if the container has a placeholder visible
                const container = inp.closest('.select') || inp.closest('[class*="select__container"]');
                if (!container) continue;
                const placeholder = container.querySelector('[class*="placeholder"]');
                const singleVal  = container.querySelector('[class*="single-value"]');
                const hasRealVal = singleVal && singleVal.innerText && singleVal.innerText.trim() &&
                                   !singleVal.innerText.toLowerCase().includes('select');
                if (hasRealVal) continue;  // Already filled
                // Get label from the associated <label> element
                const labelId = inp.id ? inp.id + '-label' : '';
                const lbl = labelId ? document.getElementById(labelId) : null;
                const labelText = lbl ? lbl.innerText.trim() :
                    (container.querySelector('label') || {}).innerText || inp.placeholder || inp.id || '';
                results.push({
                    id: inp.id || '',
                    label: labelText.replace(/\\*/g, '').trim(),
                    placeholder: placeholder ? placeholder.innerText.trim() : '',
                });
            }
            return results;
        }""") or []
    except Exception:
        stuck_react = []

    for combo in stuck_react:
        combo_id = combo.get("id", "")
        combo_label = combo.get("label", "")
        lt = combo_label.lower()
        logger.info("[force-select] React combobox stuck: id=%s label='%s'", combo_id, combo_label[:40])

        try:
            inp = page.locator(f"#{combo_id}").first if combo_id else None
            if not inp or not inp.is_visible(timeout=500):
                continue

            # ── Degree Logic (React Select) ───────────────────────────────────
            if any(kw in lt for kw in ["degree", "education level", "highest education",
                                        "highest level", "level of education"]):
                # Try "Master of Science" first, then fall back through alias list
                _clicked = None
                for _deg_query in ["Master of Science", "Master's Degree", "Masters", "M.S.", "Graduate Degree", "Master"]:
                    inp.click(timeout=1500)
                    page.wait_for_timeout(400)
                    # Clear any previous text
                    inp.fill("")
                    page.keyboard.type(_deg_query)
                    page.wait_for_timeout(500)
                    # Click the first visible option containing the query
                    _clicked = page.evaluate("""(query) => {
                        const q = query.toLowerCase();
                        const opts = document.querySelectorAll(
                            '[role="option"], [class*="select__option"], [id*="option"]'
                        );
                        for (const o of opts) {
                            const r = o.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0 &&
                                (o.innerText || '').toLowerCase().includes(q)) {
                                o.click(); return (o.innerText || '').trim().slice(0,50);
                            }
                        }
                        return null;
                    }""", _deg_query)
                    if _clicked:
                        break
                    # Escape to close dropdown before trying next query
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(200)
                if _clicked:
                    fixed += 1
                    logger.info("[force-select] Degree (React) → '%s'", _clicked)
                else:
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(300)
                    fixed += 1
                    logger.info("[force-select] Degree (React) → typed 'Master' + Enter")
                continue

            # ── Citizenship / Visa (React Select) ────────────────────────────
            if any(kw in lt for kw in ["citizenship", "visa", "immigration", "right to work"]):
                for candidate in ["F1 OPT", "OPT", "Other"]:
                    inp.click(timeout=1500)
                    page.wait_for_timeout(300)
                    inp.fill("")
                    page.keyboard.type(candidate)
                    page.wait_for_timeout(500)
                    _clicked = page.evaluate("""(target) => {
                        const opts = document.querySelectorAll('[role="option"], [class*="select__option"]');
                        for (const o of opts) {
                            const r = o.getBoundingClientRect();
                            const t = (o.innerText || '').toLowerCase().trim();
                            if (r.width > 0 && r.height > 0 && t.includes(target.toLowerCase())) {
                                o.click(); return t.slice(0,50);
                            }
                        }
                        return null;
                    }""", candidate)
                    if _clicked:
                        fixed += 1
                        logger.info("[force-select] Citizenship (React) → '%s'", _clicked)
                        if "other" in _clicked.lower():
                            page.wait_for_timeout(400)
                            try:
                                for _txt in page.query_selector_all("input[type='text']:visible"):
                                    _tl = _get_label_text(page, _txt).lower()
                                    if any(k in _tl for k in ["visa", "status", "specify", "other"]):
                                        _txt.fill("F1 OPT")
                                        break
                            except Exception:
                                pass
                        break
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(200)
                continue

            # ── ABSOLUTE EEO OVERRIDES (React combobox) ───────────────────────
            # Gender: FORBIDDEN from "Decline" — try "Male" then "Man"
            if "gender" in lt:
                for _g_query in ["Male", "Man"]:
                    inp.click(timeout=1500)
                    page.wait_for_timeout(300)
                    inp.fill("")
                    page.keyboard.type(_g_query)
                    page.wait_for_timeout(500)
                    _clicked = page.evaluate("""(q) => {
                        const opts = document.querySelectorAll('[role="option"], [class*="select__option"]');
                        for (const o of opts) {
                            const r = o.getBoundingClientRect();
                            const t = (o.innerText || '').toLowerCase().trim();
                            if (r.width > 0 && r.height > 0 && t.includes(q.toLowerCase()) &&
                                !t.includes('decline') && !t.includes('prefer not')) {
                                o.click(); return (o.innerText || '').trim().slice(0,50);
                            }
                        }
                        return null;
                    }""", _g_query)
                    if _clicked:
                        fixed += 1
                        logger.info("[force-select] Gender (React) → '%s'", _clicked)
                        break
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(200)
                continue

            # Disability: FORBIDDEN from "Decline"/"I don't wish to answer"
            if "disability" in lt:
                for _d_query in ["No, I do not", "No", "I do not have", "I don't have"]:
                    inp.click(timeout=1500)
                    page.wait_for_timeout(300)
                    inp.fill("")
                    page.keyboard.type(_d_query)
                    page.wait_for_timeout(500)
                    _clicked = page.evaluate("""(q) => {
                        const opts = document.querySelectorAll('[role="option"], [class*="select__option"]');
                        for (const o of opts) {
                            const r = o.getBoundingClientRect();
                            const t = (o.innerText || '').toLowerCase().trim();
                            if (r.width > 0 && r.height > 0 && t.includes(q.toLowerCase()) &&
                                !t.includes('decline') && !t.includes('wish to answer') &&
                                !t.includes('prefer not')) {
                                o.click(); return (o.innerText || '').trim().slice(0,50);
                            }
                        }
                        return null;
                    }""", _d_query)
                    if _clicked:
                        fixed += 1
                        logger.info("[force-select] Disability (React) → '%s'", _clicked)
                        break
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(200)
                continue

            # ── Generic React combobox: type the profile value ────────────────
            # For any other stuck React Select, try typing common profile values
            _generic_map = {
                "country": "United States",
                "location": field_data.get("city", "") + ", " + field_data.get("state", ""),
                "school": field_data.get("school", "Arizona State University"),
                "discipline": "Computer Science",
                "race": field_data.get("race", "Asian"),
            }
            for _key, _val in _generic_map.items():
                if _key in lt and _val:
                    inp.click(timeout=1500)
                    page.wait_for_timeout(300)
                    page.keyboard.type(_val[:30])
                    page.wait_for_timeout(500)
                    _opt_clicked = page.evaluate("""() => {
                        const opts = document.querySelectorAll('[role="option"], [class*="select__option"]');
                        for (const o of opts) {
                            const r = o.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) {
                                o.click(); return (o.innerText || '').trim().slice(0,50);
                            }
                        }
                        return null;
                    }""")
                    if _opt_clicked:
                        fixed += 1
                        logger.info("[force-select] React '%s' → '%s'", combo_label[:30], _opt_clicked)
                    else:
                        page.keyboard.press("Escape")
                    break

        except Exception as e:
            logger.debug("[force-select] React combobox error for '%s': %s", combo_label[:30], e)

    # ── Part B: Native <select> elements ─────────────────────────────────────
    selects = page.query_selector_all("select")
    for sel in selects:
        try:
            if not sel.is_visible():
                continue
            current_text = sel.evaluate("""el => {
                const opt = el.options[el.selectedIndex];
                return opt ? opt.text.trim() : '';
            }""")
            current_lower = (current_text or "").lower()
            placeholders = ("select...", "choose...", "select one", "please select",
                            "select an option", "--", "- select -", "")
            if current_lower not in placeholders and not current_lower.startswith("select"):
                continue

            label = _get_label_text(page, sel)
            lt = label.lower()
            logger.info("[force-select] Native <select> stuck: '%s' (showing: '%s')", label[:40], current_text[:30])

            if any(kw in lt for kw in ["degree", "education level", "highest education"]):
                for candidate in ["Master of Science", "Master's Degree", "Masters", "M.S.", "Graduate Degree", "Master", "Graduate"]:
                    if _try_select_value(sel, candidate):
                        fixed += 1
                        logger.info("[force-select] Degree (native) → '%s'", candidate)
                        break
            elif any(kw in lt for kw in ["citizenship", "visa", "immigration"]):
                for candidate in ["F1 OPT", "OPT", "Other"]:
                    if _try_select_value(sel, candidate):
                        fixed += 1
                        logger.info("[force-select] Citizenship (native) → '%s'", candidate)
                        if candidate == "Other":
                            page.wait_for_timeout(400)
                            try:
                                for _inp in page.query_selector_all("input[type='text']:visible"):
                                    _inp_lbl = _get_label_text(page, _inp)
                                    if any(k in _inp_lbl.lower() for k in ["visa", "status", "specify", "other"]):
                                        _inp.fill("F1 OPT")
                                        break
                            except Exception:
                                pass
                        break
            elif "gender" in lt:
                if _try_select_value(sel, field_data.get("gender", "Male")):
                    fixed += 1
                    logger.info("[force-select] Gender (native) → '%s'", field_data.get("gender", "Male"))
            elif "race" in lt or "ethnicity" in lt:
                if _try_select_value(sel, field_data.get("race", "Asian")):
                    fixed += 1
                    logger.info("[force-select] Race (native) → '%s'", field_data.get("race", "Asian"))
            elif "disability" in lt:
                for candidate in ["No, I do not have a disability", "No, I Don't Have a Disability",
                                   "I don't have a disability", "I do not have a disability",
                                   "No, I don't have a disability", "No disability", "No"]:
                    if _try_select_value(sel, candidate):
                        fixed += 1
                        logger.info("[force-select] Disability (native) → '%s'", candidate)
                        break
        except Exception as e:
            logger.debug("[force-select] Native select error: %s", e)

    return fixed


# ---------------------------------------------------------------------------
# Tiered degree matching
# ---------------------------------------------------------------------------

_DEGREE_TIER1 = ["Master of Science"]
_DEGREE_TIER2 = [
    "Masters", "Master's", "Master's Degree", "Master Degree",
    "M.S.", "MS", "Graduate Degree", "Graduate",
]
_DEGREE_BROAD_SIGNALS = ["master", "graduate", "ms", "m.s"]


def _click_matching_option(
    page,
    select_el,
    label: str,
    field_data: dict,
    intelligence=None,
) -> bool:
    """Select best option for a dropdown field using 4-tier degree logic (or fuzzy for others).

    For Degree fields:
      Tier 1 — Exact: "Master of Science"
      Tier 2 — Aliases: Masters, M.S., Graduate Degree, etc.
      Tier 3 — LLM deep reasoning (120B model picks from available options)
      Tier 4 — SaaS Safety: select 'Other', type degree in companion text box

    For non-Degree fields: falls through to _try_select_value.
    Returns True if an option was successfully selected.
    """
    lt = label.lower()
    is_degree_field = any(kw in lt for kw in ["degree", "education level", "highest education",
                                               "highest level", "level of education"])

    # Collect all real options from the <select>
    options = select_el.query_selector_all("option")
    opt_texts: list[str] = []
    opt_vals: list[str] = []
    for opt in options:
        txt = (opt.inner_text() or "").strip()
        val = (opt.get_attribute("value") or "").strip()
        if val.lower() in ("", "placeholder", "select", "select one", "--select--"):
            continue
        if txt.lower() in ("select...", "select one", "-- select --", "", "--"):
            continue
        opt_texts.append(txt)
        opt_vals.append(val)

    if not is_degree_field:
        # Standard fuzzy matching for non-degree fields
        target = field_data.get("education", "")
        if not target:
            return False
        return _try_select_value(select_el, target)

    degree_target = field_data.get("degree", "Master of Science")

    def _select_by_text(text: str) -> bool:
        """Try to select an option whose text matches `text` (case-insensitive)."""
        tl = text.lower()
        for i, txt in enumerate(opt_texts):
            if tl == txt.lower():
                try:
                    select_el.select_option(value=opt_vals[i])
                    return True
                except Exception:
                    pass
        return False

    def _select_contains(needle: str) -> tuple[bool, str]:
        """Select first option whose text contains needle (case-insensitive). Returns (ok, matched_text)."""
        nl = needle.lower()
        for i, txt in enumerate(opt_texts):
            if nl in txt.lower():
                try:
                    select_el.select_option(value=opt_vals[i])
                    return True, txt
                except Exception:
                    pass
        return False, ""

    # ── Tier 1: Exact ────────────────────────────────────────────────────────
    for t1 in _DEGREE_TIER1:
        if _select_by_text(t1):
            log_step(field=label, value_source="Profile", result="Success",
                     detail=f"Tier1 exact: {t1}")
            return True

    # ── Tier 2: Common aliases ────────────────────────────────────────────────
    for alias in _DEGREE_TIER2:
        ok, matched = _select_contains(alias)
        if ok:
            log_degree_match(field=label, target=degree_target,
                             selected=matched, tier=2, confidence=0.90)
            log_step(field=label, value_source="Profile", result="Success",
                     detail=f"Tier2 alias: {alias} → {matched}")
            logger.info("[degree] Tier2 match: '%s' → '%s'", alias, matched)
            return True

    # Broader signal check (catches "Graduate-level", "Post-graduate")
    for sig in _DEGREE_BROAD_SIGNALS:
        ok, matched = _select_contains(sig)
        if ok:
            log_degree_match(field=label, target=degree_target,
                             selected=matched, tier=2, confidence=0.80)
            log_step(field=label, value_source="Profile", result="Success",
                     detail=f"Tier2 broad: {sig} → {matched}")
            logger.info("[degree] Tier2 broad match: '%s' → '%s'", sig, matched)
            return True

    # ── Tier 3: LLM deep reasoning ────────────────────────────────────────────
    if intelligence and opt_texts:
        try:
            opts_str = ", ".join(f'"{o}"' for o in opt_texts[:20])
            prompt = (
                f"The candidate has a '{degree_target}'. "
                f"These are the available degree options: [{opts_str}]. "
                "Which is the most appropriate selection? Return ONLY the exact text of the option."
            )
            raw = intelligence._call_text_model(
                system_prompt="You select the best form dropdown option for a job applicant. Return only the option text.",
                user_msg=prompt,
                max_tokens=64,
            )
            if raw:
                chosen = raw.strip().strip('"').strip("'")
                ok, matched = _select_contains(chosen)
                if not ok:
                    # Try exact
                    ok = _select_by_text(chosen)
                    matched = chosen if ok else ""
                if ok:
                    log_degree_match(field=label, target=degree_target,
                                     selected=matched, tier=3, confidence=0.75)
                    log_step(field=label, value_source="LLM", result="Success",
                             detail=f"Tier3 LLM → '{matched}'")
                    logger.info("[degree] Tier3 LLM match → '%s'", matched)
                    return True
        except Exception as exc:
            logger.debug("[degree] Tier3 LLM error: %s", exc)

    # ── Tier 4: SaaS Safety — select 'Other', fill companion text box ─────────
    ok, matched = _select_contains("other")
    if ok:
        log_degree_match(field=label, target=degree_target,
                         selected="Other", tier=4, confidence=0.50)
        log_step(field=label, value_source="Profile", result="Success",
                 detail="Tier4: selected 'Other'")
        logger.info("[degree] Tier4: selected 'Other' — looking for companion text box")
        # Wait briefly for companion text box to appear
        try:
            page.wait_for_timeout(600)
            # Find nearby text input (same parent container, within 3 DOM levels up)
            companion = select_el.evaluate("""el => {
                let node = el;
                for (let i = 0; i < 4; i++) {
                    node = node.parentElement;
                    if (!node) break;
                    const inp = node.querySelector(
                        'input[type="text"], input:not([type]), textarea'
                    );
                    if (inp && inp !== el) return inp.id || inp.name || '__found__';
                }
                return null;
            }""")
            if companion:
                # Click and fill the companion input
                for inp in page.query_selector_all("input[type='text'], input:not([type]), textarea"):
                    try:
                        if not inp.is_visible():
                            continue
                        inp.click()
                        inp.fill(degree_target)
                        logger.info("[degree] Tier4: typed '%s' into companion text box", degree_target)
                        break
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug("[degree] Tier4 companion text box error: %s", exc)
        return True

    # All tiers exhausted
    log_step(field=label, value_source="Profile", result="Failure",
             detail=f"No match found for degree in options: {opt_texts[:10]}")
    return False


# ---------------------------------------------------------------------------
# Greenhouse pre-submit safety check
# ---------------------------------------------------------------------------

_REQUIRED_FIELD_KEYS = {
    "name":          ["name", "first name", "last name", "full name"],
    "email":         ["email"],
    "degree":        ["degree", "education"],
    "authorization": ["authorized", "work auth", "legally authorized", "sponsorship"],
    "eeo":           ["gender", "race", "ethnicity", "veteran", "disability", "eeo"],
}


def _final_form_audit(page, field_data: dict, intelligence: "IntelligenceLayer | None" = None) -> bool:
    """Vision-Verified Submission audit using Llama 3.2 Vision.

    Takes a screenshot, asks the vision model if there are:
      - Any red validation error text visible
      - Any dropdown still showing 'Select...' or 'Choose...'

    If problems are found:
      - Re-runs _recursive_force_select on remaining placeholders
      - Returns False (MUST NOT submit)

    If clean:
      - Returns True (safe to submit)
    """
    import base64
    from pathlib import Path

    if intelligence is None:
        intelligence = _get_intelligence()

    try:
        # Take screenshot for vision audit
        _audit_ss = Path(f"/tmp/hireagent_audit_{int(__import__('time').time())}.png")
        page.screenshot(path=str(_audit_ss), full_page=False)
        with open(str(_audit_ss), "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        errors = intelligence.scan_for_errors(b64)
        if not errors:
            logger.info("[final_audit] Vision audit PASSED — no errors detected")
            return True

        logger.warning("[final_audit] Vision audit FAILED: %s", errors[:5])

        # Attempt correction: force-select any remaining placeholder dropdowns
        _fixed = _recursive_force_select(page, field_data, intelligence)
        if _fixed:
            logger.info("[final_audit] Fixed %d dropdown(s) in correction pass", _fixed)

        # Re-check with DOM scan (faster than another vision call)
        remaining = page.evaluate("""() => {
            const issues = [];
            // Check for red error text
            for (const el of document.querySelectorAll('[class*="error"], [class*="invalid"], .error-message')) {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    const txt = (el.innerText || '').trim();
                    if (txt && txt.length > 2) issues.push('ERROR:' + txt.slice(0,80));
                }
            }
            // Check for placeholder selects
            for (const sel of document.querySelectorAll('select')) {
                const r = sel.getBoundingClientRect();
                if (r.width < 1) continue;
                const opt = sel.options[sel.selectedIndex];
                const t = opt ? opt.text.toLowerCase().trim() : '';
                if (t.startsWith('select') || t.startsWith('choose') || t === '--' || t === '') {
                    issues.push('PLACEHOLDER:' + (sel.name || sel.id || 'dropdown'));
                }
            }
            return issues;
        }""") or []

        if remaining:
            logger.warning("[final_audit] Still %d issue(s) after correction: %s", len(remaining), remaining[:5])
            return False

        logger.info("[final_audit] Audit PASSED after correction")
        return True

    except Exception as e:
        logger.warning("[final_audit] Audit error (non-blocking): %s", e)
        return True  # Don't block submit on audit infrastructure failure


def pre_submit_check(page, field_data: dict) -> tuple[bool, list[str]]:
    """Greenhouse submit safety gate.

    Checks:
      1. No visible 'required' indicators still unfilled.
      2. Five key fields (Name, Email, Degree, Authorization, EEO) have values.

    Returns (ok: bool, issues: list[str]).
    Submit is ONLY allowed when ok is True.
    """
    issues: list[str] = []

    # ── Check 1: visible "required" text in divs/spans ───────────────────────
    try:
        required_nodes = page.evaluate("""() => {
            const hits = [];
            const nodes = document.querySelectorAll('div, span, label, p');
            for (const n of nodes) {
                const style = window.getComputedStyle(n);
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                const txt = (n.innerText || n.textContent || '').toLowerCase().trim();
                if (txt === 'required' || txt.includes('this field is required') ||
                    txt.includes('field is required') || txt.includes('* required')) {
                    hits.push(txt.slice(0, 80));
                }
            }
            return hits.slice(0, 10);
        }""")
        if required_nodes:
            issues.append(f"Visible 'required' markers found: {required_nodes}")
    except Exception as exc:
        logger.debug("[pre_submit_check] required-node scan error: %s", exc)

    # ── Check 2: five key fields have non-empty values ────────────────────────
    def _field_has_value(keys: list[str]) -> bool:
        for k in keys:
            v = field_data.get(k)
            if v and str(v).strip():
                return True
        return False

    if not _field_has_value(["first_name", "last_name", "full_name"]):
        issues.append("Name fields are empty")
    if not _field_has_value(["email"]):
        issues.append("Email is empty")
    if not _field_has_value(["degree", "education"]):
        issues.append("Degree/Education is empty")
    if not _field_has_value(["auth_yes"]):
        # auth_yes is bool — check explicitly
        if not field_data.get("auth_yes"):
            issues.append("Work authorization not set")
    # EEO: at least one eeo field must be non-decline
    eeo_ok = (
        field_data.get("gender") not in ("", "Decline to self-identify", None)
        or field_data.get("race") not in ("", "Decline to self-identify", None)
        or field_data.get("veteran") not in ("", None)
    )
    if not eeo_ok:
        issues.append("EEO fields are all blank/decline")

    ok = len(issues) == 0
    if not ok:
        logger.warning("[pre_submit_check] BLOCKED: %s", issues)
    else:
        logger.info("[pre_submit_check] PASSED — all 5 key checks OK")
    return ok, issues


def _fill_radio_checkboxes(page, field_data: dict) -> int:
    """Handle radio button groups for yes/no questions. Returns groups handled."""
    handled = 0
    # Group radios by name attribute
    radio_groups: dict[str, list] = {}
    for radio in page.query_selector_all("input[type='radio']"):
        name = radio.get_attribute("name") or ""
        if name:
            radio_groups.setdefault(name, []).append(radio)

    for name, group in radio_groups.items():
        try:
            lt = name.lower().replace("_", " ").replace("-", " ")

            desired_yes: Optional[bool] = None
            custom_radio = _match_custom("radio", lt)
            if custom_radio is not None:
                desired_yes = custom_radio.lower() not in ("no", "false", "0", "n")
            elif any(kw in lt for kw in ["authorized", "legal", "work auth"]):
                desired_yes = field_data["auth_yes"]
            elif any(kw in lt for kw in ["sponsor", "visa"]):
                # "Do you need sponsorship?" → answer No if you don't need it
                desired_yes = field_data["needs_sponsor"]
            elif any(kw in lt for kw in ["relocat", "willing to move", "open to relocation"]):
                desired_yes = field_data["willing_to_relocate"]
            elif any(kw in lt for kw in ["18", "age", "adult", "old enough"]):
                desired_yes = True
            elif any(kw in lt for kw in ["background check", "drug test", "drug screen"]):
                desired_yes = True
            elif any(kw in lt for kw in ["felony", "criminal"]):
                desired_yes = False
            elif any(kw in lt for kw in ["previously worked", "worked here before"]):
                desired_yes = False

            if desired_yes is None:
                continue

            target = "yes" if desired_yes else "no"
            for radio in group:
                val = (radio.get_attribute("value") or "").lower()
                aria = (radio.get_attribute("aria-label") or "").lower()
                rid = radio.get_attribute("id") or ""
                label_text = ""
                if rid:
                    lbl = page.query_selector(f"label[for='{rid}']")
                    if lbl:
                        label_text = (lbl.inner_text() or "").lower()
                combined = f"{val} {aria} {label_text}"
                if target in combined or combined.strip() == target:
                    if radio.is_visible() and not radio.is_disabled():
                        radio.click()
                        handled += 1
                        break
        except Exception as e:
            logger.debug("Radio fill error for '%s': %s", name, e)
    return handled


def _upload_resume(page, resume_pdf: str) -> bool:
    """Upload resume PDF to any file input found on the page.

    Handles standard <input type='file'>, drag-drop areas, and Indeed Easy Apply's
    'Add a resume' / 'Upload resume' / 'Change resume' button patterns.
    """
    pdf_path = Path(resume_pdf)
    if not pdf_path.exists():
        logger.warning("Resume PDF not found at: %s", pdf_path)
        return False

    # Try direct hidden/visible file inputs first
    for inp in page.query_selector_all("input[type='file']"):
        try:
            accept = (inp.get_attribute("accept") or "").lower()
            # Only skip if accept explicitly excludes PDFs
            if accept and "pdf" not in accept and "*" not in accept and "application" not in accept:
                continue
            inp.set_input_files(str(pdf_path))
            logger.info("Uploaded resume via file input: %s", pdf_path.name)
            return True
        except Exception as e:
            logger.debug("File input upload error: %s", e)

    # Try clicking upload/resume buttons that trigger a file chooser
    upload_kws = [
        "upload resume", "upload cv", "upload a resume", "add resume", "add a resume",
        "attach resume", "change resume", "replace resume", "upload your resume",
        "choose file", "select file", "add file", "attach file",
        "upload", "attach", "resume", "cv",
    ]
    for btn in page.query_selector_all("button, [role='button'], label, a"):
        try:
            if not btn.is_visible():
                continue
            text = (btn.inner_text() or btn.get_attribute("aria-label") or "").lower().strip()
            if not any(kw in text for kw in upload_kws):
                continue
            with page.expect_file_chooser(timeout=5000) as fc_info:
                btn.click()
            fc_info.value.set_files(str(pdf_path))
            logger.info("Uploaded resume via file chooser ('%s'): %s", text[:40], pdf_path.name)
            return True
        except Exception:
            pass

    # Last resort: try JS to find any hidden file input and set its files
    # (some drag-drop zones have a visually hidden <input type='file'>)
    try:
        result = page.evaluate(f"""(pdfPath) => {{
            const inputs = Array.from(document.querySelectorAll("input[type='file']"));
            for (const inp of inputs) {{
                const accept = (inp.getAttribute('accept') || '').toLowerCase();
                if (accept && !accept.includes('pdf') && !accept.includes('*') && !accept.includes('application')) continue;
                // Temporarily make visible for set_input_files
                inp.style.display = 'block';
                inp.style.opacity = '1';
                inp.style.position = 'fixed';
                inp.style.top = '0';
                inp.style.left = '0';
                inp.style.zIndex = '99999';
                return inp.id || inp.name || 'found';
            }}
            return 'not_found';
        }}""", str(pdf_path))
        if result != "not_found":
            # Now the input is visible — try again
            for inp in page.query_selector_all("input[type='file']"):
                try:
                    inp.set_input_files(str(pdf_path))
                    logger.info("Uploaded resume via JS-unhidden file input: %s", pdf_path.name)
                    return True
                except Exception:
                    pass
    except Exception as e:
        logger.debug("JS file input reveal error: %s", e)

    logger.debug("No file upload input found on this page")
    return False


def _detect_captcha(page) -> bool:
    """Detect a visible CAPTCHA challenge on the current page.

    Ignores reCAPTCHA v3 (invisible/background) — only flags challenges that
    actually block the user, like v2 checkbox, hCaptcha, or Cloudflare Turnstile.
    """
    try:
        # Visible reCAPTCHA v2: challenge iframe or .g-recaptcha div
        if page.query_selector("iframe[src*='recaptcha/api2/bframe']"):
            return True
        if page.query_selector(".g-recaptcha[data-sitekey]"):
            return True
        # hCaptcha
        if page.query_selector("iframe[src*='hcaptcha.com']"):
            return True
        # Cloudflare Turnstile
        if page.query_selector(".cf-turnstile, iframe[src*='challenges.cloudflare.com']"):
            return True
        return False
    except Exception:
        return False


def _try_solve_captcha(page, page_url: str, log_fn=None, max_attempts: int = 2) -> bool:
    """Attempt to solve a detected CAPTCHA using CapSolver API.

    Imports _solve_captcha from free_agent. Retries up to max_attempts times.
    Returns True if solved, False if all attempts failed.
    """
    _log = log_fn or (lambda msg: logger.info(msg))
    try:
        from hireagent.apply.free_agent import _solve_captcha
    except ImportError:
        _log("Cannot import _solve_captcha from free_agent")
        return False

    for attempt in range(1, max_attempts + 1):
        _log(f"CAPTCHA solve attempt {attempt}/{max_attempts} via CapSolver...")
        try:
            solved = _solve_captcha(page, page_url)
            if solved:
                _log(f"CAPTCHA solved on attempt {attempt}")
                page.wait_for_timeout(2000)  # Let page process the token
                return True
        except Exception as e:
            _log(f"CAPTCHA solve attempt {attempt} error: {e}")
        if attempt < max_attempts:
            page.wait_for_timeout(3000)  # Wait before retry
    _log(f"CAPTCHA unsolvable after {max_attempts} attempts")
    return False


def _wait_for_page_ready(page, timeout_ms: int = 8000) -> None:
    """Wait for a SPA to finish rendering after navigation."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass
    page.wait_for_timeout(1500)


def _handle_workday_login(page, log_fn) -> bool:
    """Detect and handle Workday sign-in / create-account wall.

    Returns True if we successfully got past the login screen.
    Credentials come from ~/.hireagent/.env: WORKDAY_EMAIL / WORKDAY_PASSWORD.
    """
    import os
    email = os.environ.get("WORKDAY_EMAIL", "")
    password = os.environ.get("WORKDAY_PASSWORD", "")
    if not email or not password:
        return False

    try:
        url = page.url.lower()
        # Workday sign-in pages contain these markers
        is_workday_auth = (
            "myworkdayjobs.com" in url or "wd1.myworkdayjobs" in url or
            "wd3.myworkdayjobs" in url or "wd5.myworkdayjobs" in url
        )
        if not is_workday_auth:
            return False
        # Require a stronger signal: URL path indicates auth/apply flow,
        # OR there's an actual email input (or sign-in page title)
        url_is_auth = any(s in url for s in [
            "/login", "/signin", "/sign-in", "/createaccount", "/create-account",
            "/apply/", "/apply", "apply?", "workdayaccounts"
        ])
        # Also check page title for "Sign In"
        title_is_auth = False
        try:
            title_is_auth = "sign in" in page.title().lower()
        except Exception:
            pass
        # Use Locator to pierce Shadow DOM when checking for email input
        has_email_input = False
        try:
            email_loc = page.locator(
                "[data-automation-id='email'], input[type='email'], "
                "input[name='email'], [data-automation-id='username'], "
                "input[autocomplete='email'], input[autocomplete='username']"
            )
            has_email_input = email_loc.first.is_visible()
        except Exception:
            pass
        if not (url_is_auth or title_is_auth or has_email_input):
            return False
    except Exception:
        return False

    log_fn("Workday sign-in page detected — attempting login")

    # ── Dismiss cookie banner first (blocks form interaction) ────────────────
    try:
        cookie_loc = page.locator(
            "button:has-text('Accept Cookies'), button:has-text('Accept All'), "
            "button:has-text('Accept all'), button:has-text('I Accept'), "
            "button:has-text('Accept'), button[id*='accept'], button[id*='cookie']"
        )
        if cookie_loc.first.is_visible():
            cookie_loc.first.click()
            page.wait_for_timeout(1500)
            log_fn("Dismissed cookie consent banner")
    except Exception:
        pass

    # ── Click "Apply Manually" if present (Workday intermediate screen) ───────
    try:
        manual_loc = page.locator(
            "button:has-text('Apply Manually'), a:has-text('Apply Manually'), "
            "[data-automation-id='applyManuallyButton']"
        )
        if manual_loc.first.is_visible():
            manual_loc.first.click()
            page.wait_for_timeout(3500)  # Wait for sign-in options to render
            log_fn("Clicked 'Apply Manually'")
    except Exception:
        pass

    def _loc_visible(locator) -> bool:
        """Check if a Playwright Locator has ≥1 visible element."""
        try:
            return locator.first.is_visible()
        except Exception:
            return False

    def _loc_fill(locator, value):
        """Fill a Playwright Locator, falling back to click+type."""
        try:
            locator.first.fill(str(value))
        except Exception:
            try:
                locator.first.click(click_count=3)
                locator.first.type(str(value), delay=40)
            except Exception:
                pass

    # ── Step 1: Click Workday "Sign In" section header (avoid Apple/Google SSO)
    # Use data-automation-id first (Workday-specific), then fall back to
    # text matching but skip SSO provider buttons (Apple, Google, Microsoft).
    signin_clicked = False
    for sel in [
        "[data-automation-id='signInLink']",
        "[data-automation-id='existing-account-link']",
        "[data-automation-id='signInWithWorkdayButton']",
        "[data-automation-id='signInWithEmail']",
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(1500)
                log_fn(f"Clicked sign-in link ({sel})")
                signin_clicked = True
                break
        except Exception:
            pass

    if not signin_clicked:
        # Text-based: find "Sign In" buttons/links that are NOT SSO providers
        # Priority order: email-specific first, then generic Sign In (below nav)
        sign_in_texts_priority = [
            "sign in with email", "sign in with username", "continue with email",
            "use email", "sign in with workday", "sign in"
        ]
        # Retry up to 5 times (some SPAs render the email sign-in option async)
        for _si_attempt in range(5):
            try:
                btns = page.query_selector_all("button, a, [role='button']")
                best_btn = None
                best_priority = 999
                for btn in btns:
                    try:
                        if not btn.is_visible():
                            continue
                        txt = (btn.inner_text() or "").strip().lower()
                        aria = (btn.get_attribute("aria-label") or "").lower()
                        combined = txt + " " + aria
                        # Skip SSO provider buttons
                        if any(sso in combined for sso in ["apple", "google", "microsoft", "linkedin", "facebook", "seek"]):
                            continue
                        for i, sig_txt in enumerate(sign_in_texts_priority):
                            if sig_txt in combined or combined == sig_txt:
                                box = btn.bounding_box()
                                # Skip nav bar (top ~100px) for generic "sign in"
                                if sig_txt == "sign in" and box and box.get("y", 0) <= 100:
                                    continue
                                if i < best_priority:
                                    best_priority = i
                                    best_btn = btn
                                break
                    except Exception:
                        pass
                if best_btn:
                    box = best_btn.bounding_box() or {}
                    txt = (best_btn.inner_text() or "").strip().lower()
                    best_btn.click()
                    page.wait_for_timeout(1500)
                    log_fn(f"Clicked sign-in button: '{txt}' (y={box.get('y',0):.0f})")
                    signin_clicked = True
                    break
                # If not found yet, wait and retry
                page.wait_for_timeout(1000)
            except Exception:
                page.wait_for_timeout(1000)

    # ── Step 2: Find email field — use JS shadow DOM traversal as fallback ──
    # First try standard Playwright Locator (pierces shadow DOM in many configs)
    email_loc = page.locator(
        "[data-automation-id='email'], input[type='email'], "
        "input[name='email'], [data-automation-id='username'], "
        "input[autocomplete='email'], input[autocomplete='username']"
    )
    email_filled = False
    for attempt in range(8):
        try:
            if _loc_visible(email_loc):
                _loc_fill(email_loc, email)
                email_filled = True
                log_fn(f"Filled Workday email via Locator (attempt {attempt})")
                break
        except Exception as e:
            log_fn(f"Workday email fill error (attempt {attempt}): {e}")

        # Fallback: JS to find input in shadow DOM and fill it
        if not email_filled:
            try:
                filled = page.evaluate(f"""(emailValue) => {{
                    function findAndFill(root) {{
                        const inputs = root.querySelectorAll(
                            "input[type='email'], input[autocomplete='email'], " +
                            "input[autocomplete='username'], input[name='email'], " +
                            "input[name='username'], [data-automation-id='email']"
                        );
                        for (const inp of inputs) {{
                            if (inp.offsetParent !== null || inp.getBoundingClientRect().height > 0) {{
                                inp.focus();
                                inp.value = emailValue;
                                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                                return true;
                            }}
                        }}
                        const allEls = root.querySelectorAll('*');
                        for (const el of allEls) {{
                            if (el.shadowRoot) {{
                                if (findAndFill(el.shadowRoot)) return true;
                            }}
                        }}
                        return false;
                    }}
                    return findAndFill(document);
                }}""", email)
                if filled:
                    email_filled = True
                    log_fn(f"Filled Workday email via JS shadow DOM traversal (attempt {attempt})")
                    break
            except Exception as e:
                log_fn(f"Workday JS email fill error (attempt {attempt}): {e}")

        page.wait_for_timeout(1000)

    if not email_filled:
        log_fn(f"Workday: email field not found via Locator/JS. URL={page.url[:80]}")
        return False

    # ── Step 3: Click Continue / Next ─────────────────────────────────────────
    page.wait_for_timeout(500)
    continue_loc = page.locator(
        "[data-automation-id='continue-button'], [data-automation-id='next-button'], "
        "button:has-text('Continue'), input[value='Continue'], "
        "button:has-text('Next'), input[value='Next']"
    )
    try:
        if _loc_visible(continue_loc):
            continue_loc.first.click()
            log_fn("Clicked Continue/Next")
            page.wait_for_timeout(2500)
    except Exception as e:
        log_fn(f"Continue button click error: {e}")

    # After Continue, Workday may show "Sign In" link for existing accounts
    for text in ["Sign In", "Already have an account"]:
        try:
            signin_lnk = page.locator(
                f"[data-automation-id='signInLink'], "
                f"[data-automation-id='existing-account-link'], "
                f"a:has-text('{text}')"
            )
            if _loc_visible(signin_lnk):
                signin_lnk.first.click()
                page.wait_for_timeout(2000)
                log_fn(f"Clicked '{text}' link after Continue")
                break
        except Exception:
            pass

    # ── Step 4: Wait for password field (up to 8s) ───────────────────────────
    pw_loc = page.locator(
        "[data-automation-id='password'], input[type='password'], "
        "input[name='password'], input[autocomplete='current-password']"
    )
    pw_found = False
    for _ in range(8):
        try:
            if _loc_visible(pw_loc):
                pw_found = True
                break
        except Exception:
            pass
        # Also check via JS shadow DOM
        try:
            found_js = page.evaluate("""() => {
                function findPw(root) {
                    const inputs = root.querySelectorAll(
                        "input[type='password'], [data-automation-id='password']"
                    );
                    for (const inp of inputs) {
                        if (inp.offsetParent !== null || inp.getBoundingClientRect().height > 0)
                            return true;
                    }
                    for (const el of root.querySelectorAll('*')) {
                        if (el.shadowRoot && findPw(el.shadowRoot)) return true;
                    }
                    return false;
                }
                return findPw(document);
            }""")
            if found_js:
                pw_found = True
                break
        except Exception:
            pass
        page.wait_for_timeout(1000)

    if pw_found:
        # ── Step 5: Fill password via Locator or JS ──────────────────────────
        pw_filled = False
        try:
            if _loc_visible(pw_loc):
                _loc_fill(pw_loc, password)
                pw_filled = True
                log_fn("Filled Workday password via Locator")
        except Exception as e:
            log_fn(f"Workday password Locator fill error: {e}")

        if not pw_filled:
            try:
                ok = page.evaluate(f"""(pw) => {{
                    function fillPw(root) {{
                        const inputs = root.querySelectorAll(
                            "input[type='password'], [data-automation-id='password']"
                        );
                        for (const inp of inputs) {{
                            if (inp.offsetParent !== null || inp.getBoundingClientRect().height > 0) {{
                                inp.focus();
                                inp.value = pw;
                                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                                return true;
                            }}
                        }}
                        for (const el of root.querySelectorAll('*')) {{
                            if (el.shadowRoot && fillPw(el.shadowRoot)) return true;
                        }}
                        return false;
                    }}
                    return fillPw(document);
                }}""", password)
                if ok:
                    log_fn("Filled Workday password via JS")
            except Exception as e:
                log_fn(f"Workday password JS fill error: {e}")

        # Click Sign In — try locator first, then JS to bypass consent overlay
        sign_loc = page.locator(
            "[data-automation-id='sign-in-button']:not([aria-hidden='true']), "
            "[data-automation-id='signInButton']:not([aria-hidden='true']), "
            "button:has-text('Sign In'):not([aria-hidden='true']), "
            "input[value='Sign In']"
        )
        _signin_done = False
        try:
            if _loc_visible(sign_loc):
                sign_loc.first.click(timeout=5000)
                page.wait_for_timeout(4000)
                log_fn("Workday sign-in submitted — waiting for redirect")
                _signin_done = True
        except Exception as e:
            log_fn(f"Workday sign-in button error: {e}")

        if not _signin_done:
            # JS click bypasses consent modal overlay that intercepts pointer events
            try:
                js_result = page.evaluate("""() => {
                    const btn = document.querySelector(
                        "[data-automation-id='signInSubmitButton'], " +
                        "[data-automation-id='sign-in-button'], " +
                        "button[type='submit']:not([data-automation-id='utilityButtonSignIn'])"
                    );
                    if (btn) { btn.click(); return 'clicked:' + (btn.textContent||'').trim().slice(0,30); }
                    const modal = document.querySelector('[data-behavior-click-outside-close]');
                    if (modal) {
                        const btns = modal.querySelectorAll('button, [role=button]');
                        for (const b of btns) {
                            const t = (b.textContent||'').toLowerCase().trim();
                            if (t.includes('sign') || t.includes('agree') || t.includes('accept')) {
                                b.click(); return 'modal:' + t.slice(0,30);
                            }
                        }
                    }
                    return 'not_found';
                }""")
                page.wait_for_timeout(4000)
                log_fn(f"Workday sign-in JS click: {js_result}")
                _signin_done = True
            except Exception as e:
                log_fn(f"Workday sign-in JS error: {e}")

        if _signin_done:
            return True

        log_fn("Workday: could not find Sign In button after password")
        return False

    # ── Fallback: create account flow ─────────────────────────────────────────
    log_fn("Workday: password not found — trying Create Account flow")
    try:
        ca_loc = page.locator(
            "[data-automation-id='createAccountLink'], "
            "a:has-text('Create Account'), button:has-text('Create Account')"
        )
        if _loc_visible(ca_loc):
            ca_loc.first.click()
            page.wait_for_timeout(2000)
            log_fn("Clicked Create Account")

            # Fill email
            email_loc2 = page.locator(
                "[data-automation-id='email'], input[type='email']"
            )
            if _loc_visible(email_loc2):
                _loc_fill(email_loc2, email)

            # Fill password fields (password + confirm password)
            pw_fields_loc = page.locator(
                "[data-automation-id='password'], input[type='password']"
            )
            try:
                count = pw_fields_loc.count()
                for i in range(count):
                    pw_el = pw_fields_loc.nth(i)
                    if pw_el.is_visible():
                        pw_el.fill(password)
            except Exception:
                pass

            # Submit
            submit_loc2 = page.locator(
                "[data-automation-id='createAccountButton'], "
                "button:has-text('Create Account'), button[type='submit']"
            )
            if _loc_visible(submit_loc2):
                submit_loc2.first.click()
                page.wait_for_timeout(3000)
                log_fn("Workday create account submitted")
                return True
    except Exception as e:
        log_fn(f"Workday create account error: {e}")

    return False


def _click_apply_cta(page) -> bool:
    """Click the primary 'Apply' CTA button on job description pages.

    Tries ATS-specific selectors first, then falls back to text matching.
    Returns True if a button was found and clicked.
    """
    # ATS-specific apply button selectors (checked first)
    ats_selectors = [
        # Indeed Easy Apply
        "[data-testid='IndeedApplyButton']",
        "button[data-indeed-apply-joburl]",
        ".ia-IndeedApplyButton",
        ".indeed-apply-button",
        # Indeed external apply (company site)
        "[data-testid='job-apply-button']",
        "[data-indeed-apply]",
        # Workday
        "[data-automation-id='applyButton']",
        "[data-automation-id='apply-button']",
        "[data-automation-id='Apply']",
        # Greenhouse
        "#apply_button",
        ".application--cta a",
        # Lever
        ".postings-btn-wrapper a",
        ".template-btn-submit",
        # Ashby
        "[data-testid='apply-button']",
        # SmartRecruiters — "I'm interested" is the primary CTA; js-apply-btn is fallback
        "button.js-apply-btn",
        ".js-apply-btn",
        "button[data-sh-id*='apply' i]",
        # Rippling
        "[data-testid='apply-now-button']",
        # iCIMS
        ".iCIMS_Anchor[title*='Apply']",
    ]
    for sel in ats_selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                logger.info("Clicked ATS-specific Apply CTA: %s", sel)
                return True
        except Exception:
            pass

    # Fallback: text-based matching
    # "I'm interested" (SmartRecruiters) is highest priority — placed before generic "apply"
    # to ensure we fill with profile.json rather than a LinkedIn 1-click scrape.
    apply_kws = [
        "i'm interested", "im interested",  # SmartRecruiters primary CTA
        "apply now", "apply for this job", "apply to this job", "apply for job",
        "start application", "begin application", "easy apply", "quick apply",
        "easily apply", "apply on company site", "apply on employer site",
        "apply on indeed", "apply with indeed", "apply",
    ]
    candidates = page.query_selector_all(
        "button, a, [role='button'], input[type='button'], input[type='submit']"
    )
    best = None
    best_score = -1
    for el in candidates:
        try:
            if not el.is_visible():
                continue
            text = (el.inner_text() or el.get_attribute("value") or "").lower().strip()
            for i, kw in enumerate(apply_kws):
                if text == kw or text.startswith(kw):
                    score = len(apply_kws) - i
                    if score > best_score:
                        best_score = score
                        best = el
                    break
        except Exception:
            pass
    if best is not None:
        try:
            best.click()
            logger.info("Clicked Apply CTA (text match)")
            return True
        except Exception as e:
            logger.debug("CTA click error: %s", e)
    return False


def _has_form_elements(page) -> bool:
    """Check if the page has an active application form (not just nav/search inputs).

    Returns True only if there are meaningful application form fields — not just
    a single search box or header input that exists on every job description page.
    """
    try:
        # Exclude search/button/hidden inputs; type='search' is always a search box
        inputs = page.query_selector_all(
            "input[type='text'], input[type='email'], input[type='tel'], "
            "input[type='url'], input[type='number'], input[type='password'], "
            "input:not([type]), select, textarea"
        )
        visible = []
        for el in inputs:
            try:
                if not el.is_visible():
                    continue
                # Skip inputs inside nav / header / search containers
                in_chrome = el.evaluate("""el => {
                    let node = el;
                    for (let i = 0; i < 8; i++) {
                        node = node.parentElement;
                        if (!node) break;
                        const tag = (node.tagName || '').toLowerCase();
                        const role = (node.getAttribute('role') || '').toLowerCase();
                        const cls = (node.className || '').toLowerCase();
                        if (['header', 'nav'].includes(tag) ||
                            role === 'navigation' || role === 'search' ||
                            cls.includes('header') || cls.includes('navbar') ||
                            cls.includes('search-bar') || cls.includes('searchbar')) {
                            return true;
                        }
                    }
                    return false;
                }""")
                if not in_chrome:
                    visible.append(el)
            except Exception:
                visible.append(el)
        # Require at least 2 meaningful inputs to distinguish an application form
        # from a single search box on a job description page.
        return len(visible) >= 2
    except Exception:
        return False


def _detect_success(page) -> bool:
    """Detect successful application submission."""
    try:
        url = page.url.lower()
        content = page.content().lower()
    except Exception:
        return False

    url_signals = ["thank", "confirm", "success", "submitted", "complete", "received", "done"]
    content_signals = [
        "thank you for applying",
        "application submitted",
        "application received",
        "application complete",
        "successfully submitted",
        "you have applied",
        "your application has been",
        "we've received your application",
        "we have received your application",
        "application confirmation",
        "your application was submitted",
    ]

    for s in url_signals:
        if s in url:
            return True
    for s in content_signals:
        if s in content:
            return True
    return False


def _find_submit_or_next(page) -> tuple[str, object]:
    """Find the best button to click. Returns ('submit'|'next'|'none', element).

    Checks ATS-specific selectors first, then falls back to text matching.
    """
    # ATS-specific submit selectors
    ats_submit_selectors = [
        "[data-automation-id='bottom-navigation-next-button']",  # Workday Next
        "[data-automation-id='wd-CommandButton_uic_submitAction']",  # Workday Submit
    ]
    ats_next_selectors = [
        "[data-automation-id='bottom-navigation-next-button']",  # Workday
        "[data-automation-id='nextButton']",
        ".ia-continueButton",  # iCIMS
        ".js-continue",  # SmartRecruiters
    ]

    # Check Workday submit/review button specifically
    # Use Locator (not query_selector) so it pierces shadow DOM
    for sel in [
        "[data-automation-id='bottom-navigation-next-button']",
        "[data-automation-id='bottom-navigation-finish-button']",
        "[data-automation-id='bottom-navigation-review-button']",
        "[data-automation-id='wd-CommandButton_uic_submitAction']",
    ]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=500):
                btn_text = (loc.inner_text(timeout=1000) or "").lower()
                if any(kw in btn_text for kw in ["submit", "review", "finish", "complete"]):
                    return "submit", loc
                else:
                    return "next", loc
        except Exception:
            pass

    submit_kws = ["submit application", "submit", "apply now", "apply", "send application",
                  "complete application", "finish", "done", "review"]
    next_kws = ["next", "continue", "proceed", "save and continue", "save & continue",
                "save and next", "next step"]
    # Nav/auth buttons that should never be form submit actions
    exclude_as_submit = ["sign in", "signin", "log in", "login", "register", "create account",
                         "sign up", "forget password", "forgot password"]

    all_buttons = page.query_selector_all(
        "button[type='submit'], input[type='submit'], button, [role='button'], a[role='button']"
    )

    submit_candidates = []
    next_candidates = []

    for btn in all_buttons:
        try:
            if not btn.is_visible():
                continue
            disabled = btn.get_attribute("disabled")
            aria_disabled = btn.get_attribute("aria-disabled")
            if disabled is not None or aria_disabled == "true":
                continue
            text = (btn.inner_text() or btn.get_attribute("value") or "").lower().strip()
            btn_type = (btn.get_attribute("type") or "").lower()
            # Text always takes priority over button type:
            # "Next"/"Continue" buttons are "next" even if type='submit'
            is_next_text = any(kw in text for kw in next_kws)
            is_submit_text = any(kw in text for kw in submit_kws) and not is_next_text
            is_excluded = any(ex == text or text.startswith(ex) for ex in exclude_as_submit)
            # Positional check: buttons in top nav (y <= 120px) are navigation, not form buttons.
            # A "sign in" button below 120px is likely a form-level auth step button.
            if is_excluded:
                try:
                    box = btn.bounding_box()
                    if box and box.get("y", 0) > 120:
                        is_excluded = False  # form-level button, not nav
                except Exception:
                    pass
            if is_next_text:
                next_candidates.append((text, btn))
            elif is_excluded:
                pass  # Skip nav/auth buttons in top bar
            elif is_submit_text:
                submit_candidates.append((text, btn))
            elif btn_type == "submit":
                submit_candidates.insert(0, (text, btn))
        except Exception:
            pass

    if submit_candidates:
        logger.debug("Submit button found: %s", submit_candidates[0][0])
        return "submit", submit_candidates[0][1]
    if next_candidates:
        logger.debug("Next button found: %s", next_candidates[0][0])
        return "next", next_candidates[0][1]
    # Log all visible buttons for diagnosis
    try:
        all_vis = page.query_selector_all("button, [role='button'], input[type='submit']")
        vis_info = []
        for b in all_vis[:20]:
            try:
                if b.is_visible():
                    t = (b.inner_text() or b.get_attribute("value") or "").strip()[:30]
                    bt = b.get_attribute("type") or ""
                    box = b.bounding_box() or {}
                    vis_info.append(f"'{t}' type={bt} y={int(box.get('y', -1))}")
            except Exception:
                pass
        if vis_info:
            logger.debug("No btn found. Visible buttons: %s", " | ".join(vis_info))
    except Exception:
        pass
    return "none", None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_playwright_apply(
    job: dict,
    port: int,
    worker_id: int = 0,
    dry_run: bool = False,
) -> tuple[str, str]:
    """Apply to a job using Playwright via CDP to an existing Chrome instance.

    Returns:
        (status, log_text)
        status: 'applied' | 'captcha' | 'expired' | 'failed:reason'
    """
    from playwright.sync_api import sync_playwright
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    apply_url = job.get("application_url") or job["url"]
    resume_path = job.get("tailored_resume_path")
    log_lines: list[str] = []

    def log(msg: str) -> None:
        logger.info("[W%d] %s", worker_id, msg)
        log_lines.append(msg)

    # Load user profile
    try:
        profile = config.load_profile()
    except Exception as e:
        return f"failed:profile_load_error", f"Could not load profile: {e}"

    field_data = _build_field_data(profile)

    with sync_playwright() as playwright:
        # Connect to the already-running Chrome via CDP (retry up to 15s)
        import time as _time
        browser = None
        last_err = None
        for _ in range(15):
            try:
                browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                log(f"Connected to Chrome on port {port}")
                break
            except Exception as e:
                last_err = e
                _time.sleep(1)
        if browser is None:
            return "failed:chrome_cdp_error", f"CDP connect failed: {last_err}"

        page = None
        try:
            contexts = browser.contexts
            if contexts:
                ctx = contexts[0]
                pages = ctx.pages
                page = pages[0] if pages else ctx.new_page()
            else:
                ctx = browser.new_context()
                page = ctx.new_page()

            page.set_default_timeout(20000)

            # For Workday job pages, navigate directly to the /apply sub-URL
            # to bypass the "click Apply" step and land on the sign-in/form page.
            nav_url = apply_url
            if "myworkdayjobs.com" in apply_url.lower():
                if not any(s in apply_url.lower() for s in ["/apply", "/login", "/signin"]):
                    nav_url = apply_url.rstrip("/") + "/apply"
                    log(f"Workday job detected — navigating directly to apply URL: {nav_url[:100]}")

            log(f"Navigating to: {nav_url}")
            try:
                page.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
            except PlaywrightTimeout:
                log("Page load timeout")
                return "expired", "\n".join(log_lines)

            # Wait for SPA rendering
            _wait_for_page_ready(page)

            # ── Initialise vision-loop singletons for this application ──────────
            _nim   = _get_intelligence()
            _capt  = _get_captcha()
            _bc    = BrowserController(page)

            if _detect_captcha(page):
                log("CAPTCHA detected on initial page load — attempting solve via CaptchaSolver...")
                if not _capt.solve(page, apply_url):
                    log("CAPTCHA unsolvable on initial page load")
                    return "captcha", "\n".join(log_lines)
                log("CAPTCHA solved — continuing")

            # Log page title and check for expired/404 pages
            try:
                title = page.title()
                log(f"Page title: {title[:80]}")
                url_now = page.url
                if url_now != apply_url:
                    log(f"Redirected to: {url_now[:100]}")
                # Detect expired/removed job postings
                title_lower = title.lower()
                expired_signals = [
                    "404", "not found", "page not found", "job not found",
                    "position not found", "no longer available", "job closed",
                    "posting expired", "listing not found", "error"
                ]
                if any(s in title_lower for s in expired_signals):
                    log(f"Job appears expired or removed (title: {title[:60]})")
                    return "expired", "\n".join(log_lines)
            except Exception:
                pass

            # Detect if we got redirected away from the specific job (e.g. Workday → homepage)
            try:
                current_url = page.url
                # If we ended up on a different domain or the URL changed significantly
                from urllib.parse import urlparse
                orig_parsed = urlparse(apply_url)
                curr_parsed = urlparse(current_url)
                if (orig_parsed.netloc == curr_parsed.netloc and
                        orig_parsed.path != curr_parsed.path and
                        len(curr_parsed.path) < len(orig_parsed.path) // 2):
                    log(f"Redirected to different path — job likely expired (was: {orig_parsed.path[:60]}, now: {curr_parsed.path[:60]})")
                    return "expired", "\n".join(log_lines)
            except Exception:
                pass

            # Handle Workday login wall (may appear before or after clicking Apply)
            _handle_workday_login(page, log)
            _wait_for_page_ready(page)

            # If this is a job description page (no form yet), click the Apply CTA
            if not _has_form_elements(page):
                log("No form found — looking for Apply CTA button")
                if _click_apply_cta(page):
                    _wait_for_page_ready(page, timeout_ms=10000)
                    page.wait_for_timeout(2500)  # Extra wait for Workday SPA to render login form
                    # Check if Apply opened a new tab (common for Workday)
                    try:
                        all_pages = ctx.pages
                        if len(all_pages) > 1:
                            newest = all_pages[-1]
                            if newest != page:
                                log(f"Apply opened new tab — switching to: {newest.url[:80]}")
                                page = newest
                                page.set_default_timeout(20000)
                                _wait_for_page_ready(page)
                    except Exception as _e:
                        log(f"New-tab check error: {_e}")
                    # Handle Workday login wall that may appear after clicking Apply
                    _handle_workday_login(page, log)
                    _wait_for_page_ready(page)
                    if _detect_captcha(page):
                        log("CAPTCHA detected after Apply CTA — attempting solve...")
                        if not _try_solve_captcha(page, page.url, log_fn=log):
                            return "captcha", "\n".join(log_lines)
                        log("CAPTCHA solved after Apply CTA — continuing")
                else:
                    log("No Apply CTA found on description page")
                    # Log visible buttons for debugging
                    try:
                        btns = page.query_selector_all("button, [role='button'], a")
                        visible_btns = []
                        for b in btns[:25]:
                            if b.is_visible():
                                txt = (b.inner_text() or b.get_attribute("aria-label") or "").strip()[:40]
                                if txt:
                                    visible_btns.append(txt)
                        if visible_btns:
                            log(f"Visible buttons on page: {visible_btns[:10]}")
                            # Check if this looks like a job search homepage (no Apply button)
                            homepage_signals = ["search for jobs", "browse jobs", "explore careers",
                                                "find jobs", "job search", "back to jobs"]
                            btn_text_combined = " ".join(visible_btns).lower()
                            if any(s in btn_text_combined for s in homepage_signals):
                                log("Page looks like careers homepage — job expired/redirected")
                                return "expired", "\n".join(log_lines)
                        else:
                            log("No visible buttons — job may be blocked or expired")
                            return "expired", "\n".join(log_lines)
                    except Exception:
                        pass

            resume_uploaded = False

            # ── Red-state guard: reload once if errors are already visible on load ──
            try:
                _body_on_load = (page.inner_text("body", timeout=3000) or "").lower()
                _red_signals = ("is required", "field is required", "please fill", "invalid", "error")
                if any(s in _body_on_load for s in _red_signals):
                    log("Red-state detected on page load — reloading to clear error state")
                    page.reload(wait_until="domcontentloaded", timeout=20000)
                    _wait_for_page_ready(page)
            except Exception:
                pass

            # ── Submit blacklist: block submit/apply buttons until enough fields filled ──
            _submit_unlock_threshold = 5   # fields must be filled before Submit is allowed
            _total_fields_filled    = 0    # cumulative across all steps on this page
            _submit_locked          = True

            # ── "Don't Touch Blue" Rule: disable all Submit/Apply buttons via JS ──
            # This prevents accidental clicks from the vision model or fill logic
            # until we explicitly re-enable them after fields are verified.
            try:
                page.evaluate("""() => {
                    const SUBMIT_KWS = ['submit', 'apply', 'send application', 'complete application'];
                    document.querySelectorAll('button, input[type="submit"], [role="button"]').forEach(el => {
                        const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').toLowerCase().trim();
                        if (SUBMIT_KWS.some(kw => t === kw || t.startsWith(kw + ' '))) {
                            el.dataset._hireagentBlocked = 'true';
                            el.style.visibility = 'hidden';
                            el.style.pointerEvents = 'none';
                        }
                    });
                }""")
                log("  Submit/Apply buttons HIDDEN (blindfold) until fields verified")
            except Exception:
                pass

            # ── URL snapshot for early-submission detection ──
            _url_before_fill = page.url

            # Multi-step form loop (up to 50 steps — Workday can be very long)
            _wd_signin_attempts = 0  # Track consecutive sign-in attempts (fail-fast after 3)
            _last_page_hash = ""    # Stagnation detector: page content hash
            _stagnant_steps = 0     # Consecutive steps with no page change
            _field_error_counts: dict[str, int] = {}   # label → consecutive error count
            for step in range(1, 151):
                try:
                    log(f"--- Step {step} [url: {page.url[:80]}] ---")
                except Exception:
                    log(f"--- Step {step} ---")

                # Detect Workday application-level sign-in form.
                # Triggers on "Create Account / Sign In" step of the application.
                # signInSubmitButton is always aria-hidden — clicking it opens the sign-in
                # options modal (Apple / Google / Email). We click "Sign in with email"
                # (SignInWithEmailButton), wait for email+password to expand, fill via
                # React-compatible JS, then JS-click signInSubmitButton to submit.
                try:
                    _wd_signin_btn = page.locator(
                        "[data-automation-id='signInSubmitButton']"
                    ).first
                    _app_signin_visible = False
                    try:
                        _app_signin_visible = _wd_signin_btn.is_visible(timeout=1000)
                    except Exception:
                        pass
                    if not _app_signin_visible:
                        # Sign-in button gone → successfully past sign-in step
                        if _wd_signin_attempts > 0:
                            log(f"  Sign-in form gone — logged in successfully")
                        _wd_signin_attempts = 0
                    if _app_signin_visible:
                        import os as _os
                        _wd_email = _os.environ.get("WORKDAY_EMAIL", "")
                        _wd_pw = _os.environ.get("WORKDAY_PASSWORD", "")
                        if not _wd_email or not _wd_pw:
                            log(f"  WORKDAY_EMAIL/PASSWORD not set — skipping app-level sign-in")
                        else:
                            _wd_signin_attempts += 1
                            log(f"  App-level Workday sign-in on step {step} (attempt {_wd_signin_attempts})")
                            # After 3 consecutive sign-in attempts with no progress, try create-account or fail
                            if _wd_signin_attempts > 3:
                                log(f"  Sign-in stuck after {_wd_signin_attempts} attempts — trying create-account or aborting")
                                _ca_done = False
                                try:
                                    _ca_btn = page.locator(
                                        "[data-automation-id='createAccountLink'], "
                                        "[data-automation-id='createAccountButton'], "
                                        "button:has-text('Create Account'), a:has-text('Create Account'), "
                                        "button:has-text('Create an account'), a:has-text('Create an account')"
                                    ).first
                                    if _ca_btn.is_visible(timeout=800):
                                        log(f"    Create Account button found — attempting")
                                        _ca_btn.click(force=True)
                                        page.wait_for_timeout(1500)
                                        _ca_done = True
                                except Exception:
                                    pass
                                if not _ca_done:
                                    return "failed:workday_auth_error", "\n".join(log_lines)
                                # Reset counter after create-account click so it doesn't re-trigger immediately
                                _wd_signin_attempts = 0
                            # Step A: click "Sign in with email" DIRECTLY on the page (not via modal)
                            # SignInWithEmailButton is directly visible at y~838, before any modal.
                            # Clicking it expands an inline email+password form.
                            _email_btn_clicked = False
                            for _email_sel in [
                                "[data-automation-id='SignInWithEmailButton']",
                                "button:has-text('Sign in with email')",
                                "button:has-text('Use email')",
                            ]:
                                try:
                                    _email_btn = page.locator(_email_sel).first
                                    if _email_btn.is_visible(timeout=1500):
                                        _email_btn.click(force=True)
                                        page.wait_for_timeout(2000)
                                        log(f"    Clicked 'Sign in with email' ({_email_sel})")
                                        _email_btn_clicked = True
                                        break
                                except Exception:
                                    pass
                            if not _email_btn_clicked:
                                # Fallback: open the options modal and click email button inside it
                                try:
                                    _wd_signin_btn.click(force=True, timeout=2000)
                                    page.wait_for_timeout(1000)
                                    for _ms in ["[data-automation-id='SignInWithEmailButton']",
                                                "button:has-text('Sign in with email')"]:
                                        try:
                                            _mb = page.locator(_ms).first
                                            if _mb.is_visible(timeout=1000):
                                                _mb.click(force=True)
                                                page.wait_for_timeout(1500)
                                                log(f"    Clicked email btn via modal fallback ({_ms})")
                                                _email_btn_clicked = True
                                                break
                                        except Exception:
                                            pass
                                except Exception as _e:
                                    log(f"    Modal fallback error: {_e}")
                            if not _email_btn_clicked:
                                log(f"    'Sign in with email' button not found anywhere")

                            # Step C: fill email + password using React-compatible setter
                            try:
                                _js_fill_result = page.evaluate("""([emailVal, pwVal]) => {
                                    function reactSet(el, val) {
                                        const desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                                        if (desc && desc.set) desc.set.call(el, val);
                                        else el.value = val;
                                        ['input', 'change'].forEach(t =>
                                            el.dispatchEvent(new Event(t, { bubbles: true }))
                                        );
                                    }
                                    const emailEl = document.querySelector(
                                        "[data-automation-id='email'] input, " +
                                        "input[type='email'], input[autocomplete='email'], " +
                                        "input[name='email']"
                                    );
                                    const pwEl = document.querySelector(
                                        "input[type='password'], [data-automation-id='password']"
                                    );
                                    if (emailEl) reactSet(emailEl, emailVal);
                                    if (pwEl) reactSet(pwEl, pwVal);
                                    return `email=${!!emailEl},pw=${!!pwEl}`;
                                }""", [_wd_email, _wd_pw])
                                log(f"    React-fill: {_js_fill_result}")
                                page.wait_for_timeout(500)
                            except Exception as _e:
                                log(f"    React-fill error: {_e}")

                            # Step D: submit — find the inline email-form submit button
                            # After clicking "sign in with email", an email+password form expands.
                            # Its submit button is NOT signInSubmitButton (which opens options modal).
                            # Log all buttons to identify the correct one.
                            try:
                                _js_submit = page.evaluate("""([emailVal, pwVal]) => {
                                    function reactSet(el, val) {
                                        const desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                                        if (desc && desc.set) desc.set.call(el, val);
                                        else el.value = val;
                                        ['input', 'change'].forEach(t =>
                                            el.dispatchEvent(new Event(t, { bubbles: true }))
                                        );
                                    }
                                    // Re-fill credentials to make sure they're current
                                    const emailEl = document.querySelector(
                                        "input[type='email'], input[autocomplete='email'], input[name='email']"
                                    );
                                    const pwEl = document.querySelector("input[type='password']");
                                    if (emailEl) reactSet(emailEl, emailVal);
                                    if (pwEl) reactSet(pwEl, pwVal);

                                    // Find all visible submit buttons and their positions
                                    const allBtns = Array.from(document.querySelectorAll(
                                        "button[type='submit'], input[type='submit']"
                                    ));
                                    const btnInfo = allBtns.map(b => {
                                        const r = b.getBoundingClientRect();
                                        return `y=${Math.round(r.y)} aid=${b.getAttribute('data-automation-id')||''} t="${(b.textContent||b.value||'').trim().slice(0,20)}"`;
                                    }).join(' | ');

                                    // Click the LOWEST positioned submit button (form button, not nav)
                                    // EXCLUDE signInSubmitButton — it's the ghost modal-opener that
                                    // would dismiss the inline email form we just expanded.
                                    let best = null, bestY = -1;
                                    for (const b of allBtns) {
                                        const aid = b.getAttribute('data-automation-id') || '';
                                        if (aid === 'utilityButtonSignIn') continue;
                                        if (aid === 'signInSubmitButton') continue;
                                        const r = b.getBoundingClientRect();
                                        if (r.width === 0 || r.height === 0) continue;
                                        if (r.y > bestY) {
                                            bestY = r.y;
                                            best = b;
                                        }
                                    }
                                    if (best) {
                                        best.click();
                                        return 'clicked_y' + Math.round(bestY) + ':' + (best.textContent||best.value||'').trim().slice(0,20) + ' | btns:' + btnInfo;
                                    }
                                    return 'not_found | btns:' + btnInfo;
                                }""", [_wd_email, _wd_pw])
                                log(f"    Submit result: {_js_submit}")
                                page.wait_for_timeout(1000)
                            except Exception as _e:
                                log(f"    Submit error: {_e}")

                            # Press Enter in password field — most reliable way to submit inline sign-in form
                            try:
                                _pw_inp = page.locator("input[type='password']").first
                                if _pw_inp.is_visible(timeout=800):
                                    _pw_inp.focus()
                                    page.wait_for_timeout(200)
                                    _pw_inp.press("Enter")
                                    log(f"    Pressed Enter in password field")
                                    page.wait_for_timeout(4000)
                                else:
                                    page.wait_for_timeout(3000)
                            except Exception as _e:
                                log(f"    Enter-press error: {_e}")
                                page.wait_for_timeout(3000)

                            # Check for sign-in errors
                            _signin_error = None
                            try:
                                _err_el = page.locator(
                                    "[data-automation-id='errorMessage'], "
                                    "[aria-live='assertive']:not(:empty), "
                                    "[class*='error']:visible"
                                ).first
                                if _err_el.is_visible(timeout=1000):
                                    _signin_error = (_err_el.inner_text() or "").strip()[:150]
                                    log(f"    Sign-in error: '{_signin_error}'")
                            except Exception:
                                pass

                            _wait_for_page_ready(page)
                            log(f"  App-level sign-in attempt complete")

                            # If credentials are wrong / account locked, try create-account first
                            # (handles first-time users who have no existing Workday account)
                            if _signin_error and any(kw in _signin_error.lower() for kw in
                                    ["wrong email", "wrong password", "locked", "incorrect",
                                     "invalid", "not found", "does not exist"]):
                                _ca_done = False
                                try:
                                    _ca_btn_loc = page.locator(
                                        "[data-automation-id='createAccountLink'], "
                                        "[data-automation-id='createAccountButton'], "
                                        "button:has-text('Create Account'), a:has-text('Create Account'), "
                                        "button:has-text('Create an account'), a:has-text('Create an account'), "
                                        "a:has-text('Register'), button:has-text('Register')"
                                    )
                                    _verify_loc = page.locator(
                                        "[data-automation-id='verifyPassword'], "
                                        "[data-automation-id='confirmPassword']"
                                    )
                                    _has_ca = False
                                    try:
                                        _has_ca = (
                                            _ca_btn_loc.first.is_visible(timeout=800) or
                                            _verify_loc.first.is_visible(timeout=800)
                                        )
                                    except Exception:
                                        pass
                                    if _has_ca:
                                        log(f"    Create Account option detected — attempting account creation")
                                        try:
                                            if _ca_btn_loc.first.is_visible(timeout=500):
                                                _ca_btn_loc.first.click(force=True)
                                                page.wait_for_timeout(1500)
                                                log(f"    Clicked Create Account button")
                                        except Exception:
                                            pass
                                        # Fill all create-account fields via React-compatible setter
                                        _ca_fill = page.evaluate("""([emailVal, pwVal, fn, ln]) => {
                                            function reactSet(el, val) {
                                                const desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                                                if (desc && desc.set) desc.set.call(el, val);
                                                else el.value = val;
                                                ['input', 'change'].forEach(t =>
                                                    el.dispatchEvent(new Event(t, { bubbles: true }))
                                                );
                                            }
                                            // Fill ALL password inputs (password + confirm/verify)
                                            const pwInputs = document.querySelectorAll("input[type='password']");
                                            for (const pw of pwInputs) reactSet(pw, pwVal);
                                            // Fill email
                                            const emailEl = document.querySelector(
                                                "input[type='email'], [data-automation-id='email'] input, " +
                                                "input[autocomplete='email'], input[name='email']"
                                            );
                                            if (emailEl) reactSet(emailEl, emailVal);
                                            // Fill name fields if present
                                            const fnEl = document.querySelector(
                                                "[data-automation-id='firstName'] input, " +
                                                "[data-automation-id='legalName--firstName'] input, " +
                                                "input[name='firstName'], input[id*='firstName']"
                                            );
                                            if (fnEl) reactSet(fnEl, fn);
                                            const lnEl = document.querySelector(
                                                "[data-automation-id='lastName'] input, " +
                                                "[data-automation-id='legalName--lastName'] input, " +
                                                "input[name='lastName'], input[id*='lastName']"
                                            );
                                            if (lnEl) reactSet(lnEl, ln);
                                            return `email=${!!emailEl},fn=${!!fnEl},ln=${!!lnEl},pwCount=${pwInputs.length}`;
                                        }""", [_wd_email, _wd_pw,
                                               field_data.get("first_name", ""),
                                               field_data.get("last_name", "")])
                                        log(f"    Create account fill: {_ca_fill}")
                                        page.wait_for_timeout(500)
                                        # Submit the create-account form
                                        _ca_submit = page.evaluate("""() => {
                                            const btns = Array.from(document.querySelectorAll(
                                                "button[type='submit'], input[type='submit'], " +
                                                "[data-automation-id='createAccountButton']"
                                            ));
                                            const info = btns.map(b =>
                                                `aid=${b.getAttribute('data-automation-id')||''} t="${(b.textContent||b.value||'').trim().slice(0,20)}"`
                                            ).join(' | ');
                                            // Prefer buttons with "create"/"register"/"sign up" text
                                            for (const b of btns) {
                                                const t = (b.textContent || b.value || '').toLowerCase();
                                                if (t.includes('create') || t.includes('register') || t.includes('sign up')) {
                                                    b.click();
                                                    return 'create:' + t.slice(0, 20) + ' | ' + info;
                                                }
                                            }
                                            // Fallback: lowest positioned visible submit button
                                            let best = null, bestY = -1;
                                            for (const b of btns) {
                                                const r = b.getBoundingClientRect();
                                                if (r.width > 0 && r.height > 0 && r.y > bestY) {
                                                    bestY = r.y; best = b;
                                                }
                                            }
                                            if (best) {
                                                best.click();
                                                return 'lowest:' + (best.textContent||'').trim().slice(0,20) + ' | ' + info;
                                            }
                                            return 'not_found | ' + info;
                                        }""")
                                        log(f"    Create account submit: {_ca_submit}")
                                        page.wait_for_timeout(4000)
                                        _wait_for_page_ready(page)
                                        # Check for errors on the create-account form
                                        _ca_error = None
                                        try:
                                            _ca_err_el = page.locator(
                                                "[data-automation-id='errorMessage'], "
                                                "[aria-live='assertive']:not(:empty)"
                                            ).first
                                            if _ca_err_el.is_visible(timeout=1000):
                                                _ca_error = (_ca_err_el.inner_text() or "").strip()[:150]
                                                log(f"    Create account error: '{_ca_error}'")
                                        except Exception:
                                            pass
                                        if not _ca_error:
                                            log(f"    Create account succeeded — continuing")
                                            _ca_done = True
                                except Exception as _ca_ex:
                                    log(f"    Create account attempt error: {_ca_ex}")

                                if not _ca_done:
                                    log(f"  Workday credentials failed — aborting (check WORKDAY_EMAIL/PASSWORD)")
                                    return "failed:workday_auth_error", "\n".join(log_lines)

                            continue
                except Exception as _app_signin_err:
                    log(f"  App sign-in detection error: {_app_signin_err}")

                # ── Re-apply blindfold every step (React re-renders restore buttons) ──
                try:
                    page.evaluate("""() => {
                        const SUBMIT_KWS = ['submit', 'apply', 'send application', 'complete application'];
                        document.querySelectorAll('button, input[type="submit"], [role="button"]').forEach(el => {
                            const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').toLowerCase().trim();
                            if (SUBMIT_KWS.some(kw => t === kw || t.startsWith(kw + ' '))) {
                                el.dataset._hireagentBlocked = 'true';
                                el.style.visibility = 'hidden';
                                el.style.pointerEvents = 'none';
                            }
                        });
                    }""")
                except Exception:
                    pass

                # ── Vision-verified pass first (Nemotron + type_with_verification) ──
                _bc.page = page  # keep reference current after any page switches
                _v_filled, _v_errors = vision_verified_fill(
                    page, field_data, _nim, _bc, _capt, page.url
                )
                if _v_errors:
                    log(f"  Vision red-line errors: {_v_errors[:3]}")
                    # Track per-field error counts — send to Telegram after 2 consecutive failures
                    for _verr in (_v_errors or []):
                        _verr_key = str(_verr)[:60]
                        _field_error_counts[_verr_key] = _field_error_counts.get(_verr_key, 0) + 1
                        if _field_error_counts[_verr_key] >= 2:
                            log(f"  Field stuck in error x{_field_error_counts[_verr_key]}: {_verr_key}")
                            try:
                                from hireagent.telegram_bot import notify
                                _ss_err = Path(f"/tmp/hireagent_fielderr_{int(__import__('time').time())}.png")
                                page.screenshot(path=str(_ss_err), full_page=False)
                                notify(f"⚠️ Field error x{_field_error_counts[_verr_key]}: {_verr_key[:80]}\nWaiting for manual override…", _ss_err)
                            except Exception:
                                pass

                # ── Legacy selector-based pass for selects, radios, Workday dropdowns ──
                n_text = _fill_text_inputs(page, field_data)
                n_sel  = _fill_selects(page, field_data, intelligence=_nim)
                n_radio = _fill_radio_checkboxes(page, field_data)
                # ── Recursive Force-Select: re-check any dropdown still at placeholder ──
                n_force = _recursive_force_select(page, field_data, intelligence=_nim)
                if n_force:
                    log(f"  Force-select fixed {n_force} stuck dropdown(s)")
                log(f"  Filled: vision={_v_filled} text={n_text} selects={n_sel} radios={n_radio} force={n_force}")
                for _d in _wd_fill_diag:
                    log(f"    {_d}")

                # ── Dispatch blur after every fill pass (prevents Enter-key submission) ──
                try:
                    page.evaluate("""() => {
                        const active = document.activeElement;
                        if (active && active !== document.body) {
                            active.dispatchEvent(new Event('blur', {bubbles: true}));
                            active.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                    }""")
                except Exception:
                    pass

                # ── Track total fields filled ─────────────────────────────────
                _step_filled = (_v_filled or 0) + (n_text or 0) + (n_sel or 0) + (n_radio or 0) + (n_force or 0)
                _total_fields_filled += _step_filled
                # Submit button reveal is now done right before _find_submit_or_next above.
                # We no longer reveal mid-loop on a count threshold — that caused premature submit.

                # ── URL change detection: catch accidental early submission ──
                try:
                    _url_now = page.url
                    if _url_now != _url_before_fill and step <= 3:
                        log(f"  Early submission detected — URL changed before Submit: {_url_now[:80]}")
                        log("  Retrying with restricted button access")
                        _submit_locked = True   # re-lock submit
                        _total_fields_filled = 0
                        _url_before_fill = _url_now
                        _wait_for_page_ready(page)
                        continue
                    _url_before_fill = _url_now
                except Exception:
                    pass

                # Stagnation check: if page content hasn't changed for 10 consecutive steps, abort
                try:
                    import hashlib as _hashlib
                    _page_body = page.inner_text("body", timeout=2000)[:800]
                    _cur_hash = _hashlib.md5(_page_body.encode()).hexdigest()
                    if _cur_hash == _last_page_hash:
                        _stagnant_steps += 1
                        if _stagnant_steps >= 10:
                            log(f"  Page unchanged for {_stagnant_steps} steps — aborting (stuck)")
                            return "failed:stuck_loop", "\n".join(log_lines)
                        elif _stagnant_steps >= 3:
                            log(f"  Warning: page unchanged for {_stagnant_steps} steps")
                    else:
                        _stagnant_steps = 0
                    _last_page_hash = _cur_hash
                except Exception:
                    pass

                if resume_path and not resume_uploaded:
                    if _upload_resume(page, resume_path):
                        resume_uploaded = True
                        log(f"  Resume uploaded: {Path(resume_path).name}")
                        page.wait_for_timeout(1000)

                if _detect_captcha(page):
                    log("CAPTCHA detected during form fill — attempting solve via CaptchaSolver...")
                    if not _capt.solve(page, page.url):
                        log("CAPTCHA unsolvable during form fill")
                        return "captcha", "\n".join(log_lines)
                    log("CAPTCHA solved during form fill — continuing")

                # Log all visible buttons for diagnosis (first 5 steps only)
                if step <= 5 or step % 20 == 0:
                    try:
                        all_vis_btns = page.query_selector_all(
                            "button, [role='button'], input[type='submit']"
                        )
                        vis_btn_info = []
                        for _b in all_vis_btns[:30]:
                            try:
                                if _b.is_visible():
                                    _t = (_b.inner_text() or _b.get_attribute("value") or "").strip()[:30]
                                    _bt = _b.get_attribute("type") or ""
                                    _aid = _b.get_attribute("data-automation-id") or ""
                                    _box = _b.bounding_box() or {}
                                    vis_btn_info.append(
                                        f"'{_t}' type={_bt} aid={_aid} y={int(_box.get('y', -1))}"
                                    )
                            except Exception:
                                pass
                        log(f"  Visible buttons: {vis_btn_info[:10]}")
                    except Exception:
                        pass
                    # Also log page heading/text summary
                    try:
                        headings = page.query_selector_all("h1, h2, h3, [data-automation-id*='header'], [data-automation-id*='title'], [data-automation-id*='heading']")
                        heading_texts = []
                        for _h in headings[:5]:
                            try:
                                if _h.is_visible():
                                    _ht = (_h.inner_text() or "").strip()[:60]
                                    if _ht:
                                        heading_texts.append(_ht)
                            except Exception:
                                pass
                        if heading_texts:
                            log(f"  Page headings: {heading_texts}")
                    except Exception:
                        pass

                # ── Reveal submit only now — after fill passes are done ───────
                try:
                    page.evaluate("""() => {
                        document.querySelectorAll('[data-_hireagent-blocked]').forEach(el => {
                            el.style.visibility = 'visible';
                            el.style.pointerEvents = '';
                            delete el.dataset._hireagentBlocked;
                        });
                    }""")
                except Exception:
                    pass

                action, btn = _find_submit_or_next(page)
                try:
                    btn_text = (btn.inner_text() or btn.get_attribute("value") or "").strip()[:30] if btn else ""
                    log(f"  Next action: {action} (btn: '{btn_text}')")
                except Exception:
                    log(f"  Next action: {action}")

                # ── Hard guard: never submit on step 1 with 0 fields filled ──
                # This prevents immediately clicking Submit right after resume upload.
                _step_filled_so_far = (_v_filled or 0) + (n_text or 0) + (n_sel or 0) + (n_radio or 0) + (n_force or 0)
                if action == "submit" and step <= 2 and _step_filled_so_far == 0:
                    log(f"  [EARLY-SUBMIT GUARD] Submit found on step {step} with 0 fields filled — skipping, will fill first")
                    action = "none"  # force it to keep looping

                if action == "none":
                    # Check if we're on a success page already
                    if _detect_success(page):
                        log("Success page detected (no button needed)")
                        return "applied", "\n".join(log_lines)
                    # ── Vision-model fallback: SoM screenshot to find Submit ──────
                    log("No submit/next button found — trying vision model (SoM) fallback")
                    _bc.page = page
                    if find_submit_button_vision(page, _bc, _nim):
                        page.wait_for_timeout(2500)
                        _wait_for_page_ready(page)
                        if _detect_success(page):
                            log("Application submitted via vision fallback")
                            return "applied", "\n".join(log_lines)
                        continue  # submission navigated to next step
                    # Fallback: try Apply CTA click before giving up.
                    # This handles the case where we're still on the job description
                    # page and the Apply button wasn't matched by _find_submit_or_next.
                    log("Vision fallback failed — trying Apply CTA")
                    if _click_apply_cta(page):
                        _wait_for_page_ready(page, timeout_ms=10000)
                        page.wait_for_timeout(2000)
                        try:
                            all_pages = ctx.pages
                            if len(all_pages) > 1:
                                newest = all_pages[-1]
                                if newest != page:
                                    log(f"  Apply CTA opened new tab — switching to: {newest.url[:80]}")
                                    page = newest
                                    page.set_default_timeout(20000)
                                    _wait_for_page_ready(page)
                        except Exception as _nte:
                            log(f"  New-tab check error: {_nte}")
                        _handle_workday_login(page, log)
                        _wait_for_page_ready(page)
                        continue
                    # Also try a broader JS click on any visible "Apply" button as last resort
                    log("  CTA fallback failed — trying JS broad apply button search")
                    try:
                        _js_apply = page.evaluate("""() => {
                            const kws = ['apply now', 'apply for this job', 'apply to this job',
                                         'easily apply', 'easy apply', 'quick apply',
                                         'apply on company site', 'start application', 'apply'];
                            const els = Array.from(document.querySelectorAll(
                                'button, a, [role="button"], input[type="button"], input[type="submit"]'
                            ));
                            for (const kw of kws) {
                                for (const el of els) {
                                    const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').toLowerCase().trim();
                                    if (t === kw || t.startsWith(kw)) {
                                        const r = el.getBoundingClientRect();
                                        if (r.width > 0 && r.height > 0) {
                                            el.click();
                                            return 'clicked:' + t.slice(0, 40);
                                        }
                                    }
                                }
                            }
                            return 'not_found';
                        }""")
                        log(f"  JS apply search: {_js_apply}")
                        if _js_apply != "not_found":
                            _wait_for_page_ready(page, timeout_ms=10000)
                            page.wait_for_timeout(2000)
                            try:
                                all_pages = ctx.pages
                                if len(all_pages) > 1:
                                    newest = all_pages[-1]
                                    if newest != page:
                                        log(f"  JS Apply opened new tab — switching to: {newest.url[:80]}")
                                        page = newest
                                        page.set_default_timeout(20000)
                                        _wait_for_page_ready(page)
                            except Exception:
                                pass
                            _handle_workday_login(page, log)
                            _wait_for_page_ready(page)
                            continue
                    except Exception as _jse:
                        log(f"  JS apply search error: {_jse}")
                    log("All Apply button strategies exhausted — no submit button found")
                    return "failed:no_submit_button", "\n".join(log_lines)

                elif action == "next":
                    try:
                        btn.click(timeout=10000)
                    except Exception:
                        try:
                            btn.click(force=True, timeout=10000)
                        except Exception as click_e:
                            log(f"  Next button click error: {click_e}")
                    page.wait_for_timeout(2000)
                    # Check if Next opened a new tab (some ATS redirect to external forms)
                    try:
                        all_pages = ctx.pages
                        if len(all_pages) > 1:
                            newest = all_pages[-1]
                            if newest != page:
                                log(f"  Next opened new tab — switching to: {newest.url[:80]}")
                                page = newest
                                page.set_default_timeout(20000)
                                _wait_for_page_ready(page)
                    except Exception:
                        pass
                    continue

                elif action == "submit":
                    if dry_run:
                        log("[DRY RUN] Would click submit — stopping here")
                        return "dry_run", "\n".join(log_lines)

                    # ── Hard submit blacklist: not enough fields filled yet ────
                    if _submit_locked:
                        log(f"  [SUBMIT LOCKED] Only {_total_fields_filled}/{_submit_unlock_threshold} fields filled — skipping submit, filling more")
                        # Force another fill pass instead
                        _v_filled2, _ = vision_verified_fill(page, field_data, _nim, _bc, _capt, page.url)
                        n_text2 = _fill_text_inputs(page, field_data)
                        n_sel2  = _fill_selects(page, field_data, intelligence=_nim)
                        _total_fields_filled += (_v_filled2 or 0) + (n_text2 or 0) + (n_sel2 or 0)
                        if _total_fields_filled >= _submit_unlock_threshold:
                            _submit_locked = False
                            log(f"  Submit unlocked after retry pass (total={_total_fields_filled})")
                            try:
                                page.evaluate("""() => {
                                    document.querySelectorAll('[data-_hireagent-blocked]').forEach(el => {
                                        el.disabled = false;
                                        el.style.pointerEvents = '';
                                        delete el.dataset._hireagentBlocked;
                                    });
                                }""")
                                log("  Submit/Apply buttons RE-ENABLED")
                            except Exception:
                                pass
                        else:
                            log(f"  Still locked after retry (total={_total_fields_filled}) — skipping step")
                            continue

                    # ── Abort submit if ANY red error text is visible ─────────
                    try:
                        _red_errors = page.evaluate("""() => {
                            const hits = [];
                            for (const el of document.querySelectorAll('*')) {
                                const st = window.getComputedStyle(el);
                                if (st.display === 'none' || st.visibility === 'hidden') continue;
                                const txt = (el.innerText || '').trim().toLowerCase();
                                if (!txt || txt.length > 200) continue;
                                const color = st.color;
                                // Red text: rgb(r,g,b) where r >> g and r >> b
                                const m = color.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/);
                                if (m && parseInt(m[1]) > 150 && parseInt(m[2]) < 100 && parseInt(m[3]) < 100) {
                                    if (txt.includes('required') || txt.includes('error') || txt.includes('invalid') || txt.includes('please')) {
                                        hits.push(txt.slice(0,60));
                                    }
                                }
                            }
                            return hits.slice(0, 5);
                        }""")
                        if _red_errors:
                            log(f"  [SUBMIT BLOCKED] Red error text visible: {_red_errors} — not submitting")
                            continue
                    except Exception:
                        pass

                    # ── Greenhouse Submit Lock: pre_submit_check MUST pass ────
                    try:
                        _check_ok, _check_issues = pre_submit_check(page, field_data)
                        if not _check_ok:
                            log(f"  [SUBMIT BLOCKED] pre_submit_check failed: {_check_issues}")
                            log("  Skipping this step — will re-fill and retry next iteration")
                            continue
                        log("  [pre_submit_check] Passed — proceeding with submit")
                    except Exception as _psc_e:
                        log(f"  pre_submit_check error (non-fatal): {_psc_e}")

                    # ── Vision-Verified Submission: final_form_audit MUST pass ──
                    if not _final_form_audit(page, field_data, intelligence=_nim):
                        log("  [SUBMIT BLOCKED] _final_form_audit FAILED — retrying fill")
                        # One more force-select pass before looping back
                        _recursive_force_select(page, field_data, intelligence=_nim)
                        continue

                    # ── Senior QA Auditor: vision scan before EVERY submit ────
                    # Ground truth: Male / Asian / No disability / Gunakarthik Naidu / Master of Science
                    _audit_passed = False
                    for _audit_round in range(3):
                        try:
                            import base64 as _b64
                            _audit_ss = Path(f"/tmp/hireagent_audit_qa_{int(__import__('time').time())}.png")
                            page.screenshot(path=str(_audit_ss), full_page=False)
                            with open(str(_audit_ss), "rb") as _f:
                                _audit_b64 = _b64.b64encode(_f.read()).decode()
                            # Inject SoM overlay so auditor can reference element IDs
                            try:
                                from hireagent.apply.vision_loop import _SOM_INJECT_JS, _SOM_REMOVE_JS
                                _som_raw = page.evaluate(_SOM_INJECT_JS)
                                _som_map = {int(k): v for k, v in __import__('json').loads(_som_raw).items()} if _som_raw else {}
                                _audit_ss2 = Path(f"/tmp/hireagent_audit_som_{int(__import__('time').time())}.png")
                                page.screenshot(path=str(_audit_ss2), full_page=False)
                                with open(str(_audit_ss2), "rb") as _f2:
                                    _audit_b64 = _b64.b64encode(_f2.read()).decode()
                                page.evaluate(_SOM_REMOVE_JS)
                            except Exception:
                                _som_map = {}

                            _audit_result = _nim.audit_screen(_audit_b64, som_map=_som_map)
                            _audit_status = _audit_result.get("status", "PASS")
                            _blunder      = _audit_result.get("detected_blunder", "")
                            _elem_id      = _audit_result.get("offending_element_id")
                            _fix          = _audit_result.get("fix_instruction", "")

                            if _audit_status == "PASS":
                                log(f"  [AUDITOR] ✅ PASS (round {_audit_round + 1}) — form verified clean")
                                _audit_passed = True
                                break

                            # FAIL — log loudly and repair
                            log(f"\n{'='*60}")
                            log(f"  ⚠️  [AUDITOR] BLUNDER DETECTED: {_blunder}")
                            log(f"  ⚠️  Offending element: #{_elem_id}  Fix: {_fix}")
                            log(f"{'='*60}\n")
                            logger.warning("⚠️ [AUDITOR] BLUNDER DETECTED: %s. REPAIRING...", _blunder)

                            # ── Repair: target the offending element ─────────
                            _repaired = False
                            _blunder_lower = _blunder.lower()
                            _fix_lower     = _fix.lower()

                            # 1. EEO — gender declined
                            if "gender" in _blunder_lower or "gender" in _fix_lower:
                                for _g in ["Male", "Man"]:
                                    for _sel in page.query_selector_all("select"):
                                        try:
                                            _lbl = _get_label_text(page, _sel).lower()
                                            if "gender" in _lbl and _try_select_value(_sel, _g):
                                                log(f"  [AUDITOR] Repaired gender → '{_g}'")
                                                _repaired = True; break
                                        except Exception: pass
                                    if _repaired: break

                            # 2. Disability wrong
                            elif "disability" in _blunder_lower or "disability" in _fix_lower:
                                for _d in ["No, I do not have a disability", "No, I Don't Have a Disability",
                                           "I do not have a disability", "No"]:
                                    for _sel in page.query_selector_all("select"):
                                        try:
                                            _lbl = _get_label_text(page, _sel).lower()
                                            if "disability" in _lbl and _try_select_value(_sel, _d):
                                                log(f"  [AUDITOR] Repaired disability → '{_d}'")
                                                _repaired = True; break
                                        except Exception: pass
                                    if _repaired: break

                            # 3. First name truncated
                            elif "first name" in _blunder_lower or "guna" in _blunder_lower:
                                for _inp in page.query_selector_all("input[type='text'], input:not([type])"):
                                    try:
                                        _lbl = _get_label_text(page, _inp).lower()
                                        if "first" in _lbl or "given" in _lbl:
                                            _inp.scroll_into_view_if_needed()
                                            _inp.click(); page.wait_for_timeout(300)
                                            _inp.fill(""); page.keyboard.type(field_data.get("first_name", "Gunakarthik Naidu"), delay=30)
                                            page.keyboard.press("Tab")
                                            log(f"  [AUDITOR] Repaired first name → '{field_data.get('first_name','Gunakarthik Naidu')}'")
                                            _repaired = True; break
                                    except Exception: pass

                            # 4. Degree / dropdown placeholder
                            elif "degree" in _blunder_lower or "select" in _blunder_lower or "placeholder" in _blunder_lower:
                                _recursive_force_select(page, field_data, intelligence=_nim)
                                log("  [AUDITOR] Ran force-select to clear placeholder dropdowns")
                                _repaired = True

                            # 5. Generic: use SoM element ID if provided
                            elif _elem_id and _som_map.get(int(_elem_id)):
                                _meta = _som_map[int(_elem_id)]
                                _attr_sel = (
                                    f"#{_meta['id']}" if _meta.get("id") else
                                    f"[name='{_meta['name']}']" if _meta.get("name") else None
                                )
                                if _attr_sel and _fix:
                                    try:
                                        _target = page.locator(_attr_sel).first
                                        if _target.is_visible(timeout=500):
                                            _target.scroll_into_view_if_needed()
                                            _target.click(); page.wait_for_timeout(300)
                                            _target.fill(""); page.keyboard.type(_fix, delay=30)
                                            page.keyboard.press("Tab")
                                            log(f"  [AUDITOR] Repaired SoM#{_elem_id} → '{_fix[:40]}'")
                                            _repaired = True
                                    except Exception: pass

                            if not _repaired:
                                log(f"  [AUDITOR] No specific repair handler — running full re-fill")
                                _fill_selects(page, field_data, intelligence=_nim)
                                _fill_text_inputs(page, field_data)
                                _recursive_force_select(page, field_data, intelligence=_nim)

                            page.wait_for_timeout(600)

                        except Exception as _audit_e:
                            logger.warning("[AUDITOR] Error in audit round %d: %s", _audit_round + 1, _audit_e)
                            _audit_passed = True  # Don't block submit on auditor infrastructure failure
                            break

                    if not _audit_passed:
                        log("  [AUDITOR] All 3 repair rounds failed — submitting anyway (manual review needed)")

                    try:
                        btn.click(timeout=10000)
                    except Exception:
                        try:
                            btn.click(force=True, timeout=10000)
                        except Exception as click_e:
                            log(f"  Submit click error: {click_e} — trying JS click")
                            try:
                                page.evaluate("btn => btn.click()", btn)
                            except Exception:
                                pass
                    log("  Clicked submit button")

                    # Wait for navigation or confirmation
                    try:
                        page.wait_for_timeout(4000)
                    except Exception:
                        pass

                    # Check if submit opened a new tab (e.g. Indeed → external ATS)
                    try:
                        all_pages = ctx.pages
                        if len(all_pages) > 1:
                            newest = all_pages[-1]
                            if newest != page:
                                log(f"  Submit opened new tab — switching to: {newest.url[:80]}")
                                page = newest
                                page.set_default_timeout(20000)
                                _wait_for_page_ready(page)
                                _handle_workday_login(page, log)
                                _wait_for_page_ready(page)
                    except Exception:
                        pass

                    if _detect_captcha(page):
                        log("CAPTCHA appeared after submit — attempting solve...")
                        if not _try_solve_captcha(page, page.url, log_fn=log):
                            log("CAPTCHA unsolvable after submit")
                            return "captcha", "\n".join(log_lines)
                        log("CAPTCHA solved after submit — checking for success...")
                        page.wait_for_timeout(2000)
                        if _detect_success(page):
                            log("Application submitted after CAPTCHA solve!")
                            return "applied", "\n".join(log_lines)

                    if _detect_success(page):
                        log("Application submitted successfully!")
                        return "applied", "\n".join(log_lines)

                    # Maybe another confirmation step
                    action2, btn2 = _find_submit_or_next(page)
                    if action2 == "submit" and btn2:
                        try:
                            btn2.click(timeout=10000)
                        except Exception:
                            try:
                                btn2.click(force=True, timeout=10000)
                            except Exception:
                                try:
                                    page.evaluate("b => b.click()", btn2)
                                except Exception:
                                    pass
                        page.wait_for_timeout(3000)
                        if _detect_success(page):
                            log("Application submitted (confirmation step)")
                            return "applied", "\n".join(log_lines)

                    # No explicit confirmation — continue loop (multi-step form)
                    continue

            return "failed:too_many_steps", "\n".join(log_lines)

        except PlaywrightTimeout as e:
            log(f"Playwright timeout: {e}")
            return "expired", "\n".join(log_lines)
        except Exception as e:
            log(f"Playwright error ({type(e).__name__}): {e}")
            return f"failed:playwright_{type(e).__name__}", "\n".join(log_lines)
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
            # Do NOT close the browser — Chrome lifecycle is managed by chrome.py
