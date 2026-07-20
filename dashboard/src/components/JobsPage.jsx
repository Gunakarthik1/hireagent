import { useState, useMemo } from 'react'
import Icon from './Icon.jsx'
import { CompanyAvatar, StatusBadge, ResumeModal, useToast } from './UI.jsx'
import { api } from '../api.js'

function MatchBox({ score }) {
  const pct = Math.round(score * 10)
  const { bg, text } = pct >= 90
    ? { bg: 'bg-primary-fixed', text: 'text-primary' }
    : pct >= 80
    ? { bg: 'bg-secondary-fixed', text: 'text-on-secondary-fixed-variant' }
    : { bg: 'bg-surface-container-high', text: 'text-on-surface-variant' }
  return (
    <div className={`inline-flex flex-col items-center p-3 ${bg} rounded-xl min-w-[68px]`}>
      <span className={`${text} font-black text-2xl leading-none`}>{pct}%</span>
      <span className={`${text} text-[9px] font-bold uppercase tracking-tighter opacity-70 mt-0.5`}>Match</span>
    </div>
  )
}

function TopPickCard({ job, onView, onApply, onMark }) {
  const isApplied = ['applied', 'interview', 'rejected'].includes(job.status)
  return (
    <div className="relative overflow-hidden bg-primary text-white border border-primary-container rounded-xl p-8 shadow-xl group">
      <div className="absolute top-4 right-4">
        <span className="flex items-center gap-1.5 px-3 py-1 bg-white/20 backdrop-blur-md rounded-full text-[10px] font-bold uppercase tracking-widest text-white">
          <Icon name="star" size={13} filled />
          Top Pick
        </span>
      </div>
      <div className="flex gap-8 items-center flex-wrap">
        <div className="w-20 h-20 rounded-2xl bg-white flex items-center justify-center text-primary font-black text-3xl flex-shrink-0">
          {job.company[0]}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-2xl font-bold tracking-tight mb-1 truncate">{job.title}</h3>
          <div className="flex items-center gap-5 text-primary-fixed-dim text-sm font-medium flex-wrap gap-y-1">
            <span className="flex items-center gap-1"><Icon name="business" size={16} /> {job.company}</span>
            <span className="flex items-center gap-1"><Icon name="location_on" size={16} /> {job.location}</span>
            {job.salary !== '—' && <span className="flex items-center gap-1"><Icon name="payments" size={16} /> {job.salary}</span>}
          </div>
          <div className="mt-4 flex items-center gap-4">
            <div className="px-4 py-2 bg-white/10 rounded-lg border border-white/20">
              <p className="text-[10px] uppercase font-bold text-primary-fixed/80">Match Strength</p>
              <p className="text-xl font-black">{Math.round(job.ats * 10)}%</p>
            </div>
            {job.tailored_resume_path && (
              <div className="px-4 py-2 bg-white/10 rounded-lg border border-white/20">
                <p className="text-[10px] uppercase font-bold text-primary-fixed/80">Resume</p>
                <p className="text-base font-bold">AI Tailored</p>
              </div>
            )}
          </div>
        </div>
        <div className="flex flex-col gap-3 min-w-[160px]">
          <button
            onClick={() => onApply(job)}
            className="w-full px-6 py-3 bg-white text-primary font-bold rounded-xl hover:bg-slate-100 transition-all active:scale-95 shadow-lg text-sm"
          >
            Apply Now
          </button>
          {job.tailored_resume_path && (
            <button
              onClick={() => onView(job)}
              className="w-full px-6 py-3 bg-primary-container text-white border border-white/20 font-bold rounded-xl hover:bg-white/10 transition-all active:scale-95 text-sm"
            >
              View Resume
            </button>
          )}
          {!isApplied ? (
            <button
              onClick={() => onMark(job, 'applied')}
              className="w-full px-6 py-3 bg-white/10 text-white border border-white/20 font-medium rounded-xl hover:bg-white/20 transition-all text-sm"
            >
              Mark Applied
            </button>
          ) : (
            <button
              onClick={() => onMark(job, 'pending')}
              className="w-full px-6 py-3 bg-white/10 text-white border border-white/20 font-medium rounded-xl hover:bg-white/20 transition-all text-sm"
            >
              Reset
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function JobCard({ job, onView, onApply, onMark }) {
  const isApplied = ['applied', 'interview', 'rejected', 'failed', 'skipped'].includes(job.status)
  return (
    <div className={`bg-white border border-slate-200 rounded-xl p-6 shadow-sm hover:shadow-md transition-all group ${isApplied ? 'opacity-70' : ''}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-5 flex-1 min-w-0">
          <CompanyAvatar company={job.company} size={56} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <h3 className="font-semibold text-lg text-on-surface group-hover:text-primary transition-colors leading-tight">{job.title}</h3>
              <StatusBadge status={job.status} hasTailored={!!job.tailored_resume_path} />
            </div>
            <div className="flex items-center gap-4 text-on-surface-variant text-sm flex-wrap gap-y-0.5">
              <span className="flex items-center gap-1"><Icon name="business" size={16} /> {job.company}</span>
              <span className="flex items-center gap-1"><Icon name="location_on" size={16} /> {job.location}</span>
              {job.salary !== '—' && <span className="flex items-center gap-1"><Icon name="payments" size={16} /> {job.salary}</span>}
            </div>
          </div>
        </div>
        <MatchBox score={job.ats} />
      </div>

      <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-5">
        <div className="flex gap-2 flex-wrap">
          {job.tailored_resume_path && (
            <span className="px-3 py-1 bg-emerald-50 text-emerald-700 rounded-full text-xs font-semibold flex items-center gap-1">
              <Icon name="check_circle" size={14} filled />
              Ready to Apply
            </span>
          )}
          <span className="px-3 py-1 bg-surface-container text-on-surface-variant rounded-full text-xs">
            Posted {job.posted} ago
          </span>
          {job.site && (
            <span className="px-3 py-1 bg-surface-container text-on-surface-variant rounded-full text-xs capitalize">
              {job.site}
            </span>
          )}
        </div>
        <div className="flex gap-2">
          {job.tailored_resume_path && (
            <button
              onClick={() => onView(job)}
              className="px-3 py-1.5 text-primary text-sm font-medium hover:bg-surface-container-low rounded-lg transition-all"
            >
              View Resume
            </button>
          )}
          <button
            onClick={() => onApply(job)}
            className="px-4 py-1.5 border border-outline-variant text-on-surface text-sm font-medium rounded-lg hover:bg-slate-50 transition-all"
          >
            View Details
          </button>
          {!isApplied ? (
            <button
              onClick={() => onMark(job, 'applied')}
              className="px-5 py-1.5 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-dark transition-all active:scale-95 shadow-sm"
            >
              Apply Now
            </button>
          ) : (
            <button
              onClick={() => onMark(job, 'pending')}
              className="px-5 py-1.5 border border-outline-variant text-on-surface text-sm font-medium rounded-lg hover:bg-slate-50 transition-all flex items-center gap-1"
            >
              <Icon name="refresh" size={15} /> Reset
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default function JobsPage({ jobs, versions, companies, onMark, onRefreshJobs, onTailor }) {
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [sFilter, setSFilter] = useState('all')
  const [sort, setSort] = useState('ats')
  const [resumeJob, setResumeJob] = useState(null)
  const [activeChips, setActiveChips] = useState([])

  const CHIP_OPTIONS = [
    { id: '90plus', label: '90%+ Match' },
    { id: 'tailored', label: 'AI Tailored' },
    { id: 'remote', label: 'Remote' },
  ]

  const toggleChip = (id) => {
    setActiveChips(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id])
  }

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
    if (activeChips.includes('90plus')) xs = xs.filter(j => j.ats >= 9)
    if (activeChips.includes('tailored')) xs = xs.filter(j => j.tailored_resume_path)
    if (activeChips.includes('remote')) xs = xs.filter(j => j.location?.toLowerCase().includes('remote'))
    if (sort === 'ats') xs.sort((a, b) => b.ats - a.ats)
    else if (sort === 'recent') xs.sort((a, b) => new Date(b.discovered_at || 0) - new Date(a.discovered_at || 0))
    else if (sort === 'salary') {
      xs.sort((a, b) => {
        const toNum = s => parseInt((s || '0').replace(/\D/g, '')) || 0
        return toNum(b.salary) - toNum(a.salary)
      })
    }
    return xs
  }, [jobs, search, sFilter, sort, activeChips])

  // Top match for "Top Pick" card
  const topPick = filtered[0]
  const rest = filtered.slice(1)

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
    <div className="p-8 max-w-[1440px] mx-auto space-y-6">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold text-primary tracking-tight">Job Feed</h2>
          <p className="text-on-surface-variant mt-1">
            Discovered {jobs.length.toLocaleString()} opportunities based on your profile.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleRescrape}
            className="flex items-center gap-2 px-4 py-2 border border-outline-variant bg-white text-on-surface text-sm font-medium rounded-lg hover:bg-slate-50 transition-all"
          >
            <Icon name="filter_list" size={18} /> Filters
          </button>
          <select
            value={sort}
            onChange={e => setSort(e.target.value)}
            className="flex items-center gap-2 px-4 py-2 border border-outline-variant bg-white text-on-surface text-sm font-medium rounded-lg hover:bg-slate-50 transition-all focus:outline-none focus:ring-2 focus:ring-primary/20"
          >
            <option value="ats">Sort: Match Score</option>
            <option value="recent">Sort: Most Recent</option>
            <option value="salary">Sort: Salary</option>
          </select>
        </div>
      </div>

      {/* Search + Status filter */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[280px]">
          <Icon name="search" size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            className="w-full pl-10 pr-4 py-2 bg-surface-container-low border border-outline-variant rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/30 transition-all"
            placeholder="Search discovered jobs…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <select
          value={sFilter}
          onChange={e => setSFilter(e.target.value)}
          className="px-4 py-2 border border-outline-variant bg-white text-sm rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
        >
          <option value="all">All statuses</option>
          <option value="pending">Pending</option>
          <option value="applied">Applied</option>
          <option value="interview">Interview</option>
          <option value="rejected">Rejected</option>
        </select>
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2">
        {CHIP_OPTIONS.map(chip => (
          <button
            key={chip.id}
            onClick={() => toggleChip(chip.id)}
            className={`px-3 py-1 rounded-full text-xs font-semibold flex items-center gap-1 transition-all ${
              activeChips.includes(chip.id)
                ? 'bg-primary-fixed text-primary border border-primary/30'
                : 'bg-surface-container text-on-surface-variant border border-outline-variant hover:border-primary/30'
            }`}
          >
            {chip.label}
            {activeChips.includes(chip.id) && <Icon name="close" size={13} />}
          </button>
        ))}
        {activeChips.length > 0 && (
          <button
            onClick={() => setActiveChips([])}
            className="text-primary text-xs font-semibold px-2 hover:underline"
          >
            Clear all
          </button>
        )}
      </div>

      {/* Results */}
      {filtered.length === 0 ? (
        <div className="text-center py-20 text-on-surface-variant">
          <Icon name="search_off" size={48} className="opacity-30 mb-4" />
          <p className="font-medium">No jobs match your filters.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Top pick */}
          {topPick && topPick.ats >= 8.5 && (
            <TopPickCard
              job={topPick}
              onView={setResumeJob}
              onApply={handleApply}
              onMark={onMark}
            />
          )}

          {/* Rest of jobs */}
          {(topPick?.ats >= 8.5 ? rest : filtered).map(j => (
            <JobCard
              key={j.id}
              job={j}
              onView={setResumeJob}
              onApply={handleApply}
              onMark={onMark}
            />
          ))}

          {/* Load more hint */}
          {filtered.length > 10 && (
            <div className="text-center pt-4">
              <p className="text-on-surface-variant text-sm">Showing all {filtered.length} results</p>
            </div>
          )}
        </div>
      )}

      <ResumeModal
        open={!!resumeJob}
        onClose={() => setResumeJob(null)}
        pdfUrl={resumeJob ? api.getJobResume(resumeJob.url) : ''}
        title={resumeJob ? `${resumeJob.title} · ${resumeJob.company}` : ''}
      />
    </div>
  )
}
