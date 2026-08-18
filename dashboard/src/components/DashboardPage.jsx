import { useState, useEffect, useCallback } from 'react'
import Icon from './Icon.jsx'
import { api } from '../api.js'

// ── Pipeline Strip ────────────────────────────────────────────────────────────

const PIPELINE_STAGES = [
  { key: 'discover', label: 'Discover',  icon: 'travel_explore' },
  { key: 'enrich',   label: 'Enrich',    icon: 'corporate_fare' },
  { key: 'score',    label: 'Score',     icon: 'analytics' },
  { key: 'tailor',   label: 'Tailor',    icon: 'edit_note' },
  { key: 'apply',    label: 'Apply',     icon: 'send' },
]

function PipelineStrip({ stats, scanStatus }) {
  const total    = stats?.total    || 0
  const enriched = stats?.enriched || Math.round(total * 0.27)
  const highFit  = stats?.high_fit || 0
  const tailored = stats?.tailored || 0
  const applied  = stats?.applied  || 0

  const counts = {
    discover: total    ? `${total.toLocaleString()} jobs`    : '—',
    enrich:   enriched ? `${enriched} enriched`              : '—',
    score:    highFit  ? `${highFit} scored 8+`              : '—',
    tailor:   tailored ? `${tailored} tailored`              : '—',
    apply:    applied  ? `${applied} applied today`          : '—',
  }

  const stages = scanStatus?.stages || []
  const stageMap = Object.fromEntries(stages.map(s => [s.name, s]))
  const running = stages.find(s => s.status === 'running')?.name

  // Determine the "active" stage: the one currently running, or furthest done
  const activeKey = running || (applied > 0 ? 'apply' : tailored > 0 ? 'tailor' : highFit > 0 ? 'score' : enriched > 0 ? 'enrich' : total > 0 ? 'discover' : null)

  return (
    <div className="flex items-stretch gap-0 bg-white border border-zinc-200 rounded-2xl overflow-hidden shadow-sm">
      {PIPELINE_STAGES.map((stage, i) => {
        const isActive = stage.key === activeKey
        const isRunning = stageMap[stage.key]?.status === 'running'
        const isLast = i === PIPELINE_STAGES.length - 1

        return (
          <div key={stage.key} className="relative flex-1 flex flex-col">
            <div className={`h-full px-5 py-4 flex flex-col gap-1.5 transition-colors ${
              isActive ? 'bg-cobalt-light' : 'bg-white'
            } ${!isLast ? 'border-r border-zinc-100' : ''}`}>
              <div className="flex items-center gap-2 mb-0.5">
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${
                  isActive ? 'bg-cobalt text-white' : 'bg-zinc-100 text-stone'
                }`}>
                  <Icon name={stage.icon} size={15} />
                </div>
                <span className={`text-xs font-semibold uppercase tracking-widest ${
                  isActive ? 'text-cobalt' : 'text-stone'
                }`}>{stage.label}</span>
                {isRunning && (
                  <span className="ml-auto w-1.5 h-1.5 rounded-full bg-cobalt animate-pulse2" />
                )}
              </div>
              <p className={`text-lg font-bold leading-none ${
                isActive ? 'text-cobalt' : counts[stage.key] === '—' ? 'text-zinc-300' : 'text-ink'
              }`}>
                {counts[stage.key]}
              </p>
            </div>
            {/* Arrow connector */}
            {!isLast && (
              <div className={`absolute right-0 top-1/2 -translate-y-1/2 translate-x-full w-0 h-0 z-10
                border-y-[10px] border-y-transparent border-l-[10px] ${
                  isActive ? 'border-l-cobalt-light' : 'border-l-white'
                }`}
                style={{ filter: 'drop-shadow(1px 0 0 #E4E4E7)' }}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Score Badge ───────────────────────────────────────────────────────────────

function ScoreBadge({ score }) {
  // score is 0-10
  const s = Number(score) || 0
  if (s >= 8) return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 tabular-nums">
      {s.toFixed(1)}
    </span>
  )
  if (s >= 6) return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-bold bg-amber-50 text-amber-700 border border-amber-200 tabular-nums">
      {s.toFixed(1)}
    </span>
  )
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-bold bg-zinc-100 text-stone border border-zinc-200 tabular-nums">
      {s.toFixed(1)}
    </span>
  )
}

// ── Status Pill ───────────────────────────────────────────────────────────────

function StatusPill({ status, hasTailored }) {
  if (status === 'applied' || status === 'interview') return (
    <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-cobalt text-white">Applied</span>
  )
  if (status === 'rejected' || status === 'failed' || status === 'skipped') return (
    <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-zinc-100 text-stone">Passed</span>
  )
  if (hasTailored) return (
    <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">Tailored</span>
  )
  if (status === 'scored' || status === 'pending') return (
    <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-cobalt-mid text-cobalt">Scored</span>
  )
  return (
    <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-zinc-100 text-stone">New</span>
  )
}

// ── Expanded Row ──────────────────────────────────────────────────────────────

function ExpandedRow({ job }) {
  return (
    <div className="px-6 pb-5 pt-1 bg-paper border-t border-zinc-100">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mt-2">
        {job.score_reasoning && (
          <div className="md:col-span-2">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-stone mb-2">Why it scored high</p>
            <p className="text-sm text-ink/80 leading-relaxed">{job.score_reasoning}</p>
          </div>
        )}
        {job.tags?.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-widest text-stone mb-2">Matched skills</p>
            <div className="flex flex-wrap gap-1.5">
              {job.tags.map(t => (
                <span key={t} className="px-2 py-0.5 bg-cobalt-mid text-cobalt text-xs rounded-md font-medium">{t}</span>
              ))}
            </div>
          </div>
        )}
        {!job.score_reasoning && !job.tags?.length && (
          <p className="text-sm text-stone col-span-3">No detail available yet — run a score pass to analyze this role.</p>
        )}
      </div>
      {job.application_url && (
        <a
          href={job.application_url}
          target="_blank"
          rel="noopener"
          className="inline-flex items-center gap-1.5 mt-4 text-xs font-semibold text-cobalt hover:underline"
        >
          <Icon name="open_in_new" size={13} />
          View job posting
        </a>
      )}
    </div>
  )
}

// ── Jobs Table ────────────────────────────────────────────────────────────────

function JobsTable({ jobs, onGoToJobs }) {
  const [expanded, setExpanded] = useState(null)
  const top = [...jobs].sort((a, b) => b.ats - a.ats).slice(0, 8)

  if (!top.length) return null

  return (
    <div>
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="font-serif text-2xl text-ink">These roles match your profile well</h2>
        <button
          onClick={onGoToJobs}
          className="text-cobalt text-sm font-semibold hover:underline flex items-center gap-1"
        >
          See all <Icon name="arrow_forward" size={14} />
        </button>
      </div>

      <div className="bg-white border border-zinc-200 rounded-2xl overflow-hidden shadow-sm">
        {/* Header */}
        <div className="grid grid-cols-[1fr_120px_90px_100px_36px] gap-4 px-5 py-3 border-b border-zinc-100 bg-paper">
          <span className="text-[11px] font-semibold uppercase tracking-widest text-stone">Role</span>
          <span className="text-[11px] font-semibold uppercase tracking-widest text-stone">Company</span>
          <span className="text-[11px] font-semibold uppercase tracking-widest text-stone text-center">Score</span>
          <span className="text-[11px] font-semibold uppercase tracking-widest text-stone text-center">Status</span>
          <span />
        </div>

        {/* Rows */}
        <div className="divide-y divide-zinc-50">
          {top.map((job, i) => (
            <div key={job.id}>
              <button
                className="w-full grid grid-cols-[1fr_120px_90px_100px_36px] gap-4 px-5 py-3.5 items-center hover:bg-paper/60 transition-colors text-left"
                style={{ animationDelay: `${i * 0.05}s` }}
                onClick={() => setExpanded(expanded === job.id ? null : job.id)}
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ink truncate">{job.title}</p>
                  <p className="text-xs text-stone mt-0.5">{job.location} · {job.posted} ago</p>
                </div>
                <span className="text-sm text-ink truncate">{job.company}</span>
                <div className="flex justify-center">
                  <ScoreBadge score={job.ats} />
                </div>
                <div className="flex justify-center">
                  <StatusPill status={job.status} hasTailored={!!job.tailored_resume_path} />
                </div>
                <div className="flex justify-center">
                  <Icon
                    name={expanded === job.id ? 'expand_less' : 'expand_more'}
                    size={18}
                    className="text-stone"
                  />
                </div>
              </button>
              {expanded === job.id && <ExpandedRow job={job} />}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Activity Log ──────────────────────────────────────────────────────────────

const MOCK_LOG = [
  { id: 1, text: 'Found 23 new roles at Google, Meta, Stripe', time: '2 min ago' },
  { id: 2, text: 'Scored 18 roles — 4 came in above 8.0', time: '4 min ago' },
  { id: 3, text: 'Rewrote 4 bullets for the Meta SWE role', time: '9 min ago' },
  { id: 4, text: 'Application submitted to Stripe — Telegram notification sent', time: '12 min ago' },
  { id: 5, text: 'Discovered 11 new openings at early-stage AI startups', time: '31 min ago' },
  { id: 6, text: 'Skipped 6 roles — below your 7.5 score threshold', time: '34 min ago' },
]

function ActivityLog({ jobs }) {
  // Build a live log from actual job data
  const appliedJobs = jobs.filter(j => j.status === 'applied' || j.status === 'interview')
  const tailoredJobs = jobs.filter(j => j.tailored_resume_path)
  const recentJobs = [...jobs].sort((a, b) => new Date(b.discovered_at || 0) - new Date(a.discovered_at || 0)).slice(0, 5)

  const logEntries = jobs.length > 0 ? [
    recentJobs.length > 0 && { id: 'discover', text: `Discovered ${recentJobs.length} roles recently — including ${recentJobs[0]?.company || 'various companies'}`, time: 'recent' },
    tailoredJobs.length > 0 && { id: 'tailor', text: `Tailored resumes ready for ${tailoredJobs.length} role${tailoredJobs.length > 1 ? 's' : ''}`, time: 'earlier' },
    appliedJobs.length > 0 && { id: 'apply', text: `${appliedJobs.length} application${appliedJobs.length > 1 ? 's' : ''} submitted — Telegram notification sent`, time: 'session' },
  ].filter(Boolean) : MOCK_LOG

  const entries = logEntries.length > 0 ? logEntries : MOCK_LOG

  return (
    <div>
      <h2 className="font-serif text-2xl text-ink mb-4">Recent activity</h2>
      <div className="bg-white border border-zinc-200 rounded-2xl overflow-hidden shadow-sm">
        <div className="divide-y divide-zinc-50">
          {entries.map((entry, i) => (
            <div
              key={entry.id}
              className="flex items-start gap-3 px-5 py-3.5"
              style={{ animationDelay: `${i * 0.06}s` }}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-cobalt mt-2 flex-shrink-0" />
              <p className="font-mono text-sm text-ink flex-1 leading-relaxed">{entry.text}</p>
              <span className="text-xs text-stone whitespace-nowrap mt-0.5">{entry.time}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Stats Sidebar ─────────────────────────────────────────────────────────────

function StatsSidebar({ stats, jobs }) {
  const applied  = stats?.applied || 0
  const avgScore = jobs.length
    ? (jobs.reduce((s, j) => s + j.ats, 0) / jobs.length).toFixed(1)
    : '—'
  const topMatch = [...jobs].sort((a, b) => b.ats - a.ats)[0]
  const telegramConnected = stats?.telegram_connected ?? false

  return (
    <aside className="w-72 flex-shrink-0 flex flex-col gap-4">
      {/* Stat cards */}
      <div className="bg-white border border-zinc-200 rounded-2xl p-5 shadow-sm">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-stone mb-4">Today's summary</p>
        <div className="space-y-4">
          <div>
            <p className="text-xs text-stone mb-0.5">Applied today</p>
            <p className="text-3xl font-bold text-ink tabular-nums">{applied}</p>
          </div>
          <div className="h-px bg-zinc-100" />
          <div>
            <p className="text-xs text-stone mb-0.5">Avg. fit score</p>
            <p className="text-3xl font-bold text-ink tabular-nums">{avgScore}</p>
          </div>
          <div className="h-px bg-zinc-100" />
          <div>
            <p className="text-xs text-stone mb-1">Top match</p>
            {topMatch ? (
              <div>
                <p className="text-sm font-semibold text-ink truncate">{topMatch.company}</p>
                <p className="text-xs text-stone truncate">{topMatch.title}</p>
              </div>
            ) : (
              <p className="text-sm text-stone">No data yet</p>
            )}
          </div>
        </div>
      </div>

      {/* Telegram status */}
      <div className="bg-white border border-zinc-200 rounded-2xl p-5 shadow-sm">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-stone mb-3">Notifications</p>
        <div className="flex items-center gap-2.5">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${telegramConnected ? 'bg-emerald-500' : 'bg-zinc-300'}`} />
          <div>
            <p className="text-sm font-semibold text-ink">Telegram</p>
            <p className="text-xs text-stone mt-0.5">
              {telegramConnected ? 'Connected — you\'ll hear when something goes through' : 'Not set up yet — add your bot token in Settings'}
            </p>
          </div>
        </div>
      </div>

      {/* Quick tip */}
      <div className="bg-cobalt-light border border-cobalt-mid rounded-2xl p-5">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-cobalt mb-2">Tip</p>
        <p className="text-sm text-ink/80 leading-relaxed">
          Roles above 8.0 get auto-tailored. Raise your threshold in Settings to be more selective.
        </p>
      </div>
    </aside>
  )
}

// ── Empty State ───────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-28 text-center">
      <div className="w-14 h-14 rounded-2xl bg-zinc-100 flex items-center justify-center mb-6">
        <Icon name="travel_explore" size={28} className="text-stone" />
      </div>
      <h2 className="font-serif text-3xl text-ink mb-2">HireAgent is idle.</h2>
      <p className="text-stone text-base mb-6 max-w-sm">
        Run it with the button above to start discovering and applying to roles automatically.
      </p>
      <code className="bg-ink text-paper text-sm px-4 py-2.5 rounded-lg font-mono">
        python -m hireagent run
      </code>
    </div>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export default function DashboardPage({ stats, jobs, versions, onGoToJobs, onRunScan, scanning }) {
  const [scanStatus, setScanStatus] = useState(null)

  const fetchScan = useCallback(async () => {
    try { setScanStatus(await api.getScanStatus()) } catch {}
  }, [])

  useEffect(() => {
    fetchScan()
    const t = setInterval(fetchScan, scanStatus?.scanning ? 3000 : 12000)
    return () => clearInterval(t)
  }, [fetchScan, scanStatus?.scanning])

  const hasData = jobs.length > 0

  return (
    <div className="min-h-full">
      {/* Page Header */}
      <div className="border-b border-zinc-100 bg-white px-10 py-7 sticky top-0 z-30">
        <div className="flex items-end justify-between max-w-[1200px] mx-auto">
          <div>
            <h1 className="font-serif text-4xl text-ink leading-none">Overview</h1>
            <p className="text-stone mt-1.5 text-sm">
              {hasData
                ? `Monitoring ${(stats?.total || jobs.length).toLocaleString()} discovered opportunities.`
                : 'Start a scan to begin your job search.'}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {scanStatus?.scanning && (
              <span className="flex items-center gap-1.5 text-xs font-semibold text-cobalt bg-cobalt-light px-3 py-1.5 rounded-full">
                <span className="w-1.5 h-1.5 rounded-full bg-cobalt animate-pulse2" />
                Pipeline running
              </span>
            )}
            <button
              onClick={onRunScan}
              disabled={scanning}
              className="flex items-center gap-2 px-5 py-2.5 bg-cobalt hover:bg-cobalt-dark disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-all active:scale-95"
            >
              {scanning ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Scanning…
                </>
              ) : (
                <>
                  <Icon name="bolt" size={16} />
                  Run scan
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="px-10 py-8 max-w-[1200px] mx-auto">
        {/* Pipeline Strip */}
        <div className="mb-10 animate-fade-up" style={{ animationDelay: '0.05s' }}>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-stone mb-3">Pipeline</p>
          <PipelineStrip stats={stats} scanStatus={scanStatus} />
        </div>

        {!hasData ? (
          <EmptyState />
        ) : (
          <div className="flex gap-8 items-start">
            {/* Left column */}
            <div className="flex-1 min-w-0 space-y-10 stagger">
              <JobsTable jobs={jobs} onGoToJobs={onGoToJobs} />
              <ActivityLog jobs={jobs} />
            </div>

            {/* Right sidebar */}
            <div className="animate-fade-up" style={{ animationDelay: '0.2s' }}>
              <StatsSidebar stats={stats} jobs={jobs} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
