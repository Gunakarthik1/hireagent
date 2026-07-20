<div align="center">

# HireAgent

### AI-Powered Job Discovery, Resume Tailoring & Auto-Application Pipeline

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)
[![Browser](https://img.shields.io/badge/Automation-Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)](https://playwright.dev)
[![ATS](https://img.shields.io/badge/ATS-Workday%20%7C%20Greenhouse%20%7C%20Lever-6366f1?style=for-the-badge)]()

**Built by [Gunakarthik Naidu Lanka](https://www.linkedin.com/in/gunakarthik-naidu-lanka)**  
MS Computer Science @ Arizona State University • GPA 4.0

*From job boards → tailored resume → submitted application. Fully automated.*

</div>

---

## What Is HireAgent?

HireAgent is a **production-grade agentic pipeline** that automates the entire job hunt for entry-level software engineers.

It scrapes **8+ job boards**, scores every role with an LLM, generates a **unique tailored one-page resume** (LaTeX → PDF) per job, and fills out ATS application forms using a **Vision-Verified Browser Agent** — all from a single terminal command.

A built-in **React + FastAPI dashboard** gives you a live view of every job, score, and resume version, with one-click PDF previews and apply controls.

---

## The Pipeline

| Stage | What Happens | Model |
|-------|-------------|-------|
| **Discover** | Scrapes 8+ job boards for entry-level SWE roles | — |
| **Enrich** | Visits each job page, pulls full description + apply URL | Ollama gemma3:4b |
| **Score** | Rates each job 1–10 for fit (stack, level, location) | NVIDIA DeepSeek-V3 |
| **Tailor** | Rewrites resume bullets to mirror the job description | NVIDIA DeepSeek-R1 |
| **Cover** | Generates a targeted cover letter | NVIDIA DeepSeek-R1 |
| **PDF** | Compiles tailored resume → one-page PDF via LaTeX | — |
| **Apply** | Vision-verified form fill + enterprise CAPTCHA solving | NVIDIA Llama-3.2-Vision |

Run the whole thing with one command:

```bash
hireagent run        # discover → enrich → score → tailor → cover → pdf
hireagent apply      # submit applications automatically
```

---

## Dashboard

```bash
hireagent dashboard
```

Opens a live React dashboard at `http://localhost:8000` backed by a FastAPI server. From it you can:

- Browse all discovered jobs with scores, locations, and status
- Preview tailored resume PDFs per job
- Mark jobs as applied / skip
- Trigger pipeline scans (6-hour cooldown to avoid duplicate work)
- Manage resume versions (grouped by ATS score bucket)
- Filter by fit score, company, apply status

The dashboard talks to the backend over `/api/*` — all routes live in `src/hireagent/api/main.py`. In production it's served as a static SPA from `dashboard/dist`; in development Vite proxies `/api` → `http://localhost:8000`.

---

## Autonomous Apply Engine

### Vision-Verified Filling (Set-of-Marks)
HireAgent screenshots the ATS form, draws bounding boxes around every interactive element, and uses **Llama-3.2-11B-Vision** to map your profile data to the visual layout — field by field, verified.

### Enterprise CAPTCHA Solving
Integrated with the **CapSolver API**:
- **hCaptcha** — Lever, Veeva formats
- **Cloudflare Turnstile** — script & iframe injection
- **reCAPTCHA v2 / Enterprise** — sitekey-based solving
- **Arkose Labs / FunCaptcha** — enterprise-grade solving

### Resilient Navigation
- **Email-gate bypass** — auto-completes pre-forms (iCIMS, Breezy)
- **SSO protection** — skips SSO only when no direct form exists
- **LinkedIn deprioritization** — prefers direct ATS URLs for higher success rates
- **Stealth mode** — random human-like delays between applications

---

## Multi-LLM Routing

| Task | Model | Where |
|------|-------|-------|
| Scoring | NVIDIA DeepSeek-V3 | Cloud |
| Tailoring | NVIDIA DeepSeek-R1-14B | Cloud |
| Vision fill | NVIDIA Llama-3.2-11B-Vision | Cloud |
| Schema mapping | NVIDIA Nemotron-340B | Cloud |
| Enrichment | Ollama gemma3:4b | Local |

---

## Eligibility Filter

Every job is checked before any LLM work is done:

| Accepted | Rejected |
|----------|----------|
| Entry-level / New Grad / Junior / BS / MS | Senior / Staff / Principal / Lead |
| US-based or Remote | Non-US only |
| Software / AI / ML / Full-Stack | Requires security clearance |

---

## Chrome Extension

A lightweight Chrome extension (`extension/`) autofills job application forms using your saved HireAgent profile — no pipeline required.

```bash
hireagent export-profile    # writes ~/.hireagent/extension_profile.json
```

Then in Chrome → `chrome://extensions` → Developer mode → Load unpacked → select `extension/`. Import the exported JSON from the extension settings.

---

## Quick Start

### 1. Prerequisites

```bash
# macOS
brew install --cask mactex-no-gui    # LaTeX for PDF generation
brew install ollama && ollama pull gemma3:4b

# All platforms
pip install uv
uv pip install hireagent
playwright install chromium
```

### 2. Configure API Keys

```bash
mkdir -p ~/.hireagent
cat > ~/.hireagent/.env << 'EOF'
NVIDIA_API_KEY=nvapi-...          # https://build.nvidia.com
CAPSOLVER_API_KEY=CAP-...         # https://capsolver.com  (optional, for CAPTCHA)
HIREAGENT_TELEGRAM_TOKEN=...      # optional, Telegram bot notifications
HIREAGENT_TELEGRAM_CHAT_ID=...
EOF
```

### 3. Initialize Your Profile

```bash
hireagent init      # interactive wizard: name, resume, target roles, search config
hireagent doctor    # verify everything is wired up correctly
```

### 4. Run

```bash
# Full pipeline (no apply)
hireagent run

# Specific stages only
hireagent run discover enrich score
hireagent run tailor cover pdf

# Open the dashboard
hireagent dashboard

# Auto-apply (requires Claude Code CLI + Chrome + Node.js)
hireagent apply --limit 10
```

---

## Commands

```
hireagent init                         First-time setup wizard
hireagent doctor                       Check setup and diagnose missing deps
hireagent run [stages...]              Run pipeline stages (default: all except apply)
hireagent apply                        Auto-apply to ready jobs
hireagent apply --url <url>            Apply to one specific job
hireagent apply --dry-run              Fill forms but don't submit
hireagent apply --gen --url <url>      Write a Claude prompt file for manual debugging
hireagent apply --mark-applied <url>   Manually mark a job as applied
hireagent apply --mark-failed <url>    Mark a job as failed with an optional reason
hireagent apply --reset-failed         Reset all failed jobs for retry
hireagent status                       Show pipeline stats in the terminal
hireagent dashboard                    Launch React + FastAPI dashboard
hireagent report                       Generate a static HTML apply-queue report
hireagent export-profile               Export profile JSON for the Chrome extension
hireagent bot                          Start Telegram bot for phone-based remote control
hireagent debug jobs                   Inspect DB with schema-safe queries
hireagent debug apply-failures         Show recent apply failures
hireagent debug db-info                Show DB path and row counts
hireagent debug backup-db              Timestamped SQLite backup
hireagent debug clear-db               Reset DB (auto-backup first)
hireagent debug reclassify-eligibility Recompute eligibility for all jobs
hireagent debug reset-tailor-attempts  Reset tailor retry counters
hireagent debug reset-stale-in-progress Clear stale in-progress apply locks
hireagent debug purge-unavailable      Delete expired / fake / closed listings
hireagent debug rescue-expired         Rescue jobs wrongly marked as expired
```

### `hireagent run` options

```
--min-score INT        Minimum fit score for tailor/cover stage (default: 7)
--workers INT          Parallel threads for discover/enrich (default: 1)
--stream               Run stages concurrently
--dry-run              Preview without executing
--validation MODE      strict | normal | lenient (default: normal)
--limit-discovery INT  Cap new jobs discovered per run
--hours-old INT        Only scrape jobs posted within last N hours
```

### `hireagent apply` options

```
--limit INT            Max applications to submit
--workers INT          Parallel browser workers (default: 1)
--min-score INT        Minimum fit score (default: 5)
--continuous           Run forever, polling for new jobs
--dry-run              Fill forms but don't submit
--headless             Run browsers in headless mode
--url URL              Apply to one specific job URL
--greenhouse-only      Only target Greenhouse ATS jobs
--no-stealth           Skip human-like delays (fast testing mode)
--model MODEL          Claude model for --gen (default: claude-sonnet-4-6)
```

---

## API Reference

The FastAPI backend (`hireagent dashboard`) exposes:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/jobs` | List jobs — filter by `min_score`, `status`, `limit`, `offset` |
| `GET` | `/api/job?url=` | Single job with full description |
| `POST` | `/api/job/apply?url=` | Mark job as applied |
| `POST` | `/api/job/unapply?url=` | Undo applied mark |
| `GET` | `/api/job/resume?url=` | Stream tailored resume PDF |
| `GET` | `/api/stats` | Pipeline summary stats |
| `GET` | `/api/versions` | List all resume versions |
| `POST` | `/api/versions/assign` | Background version assignment |
| `GET` | `/api/resume/{version_id}/pdf` | Stream a version PDF |
| `GET` | `/api/scan/status` | Scan state + cooldown remaining |
| `POST` | `/api/scan/run` | Trigger discover → score → tailor (6h cooldown) |
| `POST` | `/api/pipeline/run?stage=` | Trigger any single pipeline stage |
| `POST` | `/api/jobs/reclassify` | Recompute eligibility for all scored jobs |

---

## Project Structure

```
HireAgent/
├── src/hireagent/
│   ├── cli.py                  ← All CLI commands (typer)
│   ├── pipeline.py             ← Stage orchestration
│   ├── database.py             ← SQLite schema + helpers
│   ├── eligibility.py          ← Rule-based job filter
│   ├── llm.py                  ← Multi-LLM router
│   ├── latex_renderer.py       ← LaTeX → PDF compiler
│   ├── version_manager.py      ← Resume version grouping
│   ├── view.py                 ← Static HTML report generator
│   ├── telegram_bot.py         ← Telegram bot (remote control)
│   │
│   ├── api/
│   │   └── main.py             ← FastAPI backend (all /api/* routes)
│   │
│   ├── apply/
│   │   ├── launcher.py         ← Worker queue + job dispatch
│   │   ├── free_agent.py       ← Core state machine (SSO, navigation)
│   │   ├── vision_loop.py      ← Vision fill + CAPTCHA solving
│   │   ├── playwright_apply.py ← Playwright browser automation
│   │   ├── ats_detector.py     ← ATS platform detection
│   │   ├── form_filler.py      ← Form field mapping
│   │   ├── saas_observer.py    ← SaaS ATS observer
│   │   └── prompt.py           ← LLM prompt templates
│   │
│   ├── discovery/
│   │   ├── jobspy.py           ← Multi-board job scraping
│   │   └── workday.py          ← Workday-specific discovery
│   │
│   ├── scoring/
│   │   ├── scorer.py           ← LLM fit scoring (1–10)
│   │   └── tailor.py           ← Resume + cover letter generation
│   │
│   ├── config/
│   │   ├── sites.yaml          ← Job board search targets
│   │   └── employers.yaml      ← Company-specific apply rules
│   │
│   └── wizard/
│       └── init.py             ← First-time setup wizard
│
├── dashboard/
│   ├── src/
│   │   ├── App.jsx             ← Root component, data fetching
│   │   ├── api.js              ← All /api/* client calls
│   │   ├── components/         ← Dashboard, Jobs, Versions, Settings pages
│   │   └── utils.js            ← Data mapping helpers
│   ├── dist/                   ← Production build (served by FastAPI)
│   └── vite.config.js          ← Dev proxy → localhost:8000
│
└── extension/                  ← Chrome extension (profile-based autofill)
```

---

## Tiers

HireAgent gates features by what's installed:

| Tier | Requires | Unlocks |
|------|----------|---------|
| **1** | Python + profile | Discovery, enrichment |
| **2** | + Ollama / NVIDIA API key | Scoring, tailoring, cover letters, PDF |
| **3** | + Claude Code CLI + Chrome + Node.js | Auto-apply |

Run `hireagent doctor` to see your current tier and what's missing.

---

## About

**Gunakarthik Naidu Lanka** — MS Computer Science, Arizona State University (GPA 4.0)

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=flat-square&logo=linkedin)](https://www.linkedin.com/in/gunakarthik-naidu-lanka)
[![GitHub](https://img.shields.io/badge/GitHub-guna29-181717?style=flat-square&logo=github)](https://github.com/guna29)

---

## License

MIT © 2026 Gunakarthik Naidu Lanka — see [LICENSE](LICENSE)

<div align="center">
<sub>Built with Python, FastAPI, React, Playwright, NVIDIA NIM, LaTeX, and way too many job applications.</sub>
</div>
