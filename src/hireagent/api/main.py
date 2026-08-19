"""HireAgent FastAPI Backend.

Serves job data, resume versions, and version assignment to the React dashboard.
Mounts the compiled dashboard from dashboard/dist if available.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

log = logging.getLogger(__name__)

# ── Scan state (persisted to ~/.hireagent/scan_state.json) ──────────────────

_SCAN_STATE_PATH = Path.home() / ".hireagent" / "scan_state.json"
_SCAN_COOLDOWN_HOURS = 6  # minimum hours between scans

def _load_scan_state() -> dict:
    try:
        if _SCAN_STATE_PATH.exists():
            return json.loads(_SCAN_STATE_PATH.read_text())
    except Exception:
        pass
    return {"last_scan_at": None, "scanning": False, "stages": []}

def _save_scan_state(state: dict):
    _SCAN_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SCAN_STATE_PATH.write_text(json.dumps(state, indent=2))

def _seconds_until_next_scan() -> float:
    state = _load_scan_state()
    if not state.get("last_scan_at"):
        return 0
    last = datetime.fromisoformat(state["last_scan_at"])
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    next_allowed = last + timedelta(hours=_SCAN_COOLDOWN_HOURS)
    remaining = (next_allowed - datetime.now(timezone.utc)).total_seconds()
    return max(0, remaining)

app = FastAPI(title="HireAgent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Bootstrap on startup ──────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    from hireagent.config import load_env, ensure_dirs
    from hireagent.database import init_db
    load_env()
    ensure_dirs()
    init_db()


# ── Models ────────────────────────────────────────────────────────────────────

class ApplyPayload(BaseModel):
    notes: str = ""


class VersionAssignPayload(BaseModel):
    force_new: bool = False


# ── Jobs endpoints ────────────────────────────────────────────────────────────

@app.get("/api/jobs")
def get_jobs(
    min_score: int = 0,
    status: str = "",
    limit: int = 200,
    offset: int = 0,
):
    """List all jobs with scoring, version, and apply status."""
    from hireagent.database import get_connection

    conn = get_connection()
    wheres = []
    params: list[Any] = []

    if min_score > 0:
        wheres.append("j.fit_score >= ?")
        params.append(min_score)

    if status == "applied":
        wheres.append("j.apply_status = 'applied'")
    elif status == "pending":
        wheres.append("(j.apply_status IS NULL OR j.apply_status NOT IN ('applied'))")
    elif status == "ready":
        wheres.append("j.tailored_resume_path IS NOT NULL AND j.apply_status IS NULL")

    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    rows = conn.execute(f"""
        SELECT j.url, j.title, j.company, j.salary, j.location, j.site,
               j.application_url, j.fit_score, j.score_reasoning,
               j.tailored_resume_path, j.applied_at, j.apply_status,
               j.resume_version_id, j.version_ats_score,
               j.discovered_at, j.full_description
        FROM jobs j
        {where_sql}
        ORDER BY j.fit_score DESC NULLS LAST, j.title
        LIMIT ? OFFSET ?
    """, params + [limit, offset]).fetchall()

    cols = [
        "url", "title", "company", "salary", "location", "site", "application_url",
        "fit_score", "score_reasoning", "tailored_resume_path",
        "applied_at", "apply_status", "resume_version_id", "version_ats_score",
        "discovered_at", "full_description",
    ]
    jobs = []
    for r in rows:
        j = dict(zip(cols, r))
        # Shorten description for list view
        j["description_preview"] = (j["full_description"] or "")[:300]
        del j["full_description"]
        jobs.append(j)

    total = conn.execute(
        f"SELECT COUNT(*) FROM jobs j {where_sql}", params
    ).fetchone()[0]

    return {"jobs": jobs, "total": total, "offset": offset, "limit": limit}


@app.get("/api/job")
def get_job(url: str):
    """Get a single job with full description. Uses ?url= query param to avoid encoding issues."""
    from hireagent.database import get_connection

    conn = get_connection()
    row = conn.execute("""
        SELECT url, title, company, salary, location, site, application_url,
               fit_score, score_reasoning, tailored_resume_path,
               applied_at, apply_status, resume_version_id, version_ats_score,
               discovered_at, full_description
        FROM jobs WHERE url = ?
    """, (url,)).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    cols = [
        "url", "title", "company", "salary", "location", "site", "application_url",
        "fit_score", "score_reasoning", "tailored_resume_path",
        "applied_at", "apply_status", "resume_version_id", "version_ats_score",
        "discovered_at", "full_description",
    ]
    return dict(zip(cols, row))


@app.post("/api/job/apply")
def mark_applied(url: str, payload: ApplyPayload = ApplyPayload()):
    """Mark a job as applied. Uses ?url= query param."""
    from hireagent.database import get_connection
    from datetime import datetime, timezone

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE jobs SET apply_status='applied', applied_at=? WHERE url=?",
        (now, url)
    )
    conn.commit()
    return {"ok": True, "applied_at": now}


@app.post("/api/job/unapply")
def mark_unapplied(url: str):
    """Undo an applied mark. Uses ?url= query param."""
    from hireagent.database import get_connection

    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET apply_status=NULL, applied_at=NULL WHERE url=?",
        (url,)
    )
    conn.commit()
    return {"ok": True}


# ── Resume file serving ───────────────────────────────────────────────────────

@app.get("/api/job/resume")
def get_job_resume_by_url(url: str):
    """Stream the tailored resume PDF for a job. Uses ?url= query param."""
    from hireagent.database import get_connection

    conn = get_connection()
    row = conn.execute(
        "SELECT tailored_resume_path, title FROM jobs WHERE url = ?", (url,)
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if not row[0]:
        raise HTTPException(status_code=404, detail="No tailored resume for this job")

    path = Path(row[0])
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Resume file missing: {path.name}")

    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in (row[1] or "Resume"))[:40]
    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=f"{safe_title}_Resume.pdf",
    )


@app.get("/api/resume/{version_id}/pdf")
def get_resume_pdf(version_id: str):
    """Stream the PDF for a given version."""
    from hireagent.database import get_connection

    conn = get_connection()
    row = conn.execute(
        "SELECT resume_pdf_path FROM resume_versions WHERE version_id = ?",
        (version_id,)
    ).fetchone()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Version PDF not found")

    path = Path(row[0])
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"PDF file missing: {path}")

    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=f"Resume_Version_{version_id}.pdf",
    )


@app.get("/api/jobs/{job_url:path}/resume")
def get_job_resume(job_url: str):
    """Stream the tailored resume PDF for a specific job."""
    from hireagent.database import get_connection

    conn = get_connection()
    row = conn.execute(
        "SELECT tailored_resume_path FROM jobs WHERE url = ?", (job_url,)
    ).fetchone()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No resume for this job")

    path = Path(row[0])
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Resume file missing: {path}")

    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename="Resume.pdf",
    )


# ── Versions endpoints ────────────────────────────────────────────────────────

@app.get("/api/versions")
def get_versions():
    """List all resume versions with their covered jobs."""
    from hireagent.version_manager import list_versions
    return {"versions": list_versions()}


@app.post("/api/versions/assign")
def assign_versions(payload: VersionAssignPayload, background_tasks: BackgroundTasks):
    """Kick off background version assignment for all unversioned tailored jobs."""
    background_tasks.add_task(_run_versioning_bg, payload.force_new)
    return {"ok": True, "message": "Version assignment started in background"}


def _run_versioning_bg(force_new: bool):
    try:
        from hireagent.version_manager import run_versioning
        run_versioning(force_new=force_new)
    except Exception as e:
        log.error("Background versioning error: %s", e)


# ── Stats endpoint ────────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    """Return pipeline statistics for the dashboard header."""
    from hireagent.database import get_connection

    conn = get_connection()

    def scalar(q, *p):
        return conn.execute(q, p).fetchone()[0] or 0

    total       = scalar("SELECT COUNT(*) FROM jobs")
    scored      = scalar("SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL")
    high_fit    = scalar("SELECT COUNT(*) FROM jobs WHERE fit_score >= 7")
    tailored    = scalar("SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL")
    applied     = scalar("SELECT COUNT(*) FROM jobs WHERE apply_status = 'applied'")
    pending     = scalar(
        "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL "
        "AND (apply_status IS NULL OR apply_status != 'applied')"
    )
    versioned   = scalar("SELECT COUNT(*) FROM resume_versions")

    score_dist_rows = conn.execute("""
        SELECT fit_score, COUNT(*) FROM jobs
        WHERE fit_score IS NOT NULL
        GROUP BY fit_score ORDER BY fit_score DESC
    """).fetchall()

    # Jobs per week (last 4 weeks)
    weekly = conn.execute("""
        SELECT strftime('%Y-W%W', discovered_at) as week, COUNT(*)
        FROM jobs WHERE discovered_at IS NOT NULL
        GROUP BY week ORDER BY week DESC LIMIT 8
    """).fetchall()

    return {
        "total": total,
        "scored": scored,
        "high_fit": high_fit,
        "tailored": tailored,
        "applied": applied,
        "pending": pending,
        "versions": versioned,
        "score_distribution": [{"score": r[0], "count": r[1]} for r in score_dist_rows],
        "weekly_discovery": [{"week": r[0], "count": r[1]} for r in reversed(weekly)],
    }


# ── Re-classify ineligible jobs (zero out bad scores) ────────────────────────

@app.post("/api/jobs/reclassify")
def reclassify_eligibility():
    """Re-run eligibility on all scored jobs and zero out ineligible ones."""
    from hireagent.database import get_connection
    from hireagent.eligibility import classify_job_eligibility

    conn = get_connection()
    rows = conn.execute(
        "SELECT url, title, site, location, full_description, fit_score FROM jobs "
        "WHERE fit_score > 0"
    ).fetchall()
    cols = ["url", "title", "site", "location", "full_description", "fit_score"]
    zeroed = []

    for r in rows:
        job = dict(zip(cols, r))
        el = classify_job_eligibility(job)
        if not el["final_eligible"]:
            reasons = ";".join(el.get("reasons", []))
            conn.execute(
                "UPDATE jobs SET fit_score=0, eligibility_reason=? WHERE url=?",
                (reasons, job["url"])
            )
            zeroed.append({"title": job["title"], "reason": reasons})

    conn.commit()
    return {"zeroed": len(zeroed), "jobs": zeroed[:20]}


# ── Scan status & trigger ─────────────────────────────────────────────────────

@app.get("/api/scan/status")
def get_scan_status():
    """Return current scan state: last scan, next allowed scan, active stages."""
    state = _load_scan_state()
    remaining = _seconds_until_next_scan()
    return {
        "scanning": state.get("scanning", False),
        "last_scan_at": state.get("last_scan_at"),
        "cooldown_hours": _SCAN_COOLDOWN_HOURS,
        "seconds_until_next": remaining,
        "can_scan": remaining <= 0 and not state.get("scanning", False),
        "stages": state.get("stages", []),
    }

@app.post("/api/scan/run")
def trigger_scan(background_tasks: BackgroundTasks):
    """Trigger a full discover → score → tailor pipeline scan (once per 6 hours)."""
    remaining = _seconds_until_next_scan()
    state = _load_scan_state()
    if state.get("scanning"):
        raise HTTPException(status_code=409, detail="Scan already in progress")
    if remaining > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Cooldown active — next scan in {int(remaining // 3600)}h {int((remaining % 3600) // 60)}m"
        )
    background_tasks.add_task(_run_full_scan_bg)
    return {"ok": True, "message": "Scan started"}

def _run_full_scan_bg():
    """Run discover → score → tailor, recording timing per stage."""
    stages_order = ["discover", "score", "tailor"]
    state = _load_scan_state()
    state["scanning"] = True
    state["last_scan_at"] = datetime.now(timezone.utc).isoformat()
    state["stages"] = []
    _save_scan_state(state)

    from hireagent.pipeline import run_pipeline
    from hireagent.database import get_connection

    for stage in stages_order:
        entry = {"name": stage, "status": "running", "started_at": datetime.now(timezone.utc).isoformat()}
        state["stages"].append(entry)
        _save_scan_state(state)
        t0 = time.time()
        try:
            run_pipeline(stages=[stage])
            duration = round(time.time() - t0)
            # Count what was produced
            conn = get_connection()
            if stage == "discover":
                count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                note = f"{count} total jobs"
            elif stage == "score":
                count = conn.execute("SELECT COUNT(*) FROM jobs WHERE fit_score >= 7").fetchone()[0]
                note = f"{count} high-fit jobs"
            elif stage == "tailor":
                count = conn.execute("SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL").fetchone()[0]
                note = f"{count} resumes tailored"
            else:
                count = 0
                note = ""
            entry.update({"status": "done", "finished_at": datetime.now(timezone.utc).isoformat(),
                           "duration_s": duration, "count": count, "note": note})
        except Exception as e:
            duration = round(time.time() - t0)
            log.error("Scan stage %s failed: %s", stage, e)
            entry.update({"status": "error", "finished_at": datetime.now(timezone.utc).isoformat(),
                           "duration_s": duration, "error": str(e)})
        _save_scan_state(state)

    state["scanning"] = False
    _save_scan_state(state)
    log.info("Full scan complete")


# ── Pipeline trigger endpoints ────────────────────────────────────────────────

@app.post("/api/pipeline/run")
def run_pipeline_stage(stage: str, background_tasks: BackgroundTasks):
    """Trigger a pipeline stage in the background."""
    valid = {"discover", "enrich", "score", "tailor", "version"}
    if stage not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown stage: {stage}")
    background_tasks.add_task(_run_stage_bg, stage)
    return {"ok": True, "stage": stage, "message": f"{stage} started"}


def _run_stage_bg(stage: str):
    try:
        if stage == "version":
            from hireagent.version_manager import run_versioning
            run_versioning()
        else:
            from hireagent.pipeline import run_pipeline
            run_pipeline(stages=[stage])
    except Exception as e:
        log.error("Pipeline stage %s error: %s", stage, e)


# ── Serve React dashboard (production build) ──────────────────────────────────

_DIST = Path(__file__).parent.parent.parent.parent / "dashboard" / "dist"

if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

@app.get("/", include_in_schema=False)
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str = ""):
    index = _DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"error": "Frontend not built. Run: cd dashboard && npm run build"}
