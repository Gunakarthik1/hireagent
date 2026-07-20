"""Job fit scoring: LLM-powered evaluation of candidate-job match quality.

Scores jobs on a 1-10 scale by comparing the user's resume against each
job description. All personal data is loaded at runtime from the user's
profile and resume file.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

from hireagent.config import RESUME_PATH, load_profile
from hireagent.database import get_connection, get_jobs_by_stage
from hireagent.llm import get_score_client

log = logging.getLogger(__name__)


# ── Scoring Prompt ────────────────────────────────────────────────────────

SCORE_PROMPT = """You are a Senior Technical Recruiter. Evaluate how well this resume matches the job description.

## CHAIN OF THOUGHT — reason step by step before scoring:
1. List the must-have technical skills and requirements from the JD.
2. For each must-have, check: does the resume demonstrate this? (yes/partial/no)
3. Check seniority: does the candidate's level match what the JD requires?
4. Check any hard blockers: missing core language, degree requirement, sponsorship incompatibility.
5. Calculate final score based on the above analysis.

## SCORING SCALE (0-10):
- 9-10: Strong match — 80%+ requirements met, right seniority, no blockers
- 7-8:  Good match — 60-80% requirements met, minor gaps
- 5-6:  Partial match — 40-60% met, notable gaps but viable
- 3-4:  Weak match — under 40% met, significant gaps
- 0-2:  Hard blocker — missing core required language/degree, clear seniority mismatch, or sponsorship required but unavailable

## OUTPUT: Return ONLY valid JSON. No markdown fences. No preamble. No commentary.
{"score": <integer 0-10>, "reasoning": "<2-3 sentences: what matched, what gaps exist, final verdict>"}"""


def _parse_score_response(response: str) -> dict:
    """Parse the LLM's JSON score response into structured data.

    Returns:
        {"score": int, "keywords": str, "reasoning": str}
    """
    # Strip markdown fences if the LLM ignored instructions
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
        cleaned = cleaned.strip()

    # Extract JSON object even when LLM adds preamble text before/after
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if json_match:
        cleaned = json_match.group(0)

    try:
        data = json.loads(cleaned)
        # Support both new {"score": int, "reasoning": str} and legacy {"fit_score": int} formats
        score = int(data.get("score", data.get("fit_score", 0)))
        score = max(0, min(10, score))
        reasoning = data.get("reasoning", "")
        # Legacy fields (still extracted if present)
        matched = data.get("matched_keywords", "")
        missing = data.get("missing_critical_keywords", "")
        keywords = f"MATCHED: {matched} | MISSING: {missing}" if (matched or missing) else ""
        return {"score": score, "keywords": keywords, "reasoning": reasoning}
    except (json.JSONDecodeError, ValueError, TypeError):
        # Fallback: try legacy plain-text format and Ollama markdown format
        score = 0
        keywords = ""
        reasoning = response
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("SCORE:"):
                try:
                    score = int(re.search(r"\d+", line).group())
                    score = max(1, min(10, score))
                except (AttributeError, ValueError):
                    score = 0
            elif line.startswith("KEYWORDS:"):
                keywords = line.replace("KEYWORDS:", "").strip()
            elif line.startswith("REASONING:"):
                reasoning = line.replace("REASONING:", "").strip()

        # If no SCORE: found, try to extract from Ollama markdown responses:
        # "**Final score:** 7-8 (Good match)" or "**Final score:** 5/10"
        if score == 0:
            m = re.search(r"(?:final\s+score|score)[:\s*]+(\d+)(?:[/-](\d+))?", response, re.IGNORECASE)
            if m:
                try:
                    score = int(m.group(1))
                    score = max(0, min(10, score))
                except (ValueError, TypeError):
                    score = 0

        return {"score": score, "keywords": keywords, "reasoning": reasoning}


def score_job(resume_text: str, job: dict) -> dict:
    """Score a single job against the resume.

    Args:
        resume_text: The candidate's full resume text.
        job: Job dict with keys: title, site, location, full_description.

    Returns:
        {"score": int, "keywords": str, "reasoning": str}
    """
    title = str(job.get("title") or "Unknown")
    site = str(job.get("site") or "Unknown")
    location = str(job.get("location") or "N/A")
    description = str(job.get("full_description") or "")[:6000]

    job_text = (
        f"TITLE: {title}\n"
        f"COMPANY: {site}\n"
        f"LOCATION: {location}\n\n"
        f"DESCRIPTION:\n{description}"
    )

    messages = [
        {"role": "system", "content": SCORE_PROMPT},
        {"role": "user", "content": f"RESUME:\n{resume_text}\n\n---\n\nJOB POSTING:\n{job_text}"},
    ]

    try:
        client = get_score_client()
        response = client.chat(messages, max_tokens=1024, temperature=0.2)
        return _parse_score_response(response)
    except Exception as e:
        log.error("LLM error scoring job '%s': %s", job.get("title", "?"), e)
        return {"score": 0, "keywords": "", "reasoning": f"LLM error: {e}"}


def run_scoring(limit: int = 0, rescore: bool = False) -> dict:
    """Score unscored jobs that have full descriptions.

    Args:
        limit: Maximum number of jobs to score in this run.
        rescore: If True, re-score all jobs (not just unscored ones).

    Returns:
        {"scored": int, "errors": int, "elapsed": float, "distribution": list}
    """
    resume_text = RESUME_PATH.read_text(encoding="utf-8")
    conn = get_connection()

    if rescore:
        query = "SELECT * FROM jobs WHERE full_description IS NOT NULL"
        if limit > 0:
            query += f" LIMIT {limit}"
        jobs = conn.execute(query).fetchall()
    else:
        jobs = get_jobs_by_stage(conn=conn, stage="pending_score", limit=limit)

    if not jobs:
        log.info("No unscored jobs with descriptions found.")
        return {"scored": 0, "errors": 0, "elapsed": 0.0, "distribution": []}

    # Convert sqlite3.Row to dicts if needed
    if jobs and not isinstance(jobs[0], dict):
        columns = jobs[0].keys()
        jobs = [dict(zip(columns, row)) for row in jobs]

    # Parallel workers: default 5, override via HIREAGENT_SCORE_WORKERS env var.
    # Throttled/local-LLM setups should set HIREAGENT_SCORE_WORKERS=1.
    score_workers = int(os.environ.get("HIREAGENT_SCORE_WORKERS", "5") or 5)
    throttle = float(os.environ.get("HIREAGENT_LLM_SLEEP_SECONDS", "0") or 0)
    if throttle > 0:
        score_workers = 1  # honour throttle: serial mode only

    log.info("Scoring %d jobs (%d parallel workers)...", len(jobs), score_workers)
    t0 = time.time()
    errors = 0
    results: list[dict] = []

    from hireagent.eligibility import classify_job_eligibility, classify_job_data_quality
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    skipped = 0
    _lock = threading.Lock()
    _completed = 0

    def _score_one(job: dict) -> dict | None:
        nonlocal skipped, _completed
        title = str(job.get("title") or "?")[:60]
        _, _ = classify_job_data_quality(job)
        eligibility = classify_job_eligibility(job)
        if not eligibility["final_eligible"]:
            reason = ";".join(eligibility.get("reasons", ["ineligible"]))
            with _lock:
                skipped += 1
                _completed += 1
                log.info("[%d/%d] score=0 (skipped-ineligible: %s)  %s",
                         _completed, len(jobs), reason[:40], title)
            return {"url": job["url"], "score": 0,
                    "keywords": "", "reasoning": f"skipped:{reason}", "_ineligible": True}
        result = score_job(resume_text, job)
        result["url"] = job["url"]
        with _lock:
            _completed += 1
            log.info("[%d/%d] score=%d  %s", _completed, len(jobs), result["score"], title)
        return result

    now = datetime.now(timezone.utc).isoformat()
    _COMMIT_BATCH = 20  # write to DB every N results so progress survives kills

    with ThreadPoolExecutor(max_workers=score_workers) as pool:
        futures = {pool.submit(_score_one, job): job for job in jobs}
        for future in as_completed(futures):
            try:
                r = future.result()
                if r:
                    results.append(r)
                    if r["score"] == 0 and not r.get("_ineligible"):
                        errors += 1
                    # Incremental commit every COMMIT_BATCH results
                    if len(results) % _COMMIT_BATCH == 0:
                        for _r in results[-_COMMIT_BATCH:]:
                            conn.execute(
                                "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
                                (_r["score"], f"{_r['keywords']}\n{_r['reasoning']}", now, _r["url"]),
                            )
                        conn.commit()
            except Exception as exc:
                log.error("Score worker error: %s", exc)
                errors += 1

    # Final commit for any remaining results not yet flushed
    remainder = results[-(len(results) % _COMMIT_BATCH):] if len(results) % _COMMIT_BATCH else []
    for r in remainder:
        conn.execute(
            "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
            (r["score"], f"{r['keywords']}\n{r['reasoning']}", now, r["url"]),
        )
    if remainder:
        conn.commit()

    elapsed = time.time() - t0
    scored_count = sum(1 for r in results if not r.get("_ineligible"))
    log.info("Done: %d scored, %d skipped (ineligible) in %.1fs", scored_count, skipped, elapsed)

    # Score distribution
    dist = conn.execute("""
        SELECT fit_score, COUNT(*) FROM jobs
        WHERE fit_score IS NOT NULL
        GROUP BY fit_score ORDER BY fit_score DESC
    """).fetchall()
    distribution = [(row[0], row[1]) for row in dist]

    return {
        "scored": scored_count,
        "errors": errors,
        "elapsed": elapsed,
        "distribution": distribution,
    }
