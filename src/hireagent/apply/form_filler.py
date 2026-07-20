"""High-level form-filling API for Stage 7 (apply).

Strategy (DOM-first, then vision fallback):
  1. ATS-specific fillers  — Greenhouse / Lever / Workday / Ashby
  2. Generic smart filler  — label-matching via TEXT_PATTERNS
  3. Vision fallback        — Qwen-VL via Ollama (free, local)

All filling delegates to the battle-tested helpers in playwright_apply.py;
this module adds the public interface and ATS-specific entry points described
in the integration prompt.

Usage::

    from hireagent.apply.form_filler import (
        load_profile_for_form_filling,
        fill_form_for_ats,
        upload_resume_pdf,
        find_and_click_submit,
        verify_submission_success,
    )

    profile_data = load_profile_for_form_filling(job)
    success = fill_form_for_ats(page, ats_type, profile_data, job)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # playwright.sync_api.Page — imported lazily to avoid hard dep at import time

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------

def load_profile_for_form_filling(job: dict | None = None) -> dict:
    """Load ``~/.hireagent/profile.yaml`` and return a flat form-filling dict.

    Delegates to ``playwright_apply._build_field_data`` which already handles
    all edge-cases (name splitting, phone normalisation, EEO anchors, etc.).

    Args:
        job: Optional job dict — used to resolve salary from job description.

    Returns:
        Flat ``str → str`` mapping ready for form filling.
    """
    from hireagent import config
    from hireagent.apply.playwright_apply import _build_field_data

    profile = config.load_profile()
    return _build_field_data(profile, job or {})


# ---------------------------------------------------------------------------
# ATS-specific fillers
# ---------------------------------------------------------------------------

def fill_greenhouse_form(page, profile_data: dict, job: dict) -> bool:
    """Fill a Greenhouse application form.

    Greenhouse uses standard ``<input>`` / ``<select>`` elements with
    ``label[for=id]`` associations plus custom location comboboxes.
    The generic ``_fill_text_inputs`` + ``_fill_selects`` pass covers most
    fields; this function adds the Greenhouse-specific extras.

    Returns:
        True if at least one field was filled, False on complete failure.
    """
    from hireagent.apply.playwright_apply import (
        _fill_text_inputs,
        _fill_selects,
        _fill_radio_checkboxes,
    )

    try:
        n = 0
        n += _fill_text_inputs(page, profile_data)
        n += _fill_selects(page, profile_data)
        n += _fill_radio_checkboxes(page, profile_data)

        # Greenhouse location combobox: type city into the autocomplete and
        # wait for the suggestion to appear, then click it.
        _fill_greenhouse_location(page, profile_data)

        logger.info("[greenhouse] filled %d field(s)", n)
        return n > 0
    except Exception as exc:
        logger.warning("[greenhouse] fill error: %s", exc)
        return False


def _fill_greenhouse_location(page, profile_data: dict) -> None:
    """Fill Greenhouse location combobox (autocomplete widget)."""
    city  = profile_data.get("city", "")
    state = profile_data.get("state", "")
    if not city:
        return
    location_str = f"{city}, {state}" if state else city
    try:
        # Greenhouse renders a hidden input + visible combobox
        combobox = page.query_selector(
            "[data-field='job_application_location'] input, "
            "input[autocomplete='address-level2'], "
            "input[placeholder*='City'], "
            "input[aria-label*='ocation']"
        )
        if combobox and combobox.is_visible():
            combobox.click()
            page.wait_for_timeout(300)
            combobox.fill(city)
            page.wait_for_timeout(1200)
            # Click first suggestion
            suggestion = page.query_selector(
                "[data-qa='location-option'], "
                "[role='option']:first-child, "
                "ul[role='listbox'] li:first-child"
            )
            if suggestion:
                suggestion.click()
                page.wait_for_timeout(400)
                logger.debug("[greenhouse] location filled: %s", location_str)
    except Exception as exc:
        logger.debug("[greenhouse] location combobox error: %s", exc)


def fill_lever_form(page, profile_data: dict, job: dict) -> bool:
    """Fill a Lever application form.

    Lever uses ``name`` attributes like ``first_name``, ``last_name``, ``email``,
    ``phone``, ``org``, plus a custom cards-based multi-step form.

    Returns:
        True if at least one field was filled.
    """
    from hireagent.apply.playwright_apply import (
        _fill_text_inputs,
        _fill_selects,
        _fill_radio_checkboxes,
    )

    try:
        n = 0
        # Lever-specific name-attribute selectors (fastest path)
        lever_fields = [
            ("input[name='name']",       profile_data.get("full_name", "")),
            ("input[name='email']",      profile_data.get("email", "")),
            ("input[name='phone']",      profile_data.get("phone", "")),
            ("input[name='org']",        profile_data.get("current_company", "")),
            ("input[name='linkedin']",   profile_data.get("linkedin_url", "")),
            ("input[name='github']",     profile_data.get("github_url", "")),
            ("input[name='portfolio']",  profile_data.get("portfolio_url", "")),
            ("input[name='twitter']",    ""),
        ]
        for selector, value in lever_fields:
            if not value:
                continue
            try:
                loc = page.locator(selector)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.fill(str(value))
                    n += 1
            except Exception as e:
                logger.debug("[lever] field %s error: %s", selector, e)

        # Generic pass for remaining fields
        n += _fill_text_inputs(page, profile_data)
        n += _fill_selects(page, profile_data)
        n += _fill_radio_checkboxes(page, profile_data)

        logger.info("[lever] filled %d field(s)", n)
        return n > 0
    except Exception as exc:
        logger.warning("[lever] fill error: %s", exc)
        return False


def fill_workday_form(page, profile_data: dict, job: dict) -> bool:
    """Fill a Workday application form.

    Workday uses ``data-automation-id`` attributes and custom React dropdowns.
    Delegates entirely to ``_fill_workday_fields`` + the generic pass.

    Returns:
        True if at least one field was filled.
    """
    from hireagent.apply.playwright_apply import (
        _fill_workday_fields,
        _fill_text_inputs,
        _fill_selects,
        _fill_radio_checkboxes,
    )

    try:
        n = 0
        n += _fill_workday_fields(page, profile_data)
        n += _fill_text_inputs(page, profile_data)
        n += _fill_selects(page, profile_data)
        n += _fill_radio_checkboxes(page, profile_data)
        logger.info("[workday] filled %d field(s)", n)
        return n > 0
    except Exception as exc:
        logger.warning("[workday] fill error: %s", exc)
        return False


def fill_ashby_form(page, profile_data: dict, job: dict) -> bool:
    """Fill an Ashby application form (uses standard inputs + custom dropdowns)."""
    from hireagent.apply.playwright_apply import (
        _fill_text_inputs,
        _fill_selects,
        _fill_radio_checkboxes,
    )

    try:
        n = 0
        n += _fill_text_inputs(page, profile_data)
        n += _fill_selects(page, profile_data)
        n += _fill_radio_checkboxes(page, profile_data)
        logger.info("[ashby] filled %d field(s)", n)
        return n > 0
    except Exception as exc:
        logger.warning("[ashby] fill error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Generic smart filler
# ---------------------------------------------------------------------------

def fill_generic_form_smart(page, profile_data: dict, job: dict) -> bool:
    """Generic form-filling for any ATS using DOM-first strategy.

    1. Run all existing playwright_apply helpers (text, selects, radios).
    2. If nothing was filled, attempt vision fallback via Qwen-VL.

    Returns:
        True if at least one field was filled.
    """
    from hireagent.apply.playwright_apply import (
        _fill_text_inputs,
        _fill_selects,
        _fill_radio_checkboxes,
    )

    n = 0
    try:
        n += _fill_text_inputs(page, profile_data)
        n += _fill_selects(page, profile_data)
        n += _fill_radio_checkboxes(page, profile_data)
    except Exception as exc:
        logger.warning("[generic] fill error: %s", exc)

    if n == 0:
        logger.info("[generic] DOM fill found 0 fields — trying vision fallback")
        try:
            n += _vision_fallback_fill(page, profile_data)
        except Exception as exc:
            logger.warning("[generic] vision fallback error: %s", exc)

    logger.info("[generic] filled %d field(s)", n)
    return n > 0


def _vision_fallback_fill(page, profile_data: dict) -> int:
    """Use Qwen-VL to identify and fill fields that DOM traversal missed.

    Takes a screenshot, asks the local vision model to list visible form
    fields, then attempts to fill each one via CSS selector.

    Returns:
        Number of fields filled.
    """
    try:
        from hireagent.api.qwen_vision import find_unfilled_fields_with_vision
    except ImportError:
        logger.debug("[vision-fallback] qwen_vision not available")
        return 0

    try:
        screenshot = page.screenshot(type="png")
        fields = find_unfilled_fields_with_vision(screenshot)
        filled = 0
        for field_label, selector in fields:
            matched_value = _match_label_to_profile(field_label, profile_data)
            if not matched_value:
                continue
            try:
                loc = page.locator(selector)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.fill(str(matched_value))
                    filled += 1
                    logger.debug("[vision-fallback] '%s' → '%s'", field_label, str(matched_value)[:30])
            except Exception as e:
                logger.debug("[vision-fallback] fill error for '%s': %s", field_label, e)
        return filled
    except Exception as exc:
        logger.debug("[vision-fallback] error: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Dispatch: fill by ATS type
# ---------------------------------------------------------------------------

def fill_form_for_ats(page, ats_type: str, profile_data: dict, job: dict) -> bool:
    """Dispatch to the correct ATS filler based on *ats_type*.

    Falls back to ``fill_generic_form_smart`` for unknown ATS types.

    Args:
        page:         Playwright ``Page`` (sync or async).
        ats_type:     ATS name from ``ats_detector.detect_ats_type()``.
        profile_data: Flat profile dict from ``load_profile_for_form_filling()``.
        job:          Job dict from the database.

    Returns:
        True if at least one field was filled successfully.
    """
    dispatch = {
        "greenhouse":     fill_greenhouse_form,
        "lever":          fill_lever_form,
        "workday":        fill_workday_form,
        "ashby":          fill_ashby_form,
    }
    filler = dispatch.get(ats_type, fill_generic_form_smart)
    logger.info("[form_filler] ATS=%s → %s", ats_type, filler.__name__)
    return filler(page, profile_data, job)


# ---------------------------------------------------------------------------
# Field discovery helpers
# ---------------------------------------------------------------------------

def discover_form_fields(page) -> list[dict]:
    """Discover all fillable form fields on the current page.

    Returns a list of dicts with keys:
      - ``label``     : human-readable field name
      - ``selector``  : CSS selector to target this field
      - ``type``      : ``"text"``, ``"select"``, ``"radio"``, ``"checkbox"``
      - ``placeholder``: placeholder text (may be empty)

    This is used by ``fill_generic_form_smart`` and can be called independently
    for debugging purposes.
    """
    from hireagent.apply.playwright_apply import _get_label_text

    fields: list[dict] = []

    try:
        inputs = page.query_selector_all(
            "input[type='text'], input[type='email'], input[type='tel'], "
            "input[type='url'], input[type='number'], input:not([type]), "
            "textarea, select"
        )
        for el in inputs:
            try:
                if not el.is_visible():
                    continue
                input_type = el.get_attribute("type") or "text"
                name_attr  = el.get_attribute("name") or ""
                id_attr    = el.get_attribute("id") or ""
                placeholder = el.get_attribute("placeholder") or ""
                tag = el.evaluate("el => el.tagName.toLowerCase()")

                label_text = _get_label_text(page, el)
                if not label_text:
                    label_text = placeholder or name_attr.replace("_", " ").replace("-", " ").title()

                if name_attr:
                    selector = f"[name='{name_attr}']"
                elif id_attr:
                    selector = f"#{id_attr}"
                else:
                    selector = f"{tag}[placeholder='{placeholder}']" if placeholder else tag

                field_type = "select" if tag == "select" else input_type

                fields.append({
                    "label":       label_text.strip(),
                    "selector":    selector,
                    "type":        field_type,
                    "placeholder": placeholder,
                })
            except Exception:
                continue
    except Exception as exc:
        logger.debug("[discover_form_fields] error: %s", exc)

    return fields


def match_field_to_profile(field_label: str, profile_data: dict) -> str | None:
    """Return a profile value for *field_label*, or None if no match.

    Delegates to the TEXT_PATTERNS table in playwright_apply so the mapping
    stays consistent with the existing fill logic.
    """
    return _match_label_to_profile(field_label, profile_data)


def _match_label_to_profile(field_label: str, profile_data: dict) -> str | None:
    """Internal helper — maps a label string to a profile_data value."""
    from hireagent.apply.playwright_apply import _match_text_field

    field_key = _match_text_field(field_label)
    if field_key:
        return profile_data.get(field_key)

    # Additional mappings not in TEXT_PATTERNS
    label_lower = field_label.lower()
    extra_map = {
        "work authorization": "auth_yes",
        "visa": "visa_status",
        "sponsorship": "needs_sponsor",
        "disability": "disability",
        "veteran": "veteran",
        "salary": "salary",
        "expected salary": "salary",
        "desired compensation": "salary",
        "years of experience": "years_experience",
        "school": "school",
        "university": "school",
        "graduation": "graduation_date",
        "degree": "degree",
        "gpa": "gpa",
        "gender": "gender",
        "race": "race",
        "ethnicity": "race",
    }
    for key_phrase, profile_key in extra_map.items():
        if key_phrase in label_lower:
            val = profile_data.get(profile_key)
            if isinstance(val, bool):
                return "Yes" if val else "No"
            return str(val) if val is not None else None

    return None


# ---------------------------------------------------------------------------
# Resume upload
# ---------------------------------------------------------------------------

def upload_resume_pdf(page, pdf_path: str | Path) -> bool:
    """Upload *pdf_path* to a file input on the current page.

    Tries both visible and hidden file inputs (Greenhouse Dropzone, Ashby,
    Lever drag-drop areas).

    Returns:
        True if the file was set on an input element.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        logger.warning("[upload_resume] file not found: %s", pdf_path)
        return False

    # Reveal hidden file inputs (Dropzone / Ashby pattern)
    try:
        page.evaluate("""
            document.querySelectorAll('input[type="file"]').forEach(el => {
                el.removeAttribute('disabled');
                el.style.display = 'block';
                el.style.visibility = 'visible';
                el.style.opacity = '1';
            });
        """)
    except Exception:
        pass

    # Try clicking dropzone triggers first
    trigger_selectors = [
        'button[class*="resume"]', 'button[class*="upload"]', 'button[class*="attach"]',
        '.dz-clickable', '.dropzone', '[class*="dropzone"]', '[class*="file-upload"]',
        '[data-qa*="upload"]', '[aria-label*="resume"]', '[aria-label*="upload"]',
        'label[for*="resume"]', 'label[for*="file"]', 'label[for*="upload"]',
    ]
    for sel in trigger_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible() and el.evaluate("el => el.tagName") != "INPUT":
                el.click()
                page.wait_for_timeout(800)
                break
        except Exception:
            continue

    # Now find and set the file input
    try:
        file_input = page.query_selector("input[type='file']")
        if file_input:
            file_input.set_input_files(str(pdf_path))
            page.wait_for_timeout(600)
            logger.info("[upload_resume] uploaded: %s", pdf_path.name)
            return True
    except Exception as exc:
        logger.warning("[upload_resume] set_input_files error: %s", exc)

    return False


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------

def find_and_click_submit(page) -> bool:
    """Find and click the primary submit / apply button on the current page.

    Returns:
        True if a button was found and clicked.
    """
    submit_selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Submit Application')",
        "button:has-text('Submit')",
        "button:has-text('Apply Now')",
        "button:has-text('Apply')",
        "button:has-text('Send Application')",
        "[data-qa='btn-submit']",
        "[data-testid='submit-button']",
        "[aria-label='Submit application']",
    ]
    for selector in submit_selectors:
        try:
            btn = page.locator(selector).first
            if btn.count() > 0 and btn.is_visible():
                btn.scroll_into_view_if_needed(timeout=2000)
                btn.click(timeout=5000)
                logger.info("[submit] clicked: %s", selector)
                return True
        except Exception:
            continue
    logger.warning("[submit] no submit button found")
    return False


# ---------------------------------------------------------------------------
# Success verification
# ---------------------------------------------------------------------------

def verify_submission_success(page) -> bool:
    """Return True if the page indicates a successful application submission."""
    success_phrases = [
        "thank you for applying",
        "application submitted",
        "application received",
        "successfully applied",
        "your application has been submitted",
        "we have received your application",
        "application complete",
        "you've applied",
        "you have applied",
    ]
    try:
        page_text = page.content().lower()
        for phrase in success_phrases:
            if phrase in page_text:
                logger.info("[verify] success phrase found: '%s'", phrase)
                return True

        # Also check URL for confirmation paths
        current_url = (page.url or "").lower()
        for path in ("/confirmation", "/success", "/thank-you", "/thankyou", "/applied"):
            if path in current_url:
                logger.info("[verify] success URL path: %s", current_url)
                return True
    except Exception as exc:
        logger.debug("[verify] error: %s", exc)

    return False
