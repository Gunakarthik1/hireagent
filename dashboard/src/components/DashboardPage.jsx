import { useState, useEffect, useCallback } from 'react'
import Icon from './Icon.jsx'
import { CompanyAvatar, MatchBadge } from './UI.jsx'
import { api } from '../api.js'

function StatCard({ label, value, sub, icon, iconBg, iconColor, badge, badgeColor }) {
  return (
    <div className="bg-white p-6 rounded-xl border border-outline-variant shadow-sm hover:shadow-md transition-all group">
      <div className="flex justify-between items-start mb-4">
        <div className={`p-3 ${iconBg} rounded-lg ${iconColor} group-hover:scale-110 transition-transform`}>
          <Icon name={icon} size={22} />
        </div>
        {badge && (
          <span className={`text-xs font-semibold px-2 py-1 rounded-full ${badgeColor}`}>{badge}</span>
        )}
      </div>
      <p className="text-on-surface-variant text-sm font-medium">{label}</p>
      <h3 className="text-3xl font-bold text-on-surface mt-1 tracking-tight">{value ?? '—'}</h3>
      {sub && <p className="text-xs text-on-surface-variant mt-1">{sub}</p>}
    </div>
  )
}

function FunnelBar({ label, count, pct, color, indent = 0 }) {
  return (
    <div style={{ paddingLeft: `${indent}%`, paddingRight: `${indent}%` }}>
      <div className="flex justify-between items-end mb-2">
        <span className="text-sm font-medium text-on-surface">{label}</span>
        <span className="text-xs text-on-surface-variant font-medium">{count.toLocaleString()}</span>
      </div>
      <div className="w-full bg-surface-container h-8 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all duration-700`} style={{ width: '100%' }} />
      </div>
    </div>
  )
}

function ActiveScans({ scanStatus, onScan, scanning }) {
  const stages = scanStatus?.stages || []
  const stageNames = ['discover', 'score', 'tailor', 'apply']
  const stageMeta = {
    discover: { label: 'Job Discovery',   icon: 'travel_explore' },
    score:    { label: 'AI Scoring',       icon: 'analytics' },
    tailor:   { label: 'Resume Tailoring', icon: 'edit_note' },
    apply:    { label: 'Auto-Apply',       icon: 'send' },
  }

  const stageMap = Object.fromEntries(stages.map(s => [s.name, s]))

  const active = stages.filter(s => s.status === 'running')

  return (
    <div className="bg-white p-8 rounded-xl border border-outline-variant shadow-sm">
      <div className="flex justify-between items-center mb-6">
        <h3 className="text-lg font-semibold text-on-surface">Pipeline Status</h3>
        {scanStatus?.scanning && (
          <span className="flex items-center gap-1.5 text-xs font-bold text-primary bg-primary-fixed px-2.5 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
            LIVE
          </span>
        )}
      </div>

      <div className="space-y-3">
        {stageNames.map(name => {
          const s = stageMap[name] || { name, status: 'idle' }
          const meta = stageMeta[name]
          const isRunning = s.status === 'running'
          const isDone = s.status === 'done'
          const isError = s.status === 'error'

          return (
            <div key={name} className="p-4 bg-surface-container-low rounded-xl border border-outline-variant hover:bg-surface-container transition-colors">
              <div className="flex justify-between items-start mb-2">
                <div className="flex items-center gap-2">
                  <Icon name={meta.icon} size={16} className="text-on-surface-variant" />
                  <p className="text-sm font-medium text-on-surface">{meta.label}</p>
                </div>
                <span className={`text-xs font-semibold ${
                  isRunning ? 'text-primary' :
                  isDone ? 'text-emerald-600' :
                  isError ? 'text-red-600' :
                  'text-on-surface-variant'
                }`}>
                  {isRunning ? 'Running' : isDone ? 'Done' : isError ? 'Error' : 'Idle'}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex-1 bg-surface-variant h-1.5 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      isDone ? 'bg-emerald-500' :
                      isRunning ? 'bg-primary' :
                      isError ? 'bg-red-500' :
                      'bg-transparent'
                    }`}
                    style={{ width: isDone ? '100%' : isRunning ? '65%' : '0%' }}
                  />
                </div>
                {isDone && s.count != null && (
                  <span className="text-xs text-on-surface-variant font-medium">{s.count}</span>
                )}
                {isRunning && (
                  <span className="text-xs text-primary font-medium">…</span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {stages.length === 0 && !scanStatus?.scanning && (
        <div className="text-center py-4 text-on-surface-variant text-sm">
          No scan has run yet.
        </div>
      )}
    </div>
  )
}

function TopMatchCard({ job, onApply }) {
  const pct = Math.round(job.ats * 10)
  return (
    <div className="group border border-outline-variant rounded-xl p-5 hover:border-primary hover:shadow-md transition-all relative bg-white">
      <div className="flex gap-4 items-center mb-4">
        <CompanyAvatar company={job.company} size={48} />
        <div className="flex-1 min-w-0">
          <h4 className="font-semibold text-sm text-on-surface truncate">{job.title}</h4>
          <p className="text-xs text-on-surface-variant mt-0.5">{job.company} · {job.location}</p>
        </div>
        <div className="text-right flex-shrink-0">
          <div className="text-primary font-black text-xl">{pct}%</div>
          <div className="text-[10px] text-on-surface-variant font-bold uppercase tracking-tighter">Match</div>
        </div>
      </div>

      {job.tags.length > 0 && (
        <div className="flex gap-1.5 mb-4 flex-wrap">
          {job.tags.slice(0, 3).map(t => (
            <span key={t} className="px-2 py-0.5 bg-surface-container text-on-surface-variant text-[11px] rounded-md">{t}</span>
          ))}
          {job.tailored_resume_path && (
            <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 text-[11px] font-bold rounded-md">AI Tailored</span>
          )}
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-on-surface-variant">{job.posted} ago</span>
        <button
          onClick={() => onApply(job)}
          className="px-4 py-1.5 bg-primary text-white text-xs font-semibold rounded-lg opacity-0 group-hover:opacity-100 transition-all active:scale-95 hover:bg-primary-dark"
        >
          Apply Now
        </button>
      </div>
    </div>
  )
}

export default function DashboardPage({ stats, jobs, versions, onGoToJobs }) {
  const [scanStatus, setScanStatus] = useState(null)
  const [scanning, setScanning] = useState(false)

  const fetchScan = useCallback(async () => {
    try { setScanStatus(await api.getScanStatus()) } catch {}
  }, [])

  useEffect(() => {
    fetchScan()
    const t = setInterval(fetchScan, scanStatus?.scanning ? 3000 : 10000)
    return () => clearInterval(t)
  }, [fetchScan, scanStatus?.scanning])

  const handleApply = (job) => {
    window.open(job.application_url, '_blank', 'noopener')
  }

  const total      = stats?.total || 0
  const applied    = stats?.applied || 0
  const avgAts     = jobs.length ? Math.round((jobs.reduce((s, j) => s + j.ats, 0) / jobs.length) * 10) : 0
  const interviews = jobs.filter(j => j.status === 'interview').length
  const screened   = stats?.high_fit || jobs.filter(j => j.ats >= 7).length
  const tailored   = stats?.tailored || jobs.filter(j => j.tailored_resume_path).length

  const topMatches = [...jobs].sort((a, b) => b.ats - a.ats).slice(0, 3)

  const funnelStages = [
    { label: 'Discovered',     count: total,     color: 'bg-primary',        indent: 0 },
    { label: 'Agent Screened', count: screened,  color: 'bg-primary/80',     indent: 5 },
    { label: 'Applied',        count: applied,   color: 'bg-primary/60',     indent: 15 },
    { label: 'Interviews',     count: interviews, color: 'bg-primary/40',    indent: 30 },
  ]

  return (
    <div className="p-8 space-y-8 max-w-[1440px] mx-auto">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold text-on-surface tracking-tight">Agent Overview</h2>
          <p className="text-on-surface-variant mt-1">
            Your autonomous job search is monitoring {total.toLocaleString()} discovered opportunities.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={onGoToJobs}
            className="flex items-center gap-2 px-4 py-2 border border-outline-variant bg-white text-on-surface text-sm font-medium rounded-lg hover:bg-surface-container transition-all"
          >
            <Icon name="filter_list" size={18} />
            View All Jobs
          </button>
          <button className="flex items-center gap-2 px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-dark transition-all active:scale-95">
            <Icon name="download" size={18} />
            Quick Export
          </button>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          label="Jobs Found"
          value={total.toLocaleString()}
          icon="travel_explore"
          iconBg="bg-primary-fixed"
          iconColor="text-primary"
          badge="+12% vs last week"
          badgeColor="text-green-600 bg-green-50"
        />
        <StatCard
          label="Applications Sent"
          value={applied}
          icon="send"
          iconBg="bg-secondary-container"
          iconColor="text-secondary"
          badge={`+${Math.max(0, applied)} total`}
          badgeColor="text-green-600 bg-green-50"
        />
        <StatCard
          label="Avg. ATS Score"
          value={`${avgAts}%`}
          icon="analytics"
          iconBg="bg-tertiary-fixed"
          iconColor="text-tertiary"
          badge="Optimized"
          badgeColor="text-amber-600 bg-amber-50"
        />
        <StatCard
          label="Interviews Secured"
          value={interviews}
          icon="event_repeat"
          iconBg="bg-surface-container-high"
          iconColor="text-on-surface-variant"
          badge="48h Response"
          badgeColor="text-primary bg-primary-fixed"
        />
      </div>

      {/* Funnel + Scans */}
      <div className="grid grid-cols-12 gap-6">
        {/* Funnel */}
        <div className="col-span-12 lg:col-span-8 bg-white p-8 rounded-xl border border-outline-variant shadow-sm">
          <div className="flex justify-between items-center mb-8">
            <div>
              <h3 className="text-xl font-semibold text-on-surface">Application Funnel</h3>
              <p className="text-on-surface-variant text-sm mt-0.5">Conversion rates through hiring stages</p>
            </div>
            <select className="bg-surface-container border-none rounded-lg text-sm text-on-surface px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary/20">
              <option>All Time</option>
              <option>Last 30 Days</option>
            </select>
          </div>
          <div className="space-y-5">
            {funnelStages.map(f => (
              <FunnelBar key={f.label} {...f} />
            ))}
          </div>
        </div>

        {/* Active Scans */}
        <div className="col-span-12 lg:col-span-4">
          <ActiveScans scanStatus={scanStatus} scanning={scanning} />
        </div>
      </div>

      {/* High Match Opportunities */}
      {topMatches.length > 0 && (
        <div className="bg-white p-8 rounded-xl border border-outline-variant shadow-sm">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h3 className="text-lg font-semibold text-on-surface">High Matching Opportunities</h3>
              <p className="text-on-surface-variant text-sm mt-0.5">AI-vetted positions with ATS compatibility &gt;80%</p>
            </div>
            <button onClick={onGoToJobs} className="text-primary font-semibold text-sm hover:underline flex items-center gap-1">
              View All Matches <Icon name="arrow_forward" size={16} />
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {topMatches.map(j => (
              <TopMatchCard key={j.id} job={j} onApply={handleApply} />
            ))}
          </div>
        </div>
      )}

      {jobs.length === 0 && (
        <div className="text-center py-20 text-on-surface-variant">
          <Icon name="travel_explore" size={48} className="opacity-30 mb-4" />
          <p className="text-lg font-medium">No jobs yet</p>
          <p className="text-sm mt-1">Hit "Run Scan" in the sidebar to start discovering opportunities.</p>
        </div>
      )}
    </div>
  )
}
