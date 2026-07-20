"""ATS detection: identify which Applicant Tracking System a job URL belongs to.

This module exposes ``detect_ats_type(url)`` as a clean public API.
Internally it extends the existing ``_ATS_HINTS`` table in launcher.py with
additional patterns sourced from:
  - Job App Filler (berellevy/job_app_filler)
  - Greenhouse Filler (nuxeric/greenhouse-application-filler)
  - Career-Ops Portal Scanner (santifer/career-ops)
"""

from __future__ import annotations

from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# ATS detection rules
# Each entry: (ats_name, url_substring_to_match)
# Order matters — more specific patterns should come first.
# ---------------------------------------------------------------------------

_DETECTION_RULES: list[tuple[str, str]] = [
    # Greenhouse
    ("greenhouse", "boards.greenhouse.io"),
    ("greenhouse", "jobs.greenhouse.io"),
    ("greenhouse", "app.greenhouse.io"),
    ("greenhouse", "greenhouse.io/embed"),
    ("greenhouse", "grnh.se"),
    ("greenhouse", "greenhouse.io"),
    # Lever
    ("lever", "jobs.lever.co"),
    ("lever", "apply.lever.co"),
    ("lever", "lever.co"),
    # Workday
    ("workday", "myworkday.com"),
    ("workday", "workday.com"),
    ("workday", "/webcas/login"),
    ("workday", "/recruiting"),
    # Ashby
    ("ashby", "jobs.ashby.io"),
    ("ashby", "ashbyhq.com"),
    ("ashby", "ashby.io"),
    # SmartRecruiters
    ("smartrecruiters", "careers.smartrecruiters.com"),
    ("smartrecruiters", "smartrecruiters.com"),
    # iCIMS
    ("icims", "jobs.icims.com"),
    ("icims", "icims.com"),
    # Taleo (Oracle)
    ("taleo", "taleo.taleo.net"),
    ("taleo", "taleo.net"),
    # Oracle HCM
    ("oracle-hcm", "oraclecloud.com"),
    # SAP SuccessFactors
    ("successfactors", "successfactors.com"),
    ("successfactors", "successfactors.eu"),
    # Jobvite
    ("jobvite", "apply.jobvite.com"),
    ("jobvite", "jobvite.com"),
    # BambooHR
    ("bamboohr", "bamboohr.com"),
    # Rippling
    ("rippling", "ats.rippling.com"),
    ("rippling", "rippling.com"),
    # LinkedIn Easy Apply
    ("linkedin", "linkedin.com/jobs"),
    ("linkedin", "linkedin.com"),
    # JazzHR
    ("jazzhr", "app.jazz.co"),
    ("jazzhr", "jazz.co"),
    # Pinpoint
    ("pinpoint", "pinpointhq.com"),
    # Recruitee
    ("recruitee", "recruitee.com"),
    # Workable
    ("workable", "jobs.workable.com"),
    ("workable", "workable.com"),
    # Breezy HR
    ("breezyhr", "breezy.hr"),
    # Avature
    ("avature", "avature.net"),
    # Bullhorn
    ("bullhorn", "bullhornstaffing.com"),
    # Eightfold
    ("eightfold", "eightfold.ai"),
]

# ATS platforms that require a logged-in session or manual action —
# the apply pipeline skips these automatically.
MANUAL_ATS: frozenset[str] = frozenset({
    "linkedin",
    "oracle-hcm",
    "taleo",
    "successfactors",
    "bullhorn",
})


def detect_ats_type(url: str | None) -> str:
    """Return the ATS name for *url*, or ``"generic"`` if unknown.

    Examples::

        detect_ats_type("https://boards.greenhouse.io/acme/jobs/123")
        # → "greenhouse"

        detect_ats_type("https://jobs.lever.co/openai/abc")
        # → "lever"

        detect_ats_type("https://careers.example.com/apply")
        # → "generic"

    Args:
        url: Full application URL (may be ``None``).

    Returns:
        Lower-case ATS name string, or ``"generic"`` when no rule matches.
    """
    if not url:
        return "generic"
    lowered = url.lower()
    for ats_name, pattern in _DETECTION_RULES:
        if pattern in lowered:
            return ats_name
    # Fall back to bare hostname so callers can log something meaningful
    host = urlparse(url).netloc
    return host or "generic"


def is_supported_ats(ats_type: str) -> bool:
    """Return True if HireAgent has a dedicated filler for this ATS."""
    return ats_type in {"greenhouse", "lever", "workday", "ashby", "generic"}


def requires_manual_apply(ats_type: str) -> bool:
    """Return True if this ATS requires a human to apply manually."""
    return ats_type in MANUAL_ATS
