import { useState, useMemo } from 'react'
import Icon from './Icon.jsx'
import { ResumeModal, useToast } from './UI.jsx'
import { api } from '../api.js'

// ── Score Badge ───────────────────────────────────────────────────────────────

function ScoreBadge({ score }) {
  const s = Number(score) || 0
  if (s >= 8) return (
    <span className="inline-flex items-center justify-center w-10 h-10 rounded-xl text-sm font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 tabular-nums flex-shrink-0">
      {s.toFixed(0)}
    </span>
  )
  if (s >= 6) return (
    <span className="inline-flex items-center justify-center w-10 h-10 rounded-xl text-sm font-bold bg-amber-50 text-amber-700 border border-amber-200 tabular-nums flex-shrink-0">
      {s.toFixed(0)}
    </span>
  )
  return (
    <span className="inline-flex items-center justify-center w-10 h-10 rounded-xl text-sm font-bold bg-zinc-100 text-stone border border-zinc-200 tabular-nums flex-shrink-0">
      {s.toFixed(0)}
    </span>
  )
}

// ── Status Pill ───────────────────────────────────────────────────────────────

function StatusPill({ status, hasTailored }) {
  if (status === 'applied' || status === 'interview') return (
    <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-cobalt text-white">Applied</span>
  )
  if (status === 'rejected' || status === 'failed' || status === 'skipped') return (
    <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-zinc-100 text-stone">Passed</span>
  )
  if (hasTailored) return (
    <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">Tailored</span>
  )
  return (
    <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-cobalt-mid text-cobalt">New</span>
  )
}

// ── Company Avatar ────────────────────────────────────────────────────────────

function Avatar({ company, size = 44 }) {
  const palettes = [
    'bg-violet-100 text-violet-700',
    'bg-sky-100 text-sky-700',
    'bg-emerald-100 text-emerald-700',
    'bg-amber-100 text-amber-700',
    'bg-rose-100 text-rose-700',
    'bg-cobalt-mid text-cobalt',
  ]
  const idx = (company || '?').charCodeAt(0) % palettes.length
  return (
    <div
      className={`flex items-center justify-center rounded-xl font-bold flex-shrink-0 ${palettes[idx]}`}
      style={{ width: size, height: size, fontSize: size * 0.38 }}
    >
      {(company || '?')[0].toUpperCase()}
    </div>
  )
}

// ── Expanded Detail ───────────────────────────────────────────────────────────

function ExpandedDetail({ job, onView, onMark }) {
  const isApplied = ['applied', 'interview', 'rejected', 'failed', 'skipped'].includes(job.status)
  return (
    <div className="mt-4 pt-4 border-t border-zinc-100">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {job.score_reasoning && (
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-widest text-stone mb-2">Why this role scores high</p>
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
            {job.tailored_resume_path && (
              <div className="mt-3">
                <p className="text-[11px] font-semibold uppercase tracking-widest text-stone mb-2">Resume</p>
                <button
                  onClick={() => onView(job)}
                  className="text-sm font-semibold text-cobalt hover:underline flex items-center gap-1"
                >
                  <Icon name="description" size={14} />
                  View tailored resume
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="flex items-center gap-3 mt-4">
        <a
          href={job.application_url}
          target="_blank"
          rel="noopener"
          className="flex items-center gap-2 px-4 py-2 bg-cobalt hover:bg-cobalt-dark text-white text-sm font-semibold rounded-xl transition-all active:scale-95"
        >
          <Icon name="open_in_new" size={15} />
          Open job posting
        </a>
        {!isApplied ? (
          <button
            onClick={() => onMark(job, 'applied')}
            className="flex items-center gap-2 px-4 py-2 border border-zinc-200 bg-white hover:bg-paper text-sm font-semibold text-ink rounded-xl transition-all"
          >
            <Icon name="check_circle" size={15} />
            Mark as applied
          </button>
        ) : (
          <button
            onClick={() => onMark(job, 'pending')}
            className="flex items-center gap-2 px-4 py-2 border border-zinc-200 bg-white hover:bg-paper text-sm font-medium text-stone rounded-xl transition-all"
          >
            <Icon name="refresh" size={15} />
            Reset status
          </button>
        )}
      </div>
    </div>
  )
}

// ── Job Row ───────────────────────────────────────────────────────────────────

function JobRow({ job, onView, onMark, index }) {
  const [open, setOpen] = useState(false)
  const isApplied = ['applied', 'interview'].includes(job.status)

  return (
    <div
      className={`bg-white border border-zinc-200 rounded-2xl px-5 py-4 shadow-sm transition-all hover:shadow-md ${isApplied ? 'opacity-60' : ''}`}
      style={{ animationDelay: `${index * 0.04}s` }}
    >
      <div className="flex items-center gap-4">
        <Avatar company={job.company} size={44} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-0.5">
            <h3
              className="text-sm font-semibold text-ink cursor-pointer hover:text-cobalt transition-colors"
              onClick={() => setOpen(o => !o)}
            >
              {job.title}
            </h3>
            <StatusPill status={job.status} hasTailored={!!job.tailored_resume_path} />
          </div>
          <p className="text-xs text-stone">
            {job.company} · {job.location}
            {job.salary && job.salary !== '—' ? ` · ${job.salary}` : ''}
            {' · posted '}
            {job.posted} ago
          </p>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <ScoreBadge score={job.ats} />
          <button
            onClick={() => setOpen(o => !o)}
            className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-zinc-50 transition-colors text-stone"
          >
            <Icon name={open ? 'expand_less' : 'expand_more'} size={18} />
          </button>
        </div>
      </div>
      {open && <ExpandedDetail job={job} onView={onView} onMark={onMark} />}
    </div>
  )
}

// ── Top Pick Banner ───────────────────────────────────────────────────────────

function TopPickBanner({ job, onView, onMark, onApply }) {
  const isApplied = ['applied', 'interview', 'rejected', 'failed', 'skipped'].includes(job.status)
  return (
    <div className="bg-ink rounded-2xl p-6 text-white mb-6 relative overflow-hidden">
      <div className="absolute top-0 right-0 w-64 h-full opacity-5 bg-gradient-to-l from-cobalt pointer-events-none" />
      <div className="flex items-start gap-5">
        <div className="w-14 h-14 rounded-xl bg-white/10 flex items-center justify-center text-white font-bold text-xl flex-shrink-0">
          {(job.company || '?')[0]}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-widest text-cobalt bg-cobalt/20 px-2 py-0.5 rounded-full">Top match</span>
          </div>
          <h3 className="text-xl font-bold text-white leading-tight">{job.title}</h3>
          <p className="text-white/50 text-sm mt-0.5">{job.company} · {job.location}</p>
        </div>
        <div className="text-right flex-shrink-0">
          <p className="text-3xl font-bold text-cobalt tabular-nums">{(job.ats * 10).toFixed(0)}%</p>
          <p className="text-white/40 text-[11px] font-semibold uppercase tracking-widest">fit score</p>
        </div>
      </div>
      <div className="flex items-center gap-3 mt-5">
        <a
          href={job.application_url}
          target="_blank"
          rel="noopener"
          onClick={() => onApply(job)}
          className="flex items-center gap-2 px-5 py-2.5 bg-cobalt hover:bg-cobalt-dark text-white text-sm font-semibold rounded-xl transition-all active:scale-95"
        >
          <Icon name="open_in_new" size={15} />
          Apply now
        </a>
        {job.tailored_resume_path && (
          <button
            onClick={() => onView(job)}
            className="flex items-center gap-2 px-5 py-2.5 bg-white/10 hover:bg-white/20 border border-white/10 text-white text-sm font-semibold rounded-xl transition-all"
          >
            <Icon name="description" size={15} />
            View resume
          </button>
        )}
        {!isApplied && (
          <button
            onClick={() => onMark(job, 'applied')}
            className="flex items-center gap-2 px-5 py-2.5 bg-white/10 hover:bg-white/20 border border-white/10 text-white/70 text-sm font-medium rounded-xl transition-all"
          >
            Mark applied
          </button>
        )}
      </div>
    </div>
  )
}

// ── Main Jobs Page ────────────────────────────────────────────────────────────

export default function JobsPage({ jobs, versions, companies, onMark, onRefreshJobs, onTailor }) {
  const toast = useToast()
  const [search, setSearch]   = useState('')
  const [sFilter, setSFilter] = useState('all')
  const [sort, setSort]       = useState('ats')
  const [resumeJob, setResumeJob] = useState(null)
  const [activeChips, setActiveChips] = useState([])

  const CHIP_OPTIONS = [
    { id: '8plus',    label: 'Score 8+' },
    { id: 'tailored', label: 'Tailored' },
    { id: 'remote',   label: 'Remote' },
  ]

  const toggleChip = (id) =>
    setActiveChips(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id])

  const filtered = useMemo(() => {
    let xs = [...jobs]
    if (search) {
      const q = search.toLowerCase()
      xs = xs.filter(j =>
        j.title.toLowerCase().includes(q) ||
        j.company.toLowerCase().includes(q) ||
        j.tags.some(t => t.toLowerCase().includes(q))
      )
    }
    if (sFilter !== 'all') xs = xs.filter(j => j.status === sFilter)
    if (activeChips.includes('8plus'))    xs = xs.filter(j => j.ats >= 8)
    if (activeChips.includes('tailored')) xs = xs.filter(j => j.tailored_resume_path)
    if (activeChips.includes('remote'))   xs = xs.filter(j => j.location?.toLowerCase().includes('remote'))
    if (sort === 'ats')    xs.sort((a, b) => b.ats - a.ats)
    if (sort === 'recent') xs.sort((a, b) => new Date(b.discovered_at || 0) - new Date(a.discovered_at || 0))
    if (sort === 'salary') {
      xs.sort((a, b) => {
        const n = s => parseInt((s || '0').replace(/\D/g, '')) || 0
        return n(b.salary) - n(a.salary)
      })
    }
    return xs
  }, [jobs, search, sFilter, sort, activeChips])

  const topPick = filtered[0]
  const rest    = filtered.slice(1)
  const showTopPick = topPick && topPick.ats >= 8.5

  const handleApply = (job) => {
    window.open(job.application_url, '_blank', 'noopener')
    toast(`Opened ${job.company} application`, { kind: 'info', icon: 'open_in_new' })
  }

  const handleRescrape = async () => {
    try {
      await api.runStage('discover')
      toast('Discovery started in background', { kind: 'info', icon: 'refresh' })
      setTimeout(onRefreshJobs, 3000)
    } catch (e) {
      toast('Failed: ' + e.message, { kind: 'err', icon: 'error' })
    }
  }

  return (
    <div className="min-h-full">
      {/* Header */}
      <div className="border-b border-zinc-100 bg-white px-10 py-7 sticky top-0 z-30">
        <div className="flex items-end justify-between max-w-[900px] mx-auto">
          <div>
            <h1 className="font-serif text-4xl text-ink leading-none">Job feed</h1>
            <p className="text-stone mt-1.5 text-sm">
              {jobs.length.toLocaleString()} roles discovered based on your profile.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleRescrape}
              className="flex items-center gap-2 px-4 py-2 border border-zinc-200 bg-white hover:bg-paper text-ink text-sm font-medium rounded-xl transition-all"
            >
              <Icon name="refresh" size={16} />
              Refresh
            </button>
            <select
              value={sort}
              onChange={e => setSort(e.target.value)}
              className="px-4 py-2 border border-zinc-200 bg-white text-ink text-sm font-medium rounded-xl focus:outline-none focus:ring-2 focus:ring-cobalt/20 transition-all"
            >
              <option value="ats">Best match first</option>
              <option value="recent">Newest first</option>
              <option value="salary">Highest salary</option>
            </select>
          </div>
        </div>
      </div>

      <div className="px-10 py-8 max-w-[900px] mx-auto">
        {/* Search + Filters */}
        <div className="flex gap-3 mb-4 flex-wrap">
          <div className="relative flex-1 min-w-[240px]">
            <Icon name="search" size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-stone" />
            <input
              className="w-full pl-10 pr-4 py-2.5 bg-white border border-zinc-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-cobalt/20 focus:border-cobalt/30 transition-all"
              placeholder="Search roles, companies, skills…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <select
            value={sFilter}
            onChange={e => setSFilter(e.target.value)}
            className="px-4 py-2.5 border border-zinc-200 bg-white text-sm rounded-xl focus:outline-none focus:ring-2 focus:ring-cobalt/20 transition-all"
          >
            <option value="all">All statuses</option>
            <option value="pending">Pending</option>
            <option value="applied">Applied</option>
            <option value="interview">Interview</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>

        {/* Filter chips */}
        <div className="flex flex-wrap gap-2 mb-6">
          {CHIP_OPTIONS.map(chip => (
            <button
              key={chip.id}
              onClick={() => toggleChip(chip.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
                activeChips.includes(chip.id)
                  ? 'bg-cobalt text-white'
                  : 'bg-white border border-zinc-200 text-stone hover:border-cobalt/30'
              }`}
            >
              {chip.label}
              {activeChips.includes(chip.id) && (
                <span className="ml-1.5 opacity-70">×</span>
              )}
            </button>
          ))}
          {activeChips.length > 0 && (
            <button
              onClick={() => setActiveChips([])}
              className="text-cobalt text-xs font-semibold px-2 hover:underline"
            >
              Clear all
            </button>
          )}
        </div>

        {/* Results */}
        {filtered.length === 0 ? (
          <div className="text-center py-24 text-stone">
            <Icon name="search_off" size={40} className="opacity-30 mb-4" />
            <p className="font-semibold text-ink">No roles match your filters.</p>
            <p className="text-sm mt-1">Try loosening your search or clearing filters.</p>
          </div>
        ) : (
          <div className="space-y-3 stagger">
            {showTopPick && (
              <TopPickBanner
                job={topPick}
                onView={setResumeJob}
                onMark={onMark}
                onApply={handleApply}
              />
            )}
            {(showTopPick ? rest : filtered).map((job, i) => (
              <JobRow
                key={job.id}
                job={job}
                index={i}
                onView={setResumeJob}
                onMark={onMark}
              />
            ))}
            {filtered.length > 10 && (
              <p className="text-center text-stone text-sm pt-2">
                Showing all {filtered.length} results
              </p>
            )}
          </div>
        )}
      </div>

      <ResumeModal
        open={!!resumeJob}
        onClose={() => setResumeJob(null)}
        pdfUrl={resumeJob ? api.getJobResume(resumeJob.url) : ''}
        title={resumeJob ? `${resumeJob.title} · ${resumeJob.company}` : ''}
      />
    </div>
  )
}
