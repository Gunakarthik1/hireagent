"""Smart Resume Versioning Manager.

Core algorithm:
  For each new job JD:
    1. Score every existing version against the JD (O(N) where N = versions).
    2. If ANY version scores >= REUSE_THRESHOLD → reuse it (cheapest path).
    3. Otherwise → tailor a brand-new version and save it.

This collapses similar jobs (same tech stack, same level) onto one PDF,
saving LLM calls, disk space, and time.
"""

from __future__ import annotations

import json
import logging
import string
from datetime import datetime, timezone
from pathlib import Path

from hireagent.config import APP_DIR, load_profile
from hireagent.database import get_connection

log = logging.getLogger(__name__)

# If an existing version scores >= this against a new JD, we reuse it.
REUSE_THRESHOLD = 8

# Letter sequence for version IDs: A, B, …, Z, AA, AB, …
def _next_version_id(existing: list[str]) -> str:
    letters = string.ascii_uppercase
    if not existing:
        return "A"
    # Convert last used to next
    last = sorted(existing)[-1]
    # Increment like a base-26 number
    chars = list(last)
    i = len(chars) - 1
    while i >= 0:
        idx = letters.index(chars[i])
        if idx < 25:
            chars[i] = letters[idx + 1]
            return "".join(chars)
        chars[i] = "A"
        i -= 1
    return "A" + "".join(chars)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public API ────────────────────────────────────────────────────────────────

def assign_version(job_url: str, force_new: bool = False) -> dict | None:
    """Find or create a resume version for a given job.

    Args:
        job_url:   The job's primary key (url column).
        force_new: If True, skip reuse check and always create a new version.

    Returns:
        dict with keys: version_id, ats_score, resume_pdf_path, is_new
        or None if job has no full_description.
    """
    conn = get_connection()

    job_row = conn.execute(
        "SELECT url, title, site, location, full_description, fit_score "
        "FROM jobs WHERE url = ?", (job_url,)
    ).fetchone()

    if not job_row:
        log.warning("assign_version: job not found — %s", job_url)
        return None

    job = dict(zip(
        ["url", "title", "site", "location", "full_description", "fit_score"],
        job_row
    ))

    if not job["full_description"]:
        log.warning("assign_version: no full_description for %s", job["title"])
        return None

    # Already assigned?
    if not force_new:
        existing = conn.execute(
            "SELECT version_id, version_ats_score FROM jobs WHERE url = ?",
            (job_url,)
        ).fetchone()
        if existing and existing[0]:
            return {
                "version_id": existing[0],
                "ats_score":  existing[1],
                "resume_pdf_path": _get_pdf(existing[0]),
                "is_new": False,
            }

    # ── Step 1: Score all existing versions against this JD ──────────────────
    if not force_new:
        best = _find_best_version(job)
        if best:
            _link_job_to_version(job_url, best["version_id"], best["ats_score"])
            log.info(
                "Version reuse: '%s' → Version %s (ATS %d)",
                job["title"][:50], best["version_id"], best["ats_score"]
            )
            return {**best, "is_new": False}

    # ── Step 2: No match → tailor a new version ───────────────────────────────
    log.info("Creating new version for: %s", job["title"][:60])
    result = _create_new_version(job)
    if result:
        _link_job_to_version(job_url, result["version_id"], result["ats_score"])
    return result


def list_versions() -> list[dict]:
    """Return all resume versions with their job counts and metadata."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT rv.version_id, rv.resume_pdf_path, rv.role_cluster,
               rv.base_keywords, rv.created_at, rv.job_count,
               COALESCE(
                   (SELECT ROUND(AVG(vj.ats_score),1)
                    FROM version_jobs vj WHERE vj.version_id = rv.version_id),
               0) as avg_score
        FROM resume_versions rv
        ORDER BY rv.version_id
    """).fetchall()

    versions = []
    for r in rows:
        vid = r[0]
        jobs = conn.execute("""
            SELECT j.title, j.site, j.location, vj.ats_score
            FROM version_jobs vj
            JOIN jobs j ON j.url = vj.job_url
            WHERE vj.version_id = ?
            ORDER BY vj.ats_score DESC
        """, (vid,)).fetchall()

        versions.append({
            "version_id":    vid,
            "resume_pdf_path": r[1],
            "role_cluster":  r[2],
            "base_keywords": r[3],
            "created_at":    r[4],
            "job_count":     r[5] or 0,
            "avg_score":     r[6] or 0,
            "jobs": [
                {"title": j[0], "site": j[1], "location": j[2], "ats_score": j[3]}
                for j in jobs
            ],
        })
    return versions


def run_versioning(limit: int = 0, force_new: bool = False) -> dict:
    """Assign resume versions to all tailored jobs that don't have one yet.

    Args:
        limit:     Max jobs to process (0 = all).
        force_new: Skip reuse and always generate new versions.

    Returns:
        {"reused": int, "created": int, "skipped": int, "errors": int}
    """
    conn = get_connection()

    query = """
        SELECT url FROM jobs
        WHERE tailored_resume_path IS NOT NULL
          AND (resume_version_id IS NULL OR ? = 1)
          AND full_description IS NOT NULL
        ORDER BY fit_score DESC
    """
    args: list = [1 if force_new else 0]
    if limit > 0:
        query += f" LIMIT {limit}"

    job_urls = [r[0] for r in conn.execute(query, args).fetchall()]

    if not job_urls:
        log.info("No jobs needing version assignment.")
        return {"reused": 0, "created": 0, "skipped": 0, "errors": 0}

    log.info("Assigning versions to %d jobs...", len(job_urls))
    reused = created = skipped = errors = 0

    for url in job_urls:
        try:
            result = assign_version(url, force_new=force_new)
            if result is None:
                skipped += 1
            elif result["is_new"]:
                created += 1
            else:
                reused += 1
        except Exception as e:
            log.error("Version assignment error for %s: %s", url, e)
            errors += 1

    log.info("Versioning done: %d reused, %d created, %d skipped, %d errors",
             reused, created, skipped, errors)
    return {"reused": reused, "created": created, "skipped": skipped, "errors": errors}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _find_best_version(job: dict) -> dict | None:
    """Score all existing versions against this job. Return best if >= threshold."""
    conn = get_connection()
    versions = conn.execute(
        "SELECT version_id, resume_text FROM resume_versions"
    ).fetchall()

    if not versions:
        return None

    from hireagent.scoring.scorer import score_job

    best_score = 0
    best_vid   = None

    for vid, resume_text in versions:
        if not resume_text:
            continue
        result = score_job(resume_text, job)
        s = result.get("score", 0)
        log.debug("  Version %s vs '%s' → %d", vid, job["title"][:40], s)
        if s > best_score:
            best_score = s
            best_vid   = vid

    if best_vid and best_score >= REUSE_THRESHOLD:
        return {
            "version_id": best_vid,
            "ats_score": best_score,
            "resume_pdf_path": _get_pdf(best_vid),
        }
    return None


def _create_new_version(job: dict) -> dict | None:
    """Tailor a new resume for this job and save it as a new version."""
    conn = get_connection()

    # Get all existing version IDs to determine next letter
    existing_ids = [r[0] for r in conn.execute(
        "SELECT version_id FROM resume_versions"
    ).fetchall()]
    new_vid = _next_version_id(existing_ids)

    # Run the tailor for this one job
    try:
        from hireagent.scoring.tailor import tailor_one_job
        pdf_path, resume_text = tailor_one_job(job["url"])
    except Exception as e:
        log.error("Tailor failed for %s: %s", job["title"][:50], e)
        return None

    if not pdf_path:
        log.warning("Tailor returned no PDF for %s", job["title"][:50])
        return None

    # Score new version against this job
    from hireagent.scoring.scorer import score_job
    result = score_job(resume_text or "", job)
    ats_score = result.get("score", 0)

    # Infer role cluster from title / JD
    role_cluster = _infer_cluster(job)

    # Extract top keywords from resume text
    base_keywords = _extract_keywords(resume_text or "", top_n=15)

    now = _now()
    conn.execute("""
        INSERT OR REPLACE INTO resume_versions
            (version_id, resume_text, resume_pdf_path, base_keywords,
             role_cluster, created_at, last_used_at, job_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
    """, (new_vid, resume_text, str(pdf_path), base_keywords,
          role_cluster, now, now))
    conn.commit()

    log.info("New Version %s created (ATS %d) for: %s",
             new_vid, ats_score, job["title"][:50])
    return {
        "version_id": new_vid,
        "ats_score":  ats_score,
        "resume_pdf_path": str(pdf_path),
    }


def _link_job_to_version(job_url: str, version_id: str, ats_score: int) -> None:
    conn = get_connection()
    now = _now()

    conn.execute("""
        INSERT OR IGNORE INTO version_jobs (version_id, job_url, ats_score, matched_at)
        VALUES (?, ?, ?, ?)
    """, (version_id, job_url, ats_score, now))

    conn.execute("""
        UPDATE jobs SET resume_version_id = ?, version_ats_score = ?,
                        version_assigned_at = ?
        WHERE url = ?
    """, (version_id, ats_score, now, job_url))

    conn.execute("""
        UPDATE resume_versions
        SET last_used_at = ?,
            job_count = (SELECT COUNT(*) FROM version_jobs WHERE version_id = ?)
        WHERE version_id = ?
    """, (now, version_id, version_id))

    conn.commit()


def _get_pdf(version_id: str) -> str:
    conn = get_connection()
    row = conn.execute(
        "SELECT resume_pdf_path FROM resume_versions WHERE version_id = ?",
        (version_id,)
    ).fetchone()
    return row[0] if row else ""


def _infer_cluster(job: dict) -> str:
    title = (job.get("title") or "").lower()
    desc  = (job.get("full_description") or "").lower()[:500]
    text  = title + " " + desc

    if any(w in text for w in ("ml ", "machine learning", "deep learning", "ai ", "data science", "nlp")):
        return "ml"
    if any(w in text for w in ("devops", "sre", "infrastructure", "kubernetes", "terraform", "cloud engineer")):
        return "devops"
    if any(w in text for w in ("data engineer", "spark", "airflow", "etl", "warehouse")):
        return "data"
    if any(w in text for w in ("frontend", "react", "vue", "angular", "ui engineer", "ux engineer")):
        return "frontend"
    if any(w in text for w in ("fullstack", "full stack", "full-stack")):
        return "fullstack"
    if any(w in text for w in ("backend", "api", "microservice", "java", "spring", "fastapi", "django")):
        return "backend"
    return "software"


def _extract_keywords(text: str, top_n: int = 15) -> str:
    """Cheap keyword extraction: top N most-frequent non-trivial words."""
    STOP = {
        "the", "and", "for", "with", "are", "was", "were", "has", "have",
        "had", "but", "not", "you", "all", "can", "her", "was", "one",
        "our", "out", "day", "get", "use", "make", "that", "this", "from",
        "your", "which", "they", "will", "would", "been", "about", "into",
        "through", "more", "also", "its", "their", "each", "such", "other",
        "both", "resume", "experience", "skills", "team", "work",
    }
    import re
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.]{2,}", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in STOP:
            freq[w] = freq.get(w, 0) + 1
    top = sorted(freq, key=lambda k: freq[k], reverse=True)[:top_n]
    return ", ".join(top)
