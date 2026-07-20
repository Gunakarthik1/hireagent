"""HireAgent HTML Dashboard Generator.

Generates a self-contained HTML dashboard with:
  - Summary stats (total, enriched, scored, high-fit)
  - Score distribution bar chart
  - Jobs-by-source breakdown
  - Filterable job cards grouped by score
  - Client-side search and score filtering
"""

from __future__ import annotations

import os
import webbrowser
from html import escape
from pathlib import Path

from rich.console import Console

from hireagent.config import APP_DIR, DB_PATH
from hireagent.database import get_connection

console = Console()


def generate_dashboard(output_path: str | None = None) -> str:
    """Generate an HTML dashboard of all jobs with fit scores.

    Args:
        output_path: Where to write the HTML file. Defaults to ~/.hireagent/dashboard.html.

    Returns:
        Absolute path to the generated HTML file.
    """
    out = Path(output_path) if output_path else APP_DIR / "dashboard.html"

    conn = get_connection()

    # Stats
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    ready = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE full_description IS NOT NULL AND application_url IS NOT NULL"
    ).fetchone()[0]
    scored = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL"
    ).fetchone()[0]
    high_fit = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score >= 7"
    ).fetchone()[0]

    # Score distribution
    score_dist: dict[int, int] = {}
    if scored:
        rows = conn.execute(
            "SELECT fit_score, COUNT(*) FROM jobs "
            "WHERE fit_score IS NOT NULL "
            "GROUP BY fit_score ORDER BY fit_score DESC"
        ).fetchall()
        for r in rows:
            score_dist[r[0]] = r[1]

    # Site stats
    site_stats = conn.execute("""
        SELECT site,
               COUNT(*) as total,
               SUM(CASE WHEN fit_score >= 7 THEN 1 ELSE 0 END) as high_fit,
               SUM(CASE WHEN fit_score BETWEEN 5 AND 6 THEN 1 ELSE 0 END) as mid_fit,
               SUM(CASE WHEN fit_score < 5 AND fit_score IS NOT NULL THEN 1 ELSE 0 END) as low_fit,
               SUM(CASE WHEN fit_score IS NULL THEN 1 ELSE 0 END) as unscored,
               ROUND(AVG(fit_score), 1) as avg_score
        FROM jobs GROUP BY site ORDER BY high_fit DESC, total DESC
    """).fetchall()

    # All scored jobs (5+), ordered by score desc
    jobs = conn.execute("""
        SELECT url, title, salary, description, location, site, strategy,
               full_description, application_url, detail_error,
               fit_score, score_reasoning
        FROM jobs
        WHERE fit_score >= 5
        ORDER BY fit_score DESC, site, title
    """).fetchall()

    # Color map per site
    colors = {
        "RemoteOK": "#10b981", "WelcomeToTheJungle": "#f59e0b",
        "Job Bank Canada": "#3b82f6", "CareerJet Canada": "#8b5cf6",
        "Hacker News Jobs": "#ff6600", "BuiltIn Remote": "#ec4899",
        "TD Bank": "#00a651", "CIBC": "#c41f3e", "RBC": "#003168",
        "indeed": "#2164f3", "linkedin": "#0a66c2",
        "Dice": "#eb1c26", "Glassdoor": "#0caa41",
    }

    # Score distribution bar chart
    score_bars = ""
    max_count = max(score_dist.values()) if score_dist else 1
    for s in range(10, 0, -1):
        count = score_dist.get(s, 0)
        pct = (count / max_count * 100) if max_count else 0
        score_color = "#10b981" if s >= 7 else ("#f59e0b" if s >= 5 else "#ef4444")
        score_bars += f"""
        <div class="score-row">
          <span class="score-label">{s}</span>
          <div class="score-bar-track">
            <div class="score-bar-fill" style="width:{pct}%;background:{score_color}"></div>
          </div>
          <span class="score-count">{count}</span>
        </div>"""

    # Site stats rows
    site_rows = ""
    for s in site_stats:
        site = s["site"] or "?"
        color = colors.get(site, "#6b7280")
        avg = s["avg_score"] or 0
        site_rows += f"""
        <div class="site-row">
          <div class="site-name" style="color:{color}">{escape(site)}</div>
          <div class="site-nums">{s['total']} jobs &middot; {s['high_fit']} strong fit &middot; avg score {avg}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:{s['high_fit']/max(s['total'],1)*100}%;background:{color}"></div>
            <div class="bar-fill" style="width:{s['mid_fit']/max(s['total'],1)*100}%;background:{color}66"></div>
          </div>
        </div>"""

    # Job cards grouped by score
    job_sections = ""
    current_score = None
    for j in jobs:
        score = j["fit_score"] or 0
        if score != current_score:
            if current_score is not None:
                job_sections += "</div>"
            score_color = "#10b981" if score >= 7 else "#f59e0b"
            score_label = {
                10: "Perfect Match", 9: "Excellent Fit", 8: "Strong Fit",
                7: "Good Fit", 6: "Moderate+", 5: "Moderate",
            }.get(score, f"Score {score}")
            count_at_score = score_dist.get(score, 0)
            job_sections += f"""
            <h2 class="score-header" style="border-color:{score_color}">
              <span class="score-badge" style="background:{score_color}">{score}</span>
              {score_label} ({count_at_score} jobs)
            </h2>
            <div class="job-grid">"""
            current_score = score

        title = escape(j["title"] or "Untitled")
        url = escape(j["url"] or "")
        salary = escape(j["salary"] or "")
        location = escape(j["location"] or "")
        site = escape(j["site"] or "")
        site_color = colors.get(j["site"] or "", "#6b7280")
        apply_url = escape(j["application_url"] or "")

        # Parse keywords and reasoning from score_reasoning
        reasoning_raw = j["score_reasoning"] or ""
        reasoning_lines = reasoning_raw.split("\n")
        keywords = reasoning_lines[0][:120] if reasoning_lines else ""
        reasoning = reasoning_lines[1][:200] if len(reasoning_lines) > 1 else ""

        desc_preview = escape(j["full_description"] or "")[:300]
        full_desc_html = escape(j["full_description"] or "").replace("\n", "<br>")
        desc_len = len(j["full_description"] or "")

        meta_parts = []
        meta_parts.append(
            f'<span class="meta-tag site-tag" style="background:{site_color}33;color:{site_color}">{site}</span>'
        )
        if salary:
            meta_parts.append(f'<span class="meta-tag salary">{salary}</span>')
        if location:
            meta_parts.append(f'<span class="meta-tag location">{location[:40]}</span>')
        meta_html = " ".join(meta_parts)

        apply_html = ""
        if apply_url:
            apply_html = f'<a href="{apply_url}" class="apply-link" target="_blank">Apply</a>'

        job_sections += f"""
        <div class="job-card" data-score="{score}" data-site="{escape(j['site'] or '')}" data-location="{location.lower()}">
          <div class="card-header">
            <span class="score-pill" style="background:{'#10b981' if score >= 7 else '#f59e0b'}">{score}</span>
            <a href="{url}" class="job-title" target="_blank">{title}</a>
          </div>
          <div class="meta-row">{meta_html}</div>
          {f'<div class="keywords-row">{escape(keywords)}</div>' if keywords else ''}
          {f'<div class="reasoning-row">{escape(reasoning)}</div>' if reasoning else ''}
          <p class="desc-preview">{desc_preview}...</p>
          {"<details class='full-desc-details'><summary class='expand-btn'>Full Description (" + f'{desc_len:,}' + " chars)</summary><div class='full-desc'>" + full_desc_html + "</div></details>" if j["full_description"] else ""}
          <div class="card-footer">{apply_html}</div>
        </div>"""

    if current_score is not None:
        job_sections += "</div>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HireAgent Dashboard</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}

  h1 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 0.5rem; }}
  .subtitle {{ color: #94a3b8; margin-bottom: 2rem; }}

  /* Summary cards */
  .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2.5rem; }}
  .stat-card {{ background: #1e293b; border-radius: 12px; padding: 1.25rem; }}
  .stat-num {{ font-size: 2rem; font-weight: 700; }}
  .stat-label {{ color: #94a3b8; font-size: 0.85rem; margin-top: 0.25rem; }}
  .stat-ok .stat-num {{ color: #10b981; }}
  .stat-scored .stat-num {{ color: #60a5fa; }}
  .stat-high .stat-num {{ color: #f59e0b; }}
  .stat-total .stat-num {{ color: #e2e8f0; }}

  /* Filters */
  .filters {{ background: #1e293b; border-radius: 12px; padding: 1.25rem; margin-bottom: 2rem; display: flex; gap: 1rem; flex-wrap: wrap; align-items: center; }}
  .filter-label {{ color: #94a3b8; font-size: 0.85rem; font-weight: 600; }}
  .filter-btn {{ background: #334155; border: none; color: #94a3b8; padding: 0.4rem 0.8rem; border-radius: 6px; cursor: pointer; font-size: 0.8rem; transition: all 0.15s; }}
  .filter-btn:hover {{ background: #475569; color: #e2e8f0; }}
  .filter-btn.active {{ background: #60a5fa; color: #0f172a; font-weight: 600; }}
  .search-input {{ background: #334155; border: 1px solid #475569; color: #e2e8f0; padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.8rem; width: 200px; }}
  .search-input::placeholder {{ color: #64748b; }}

  /* Score distribution */
  .score-section {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2.5rem; }}
  .score-dist {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; }}
  .score-dist h3 {{ font-size: 1rem; margin-bottom: 1rem; color: #94a3b8; }}
  .score-row {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem; }}
  .score-label {{ width: 1.5rem; text-align: right; font-size: 0.85rem; font-weight: 600; }}
  .score-bar-track {{ flex: 1; height: 14px; background: #334155; border-radius: 4px; overflow: hidden; }}
  .score-bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}
  .score-count {{ width: 2.5rem; font-size: 0.8rem; color: #94a3b8; }}

  /* Site bars */
  .sites-section {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; }}
  .sites-section h3 {{ font-size: 1rem; margin-bottom: 1rem; color: #94a3b8; }}
  .site-row {{ margin-bottom: 0.8rem; }}
  .site-name {{ font-weight: 600; font-size: 0.9rem; }}
  .site-nums {{ color: #94a3b8; font-size: 0.75rem; margin: 0.15rem 0; }}
  .bar-track {{ height: 8px; background: #334155; border-radius: 4px; display: flex; overflow: hidden; }}
  .bar-fill {{ height: 100%; transition: width 0.3s; }}

  /* Score group headers */
  .score-header {{ font-size: 1.2rem; font-weight: 600; margin: 2.5rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 3px solid; display: flex; align-items: center; gap: 0.75rem; }}
  .score-badge {{ display: inline-flex; align-items: center; justify-content: center; width: 2rem; height: 2rem; border-radius: 8px; color: #0f172a; font-weight: 700; font-size: 1rem; }}

  /* Job grid */
  .job-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 1rem; }}

  .job-card {{ background: #1e293b; border-radius: 10px; padding: 1rem; border-left: 3px solid #334155; transition: all 0.15s; }}
  .job-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px #00000044; }}
  .job-card[data-score="9"], .job-card[data-score="10"] {{ border-left-color: #10b981; }}
  .job-card[data-score="8"] {{ border-left-color: #34d399; }}
  .job-card[data-score="7"] {{ border-left-color: #60a5fa; }}
  .job-card[data-score="6"] {{ border-left-color: #f59e0b; }}
  .job-card[data-score="5"] {{ border-left-color: #f59e0b88; }}

  .card-header {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }}
  .score-pill {{ display: inline-flex; align-items: center; justify-content: center; min-width: 1.6rem; height: 1.6rem; border-radius: 6px; color: #0f172a; font-weight: 700; font-size: 0.8rem; flex-shrink: 0; }}

  .job-title {{ color: #e2e8f0; text-decoration: none; font-weight: 600; font-size: 0.95rem; }}
  .job-title:hover {{ color: #60a5fa; }}

  .meta-row {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.4rem; }}
  .meta-tag {{ font-size: 0.72rem; padding: 0.15rem 0.5rem; border-radius: 4px; background: #334155; color: #94a3b8; }}
  .meta-tag.salary {{ background: #064e3b; color: #6ee7b7; }}
  .meta-tag.location {{ background: #1e3a5f; color: #93c5fd; }}

  .keywords-row {{ font-size: 0.75rem; color: #10b981; margin-bottom: 0.3rem; line-height: 1.4; }}
  .reasoning-row {{ font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.5rem; font-style: italic; line-height: 1.4; }}

  .desc-preview {{ font-size: 0.8rem; color: #64748b; line-height: 1.5; margin-bottom: 0.75rem; max-height: 3.6em; overflow: hidden; }}

  .card-footer {{ display: flex; justify-content: flex-end; }}
  .apply-link {{ font-size: 0.8rem; color: #60a5fa; text-decoration: none; padding: 0.3rem 0.8rem; border: 1px solid #60a5fa33; border-radius: 6px; font-weight: 500; }}
  .apply-link:hover {{ background: #60a5fa22; }}

  /* Expandable full description */
  .full-desc-details {{ margin-bottom: 0.75rem; }}
  .expand-btn {{ font-size: 0.8rem; color: #60a5fa; cursor: pointer; list-style: none; padding: 0.3rem 0; }}
  .expand-btn::-webkit-details-marker {{ display: none; }}
  .expand-btn:hover {{ color: #93c5fd; }}
  .full-desc {{ font-size: 0.8rem; color: #cbd5e1; line-height: 1.6; margin-top: 0.5rem; padding: 0.75rem; background: #0f172a; border-radius: 8px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }}

  .hidden {{ display: none !important; }}
  .job-count {{ color: #94a3b8; font-size: 0.85rem; margin-bottom: 1rem; }}

  @media (max-width: 768px) {{
    .summary {{ grid-template-columns: repeat(2, 1fr); }}
    .score-section {{ grid-template-columns: 1fr; }}
    .job-grid {{ grid-template-columns: 1fr; }}
    body {{ padding: 1rem; }}
  }}
</style>
</head>
<body>

<h1>HireAgent Dashboard</h1>
<p class="subtitle">{total} jobs &middot; {scored} scored &middot; {high_fit} strong matches (7+)</p>

<div class="summary">
  <div class="stat-card stat-total"><div class="stat-num">{total}</div><div class="stat-label">Total Jobs</div></div>
  <div class="stat-card stat-ok"><div class="stat-num">{ready}</div><div class="stat-label">Ready (desc + URL)</div></div>
  <div class="stat-card stat-scored"><div class="stat-num">{scored}</div><div class="stat-label">Scored by LLM</div></div>
  <div class="stat-card stat-high"><div class="stat-num">{high_fit}</div><div class="stat-label">Strong Fit (7+)</div></div>
</div>

<div class="filters">
  <span class="filter-label">Score:</span>
  <button class="filter-btn active" onclick="filterScore(0)">All 5+</button>
  <button class="filter-btn" onclick="filterScore(7)">7+ Strong</button>
  <button class="filter-btn" onclick="filterScore(8)">8+ Excellent</button>
  <button class="filter-btn" onclick="filterScore(9)">9+ Perfect</button>
  <span class="filter-label" style="margin-left:1rem">Search:</span>
  <input type="text" class="search-input" placeholder="Filter by title, site..." oninput="filterText(this.value)">
</div>

<div class="score-section">
  <div class="score-dist">
    <h3>Score Distribution</h3>
    {score_bars}
  </div>
  <div class="sites-section">
    <h3>By Source</h3>
    {site_rows}
  </div>
</div>

<div id="job-count" class="job-count"></div>

{job_sections}

<script>
let minScore = 0;
let searchText = '';

function filterScore(min) {{
  minScore = min;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  applyFilters();
}}

function filterText(text) {{
  searchText = text.toLowerCase();
  applyFilters();
}}

function applyFilters() {{
  let shown = 0;
  let total = 0;
  document.querySelectorAll('.job-card').forEach(card => {{
    total++;
    const score = parseInt(card.dataset.score) || 0;
    const text = card.textContent.toLowerCase();
    const scoreMatch = score >= (minScore || 5);
    const textMatch = !searchText || text.includes(searchText);
    if (scoreMatch && textMatch) {{
      card.classList.remove('hidden');
      shown++;
    }} else {{
      card.classList.add('hidden');
    }}
  }});
  document.getElementById('job-count').textContent = `Showing ${{shown}} of ${{total}} jobs`;

  // Hide empty score groups
  document.querySelectorAll('.score-header').forEach(header => {{
    const grid = header.nextElementSibling;
    if (grid && grid.classList.contains('job-grid')) {{
      const visible = grid.querySelectorAll('.job-card:not(.hidden)').length;
      header.style.display = visible ? '' : 'none';
      grid.style.display = visible ? '' : 'none';
    }}
  }});
}}

applyFilters();
</script>

</body>
</html>"""

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    abs_path = str(out.resolve())
    console.print(f"[green]Dashboard written to {abs_path}[/green]")
    return abs_path


def open_dashboard(output_path: str | None = None) -> None:
    """Generate the dashboard and open it in the default browser.

    Args:
        output_path: Where to write the HTML file. Defaults to ~/.hireagent/dashboard.html.
    """
    path = generate_dashboard(output_path)
    console.print("[dim]Opening in browser...[/dim]")
    webbrowser.open(f"file:///{path}")


# ── Apply Queue Report ────────────────────────────────────────────────────────

def generate_report(
    output_path: str | None = None,
    min_score: int = 7,
    limit: int = 0,
) -> str:
    """Generate a focused apply-queue HTML report of top-scoring jobs.

    Args:
        output_path: Where to write the HTML file. Defaults to ~/.hireagent/report.html.
        min_score: Minimum fit score to include (default 7).
        limit: Max jobs to include (0 = all).

    Returns:
        Absolute path to the generated HTML file.
    """
    from html import escape

    out = Path(output_path) if output_path else APP_DIR / "report.html"
    conn = get_connection()

    query = f"""
        SELECT url, title, salary, location, site,
               full_description, application_url,
               fit_score, score_reasoning,
               tailored_resume_path, apply_status
        FROM jobs
        WHERE fit_score >= {min_score}
          AND application_url IS NOT NULL
          AND (apply_status IS NULL OR apply_status NOT IN ('applied', 'skipped'))
        ORDER BY fit_score DESC, title
        {"LIMIT " + str(limit) if limit > 0 else ""}
    """
    rows = conn.execute(query).fetchall()
    columns = [d[0] for d in conn.execute(query).description] if rows else []

    # Normalise to dicts
    if rows and not isinstance(rows[0], dict):
        cols = [d[0] for d in conn.execute(
            "SELECT url, title, salary, location, site, full_description, "
            "application_url, fit_score, score_reasoning, tailored_resume_path, apply_status "
            "FROM jobs LIMIT 0"
        ).description]
        rows = [dict(zip(cols, r)) for r in rows]

    total_applied = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status='applied'"
    ).fetchone()[0]
    total_ready = len(rows)

    # Build job rows HTML
    job_rows_html = ""
    for i, j in enumerate(rows, 1):
        score = j.get("fit_score") or 0
        title = escape(j.get("title") or "Untitled")
        site  = escape(j.get("site") or "")
        loc   = escape(j.get("location") or "")
        sal   = escape(j.get("salary") or "")
        apply_url = escape(j.get("application_url") or "")
        job_url   = escape(j.get("url") or "")
        reasoning = escape((j.get("score_reasoning") or "").split("\n")[-1][:300])
        resume_path = j.get("tailored_resume_path") or ""
        has_resume  = bool(resume_path) and Path(resume_path).exists()

        score_color = (
            "#4ade80" if score >= 9 else
            "#34d399" if score >= 8 else
            "#60a5fa" if score >= 7 else
            "#f59e0b"
        )

        resume_btn = ""
        if has_resume:
            resume_btn = f'<a class="btn btn-resume" href="file://{escape(resume_path)}" target="_blank">📄 Resume</a>'

        job_rows_html += f"""
        <tr class="job-row" data-score="{score}">
          <td class="rank">#{i}</td>
          <td>
            <div class="score-badge" style="background:{score_color}">{score}</div>
          </td>
          <td>
            <div class="job-title-cell">
              <a class="job-title-link" href="{job_url}" target="_blank">{title}</a>
              <div class="job-meta">{site} · {loc}{(" · " + sal) if sal else ""}</div>
              {f'<div class="reasoning">{reasoning}</div>' if reasoning else ""}
            </div>
          </td>
          <td class="actions-cell">
            {resume_btn}
            <a class="btn btn-apply" href="{apply_url}" target="_blank">Apply →</a>
          </td>
        </tr>"""

    if not job_rows_html:
        job_rows_html = """
        <tr><td colspan="4" class="empty">
          No jobs ready to apply. Run <code>hireagent run score tailor</code> first.
        </td></tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HireAgent — Apply Queue</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: #0f0f1a;
    color: #e2e8f0;
    min-height: 100vh;
  }}

  /* Header */
  .topbar {{
    background: linear-gradient(135deg, #1e1b4b, #0f172a);
    border-bottom: 1px solid #2d2d4e;
    padding: 20px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
  }}
  .topbar-left {{ display: flex; align-items: center; gap: 14px; }}
  .logo {{ font-size: 28px; }}
  .brand h1 {{ font-size: 20px; font-weight: 800; color: #a5b4fc; }}
  .brand p {{ font-size: 12px; color: #64748b; margin-top: 2px; }}

  .stats-pills {{ display: flex; gap: 10px; flex-wrap: wrap; }}
  .pill {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 20px;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: 600;
    display: flex; align-items: center; gap: 6px;
  }}
  .pill .num {{ color: #a5b4fc; font-size: 16px; }}
  .pill.green {{ border-color: #4ade8044; }}
  .pill.green .num {{ color: #4ade80; }}

  /* Toolbar */
  .toolbar {{
    padding: 16px 32px;
    background: #12122a;
    border-bottom: 1px solid #1e293b;
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
  }}
  .toolbar-label {{ font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}

  .filter-btn {{
    background: #1e293b;
    border: 1px solid #334155;
    color: #94a3b8;
    padding: 6px 14px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    transition: all 0.15s;
  }}
  .filter-btn:hover {{ background: #263548; color: #e2e8f0; }}
  .filter-btn.active {{ background: #4f46e5; border-color: #4f46e5; color: #fff; }}

  .search {{
    background: #1e293b;
    border: 1px solid #334155;
    color: #e2e8f0;
    padding: 7px 14px;
    border-radius: 8px;
    font-size: 13px;
    width: 220px;
    outline: none;
    margin-left: auto;
  }}
  .search:focus {{ border-color: #4f46e5; }}
  .search::placeholder {{ color: #475569; }}

  /* Table */
  .table-wrap {{ padding: 24px 32px; }}

  .count-row {{
    font-size: 12px;
    color: #64748b;
    margin-bottom: 12px;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
  }}

  thead th {{
    text-align: left;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    color: #475569;
    font-weight: 700;
    padding: 10px 14px;
    border-bottom: 1px solid #1e293b;
  }}

  .job-row {{
    border-bottom: 1px solid #1a1a2e;
    transition: background 0.1s;
  }}
  .job-row:hover {{ background: #16213e; }}

  td {{ padding: 14px; vertical-align: top; }}

  .rank {{ color: #334155; font-size: 12px; font-weight: 600; white-space: nowrap; }}

  .score-badge {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px; height: 32px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 800;
    color: #0f0f1a;
  }}

  .job-title-cell {{ display: flex; flex-direction: column; gap: 4px; }}
  .job-title-link {{
    color: #e2e8f0;
    text-decoration: none;
    font-weight: 600;
    font-size: 14px;
    line-height: 1.3;
  }}
  .job-title-link:hover {{ color: #a5b4fc; }}

  .job-meta {{ font-size: 12px; color: #64748b; }}
  .reasoning {{ font-size: 11px; color: #475569; font-style: italic; line-height: 1.5; margin-top: 2px; max-width: 520px; }}

  .actions-cell {{ white-space: nowrap; text-align: right; }}

  .btn {{
    display: inline-block;
    padding: 7px 14px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 700;
    text-decoration: none;
    cursor: pointer;
    transition: all 0.15s;
    margin-left: 6px;
  }}

  .btn-apply {{
    background: linear-gradient(135deg, #4f46e5, #7c3aed);
    color: #fff;
    border: none;
  }}
  .btn-apply:hover {{
    background: linear-gradient(135deg, #4338ca, #6d28d9);
    transform: translateY(-1px);
    box-shadow: 0 3px 10px rgba(79,70,229,0.4);
  }}

  .btn-resume {{
    background: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
  }}
  .btn-resume:hover {{ background: #263548; color: #e2e8f0; }}

  .empty {{ text-align: center; padding: 48px; color: #64748b; font-size: 14px; }}

  .hidden {{ display: none !important; }}

  /* Extension CTA */
  .ext-cta {{
    margin: 0 32px 24px;
    background: linear-gradient(135deg, #1e1b4b, #1a1a2e);
    border: 1px solid #4f46e544;
    border-radius: 12px;
    padding: 16px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }}
  .ext-cta-icon {{ font-size: 28px; }}
  .ext-cta-text h3 {{ font-size: 14px; font-weight: 700; color: #a5b4fc; }}
  .ext-cta-text p {{ font-size: 12px; color: #64748b; margin-top: 3px; }}
  .ext-cta-btn {{
    margin-left: auto;
    background: linear-gradient(135deg, #4f46e5, #7c3aed);
    color: #fff;
    border: none;
    padding: 8px 18px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    text-decoration: none;
  }}

  @media (max-width: 768px) {{
    .topbar, .toolbar, .table-wrap {{ padding: 16px; }}
    .reasoning {{ display: none; }}
    .search {{ width: 100%; margin-left: 0; }}
  }}
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-left">
    <span class="logo">🎯</span>
    <div class="brand">
      <h1>Apply Queue</h1>
      <p>HireAgent — Top jobs ready for manual application</p>
    </div>
  </div>
  <div class="stats-pills">
    <div class="pill green"><span class="num">{total_ready}</span> Ready to Apply</div>
    <div class="pill"><span class="num">{total_applied}</span> Applied</div>
    <div class="pill"><span class="num">{min_score}+</span> Min Score</div>
  </div>
</div>

<div class="toolbar">
  <span class="toolbar-label">Score Filter:</span>
  <button class="filter-btn active" onclick="setFilter(0,this)">All {min_score}+</button>
  <button class="filter-btn" onclick="setFilter(8,this)">8+ Strong</button>
  <button class="filter-btn" onclick="setFilter(9,this)">9+ Excellent</button>
  <input type="text" class="search" placeholder="Search title, company..." oninput="filterText(this.value)">
</div>

<div class="ext-cta">
  <span class="ext-cta-icon">🤖</span>
  <div class="ext-cta-text">
    <h3>HireAgent Fill Chrome Extension</h3>
    <p>Click "Apply →" on any job, then use the extension to auto-fill the form in seconds.</p>
  </div>
  <a class="ext-cta-btn" href="chrome://extensions" target="_blank">Open Extensions</a>
</div>

<div class="table-wrap">
  <div class="count-row" id="countRow">{total_ready} jobs ready</div>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Score</th>
        <th>Job</th>
        <th style="text-align:right">Actions</th>
      </tr>
    </thead>
    <tbody id="jobTable">
{job_rows_html}
    </tbody>
  </table>
</div>

<script>
let minScore = 0;
let searchText = '';

function setFilter(min, btn) {{
  minScore = min;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}}

function filterText(val) {{
  searchText = val.toLowerCase();
  applyFilters();
}}

function applyFilters() {{
  let shown = 0, total = 0;
  document.querySelectorAll('.job-row').forEach(row => {{
    total++;
    const score = parseInt(row.dataset.score) || 0;
    const text  = row.textContent.toLowerCase();
    const ok = score >= (minScore || {min_score}) && (!searchText || text.includes(searchText));
    row.classList.toggle('hidden', !ok);
    if (ok) shown++;
  }});
  document.getElementById('countRow').textContent = shown + ' of ' + total + ' jobs showing';
}}
applyFilters();
</script>

</body>
</html>"""

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    abs_path = str(out.resolve())
    console.print(f"[green]Report written → {abs_path}[/green]")
    return abs_path


def open_report(output_path: str | None = None, min_score: int = 7, limit: int = 0) -> None:
    """Generate the apply-queue report and open it in the default browser."""
    path = generate_report(output_path, min_score=min_score, limit=limit)
    console.print("[dim]Opening in browser...[/dim]")
    webbrowser.open(f"file:///{path}")
