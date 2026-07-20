import { useState } from 'react'
import Icon from './Icon.jsx'
import { useToast } from './UI.jsx'
import { api } from '../api.js'

// Color palette per folder index
const FOLDER_COLORS = [
  { bg: 'bg-indigo-50',  border: 'border-indigo-200',  icon: 'text-indigo-500',  badge: 'bg-indigo-100 text-indigo-700',  bar: 'bg-indigo-500',  ring: 'ring-indigo-300',  active: 'bg-indigo-500' },
  { bg: 'bg-emerald-50', border: 'border-emerald-200', icon: 'text-emerald-500', badge: 'bg-emerald-100 text-emerald-700', bar: 'bg-emerald-500', ring: 'ring-emerald-300', active: 'bg-emerald-500' },
  { bg: 'bg-sky-50',     border: 'border-sky-200',     icon: 'text-sky-500',     badge: 'bg-sky-100 text-sky-700',         bar: 'bg-sky-500',     ring: 'ring-sky-300',     active: 'bg-sky-500' },
  { bg: 'bg-amber-50',   border: 'border-amber-200',   icon: 'text-amber-500',   badge: 'bg-amber-100 text-amber-700',     bar: 'bg-amber-500',   ring: 'ring-amber-300',   active: 'bg-amber-500' },
  { bg: 'bg-rose-50',    border: 'border-rose-200',    icon: 'text-rose-500',    badge: 'bg-rose-100 text-rose-700',       bar: 'bg-rose-500',    ring: 'ring-rose-300',    active: 'bg-rose-500' },
  { bg: 'bg-teal-50',    border: 'border-teal-200',    icon: 'text-teal-500',    badge: 'bg-teal-100 text-teal-700',       bar: 'bg-teal-500',    ring: 'ring-teal-300',    active: 'bg-teal-500' },
]

function getColor(idx) {
  return FOLDER_COLORS[idx % FOLDER_COLORS.length]
}

function scoreBadge(pct) {
  if (pct >= 90) return 'bg-emerald-100 text-emerald-700 border border-emerald-200'
  if (pct >= 80) return 'bg-blue-100 text-blue-700 border border-blue-200'
  if (pct >= 70) return 'bg-amber-100 text-amber-700 border border-amber-200'
  return 'bg-slate-100 text-slate-600 border border-slate-200'
}

function statusDot(status) {
  if (status === 'applied')   return 'bg-blue-400'
  if (status === 'interview') return 'bg-emerald-400'
  if (status === 'rejected')  return 'bg-red-400'
  return 'bg-slate-300'
}

// ── Folder Card ───────────────────────────────────────────────────────────
function FolderCard({ version, jobs, colorIdx, isOpen, onClick }) {
  const c = getColor(colorIdx)
  const vJobs = jobs.filter(j => j.version === version.id)
  const avgPct = vJobs.length
    ? Math.round((vJobs.reduce((s, j) => s + j.ats, 0) / vJobs.length) * 10)
    : Math.round(version.avg_score * 10)

  return (
    <button
      onClick={onClick}
      className={`group relative w-full text-left rounded-2xl border-2 transition-all duration-200 overflow-hidden ${
        isOpen
          ? `${c.border} shadow-xl ring-2 ${c.ring} scale-[1.02]`
          : `border-transparent hover:${c.border} hover:shadow-lg bg-white shadow-sm hover:scale-[1.01]`
      }`}
    >
      {/* Folder tab */}
      <div className={`h-1.5 w-full ${isOpen ? c.active : 'bg-slate-200 group-hover:' + c.active} transition-colors`} />

      <div className={`p-5 ${isOpen ? c.bg : 'bg-white group-hover:' + c.bg} transition-colors`}>
        {/* Folder icon + open/closed */}
        <div className="flex items-start justify-between mb-4">
          <div className={`p-3 rounded-xl ${isOpen ? c.bg : 'bg-slate-100 group-hover:' + c.bg} transition-colors`}>
            <Icon
              name={isOpen ? 'folder_open' : 'folder'}
              size={32}
              className={isOpen ? c.icon : 'text-slate-400 group-hover:' + c.icon}
              filled={isOpen}
            />
          </div>
          {isOpen && (
            <span className={`text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded-full ${c.badge}`}>
              Open
            </span>
          )}
        </div>

        {/* Name */}
        <h3 className="font-bold text-base text-on-surface leading-tight mb-1">{version.name}</h3>
        <p className="text-xs text-on-surface-variant truncate mb-4">{version.tagline}</p>

        {/* Stats row */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 text-xs font-semibold text-on-surface-variant">
            <Icon name="work" size={13} />
            <span>{vJobs.length} jobs</span>
          </div>
          <div className={`ml-auto px-2 py-0.5 rounded-full text-xs font-bold ${scoreBadge(avgPct)}`}>
            {avgPct}% avg
          </div>
        </div>

        {/* Mini job preview dots */}
        {vJobs.length > 0 && (
          <div className="flex gap-1 mt-3 flex-wrap">
            {vJobs.slice(0, 5).map(j => (
              <div
                key={j.id}
                className={`w-2 h-2 rounded-full ${statusDot(j.status)}`}
                title={`${j.company} · ${j.status}`}
              />
            ))}
            {vJobs.length > 5 && (
              <span className="text-[10px] text-slate-400 font-medium">+{vJobs.length - 5}</span>
            )}
          </div>
        )}

        {/* Updated */}
        <p className="text-[10px] text-slate-400 mt-3">Updated {version.updated}</p>
      </div>
    </button>
  )
}

// ── Folder Detail (inline expand) ─────────────────────────────────────────
function FolderDetail({ version, jobs, colorIdx, onClose }) {
  const c = getColor(colorIdx)
  const vJobs = [...jobs.filter(j => j.version === version.id)].sort((a, b) => b.ats - a.ats)

  return (
    <div className={`col-span-full rounded-2xl border-2 ${c.border} overflow-hidden shadow-lg animate-fade-in`}>
      {/* Header */}
      <div className={`${c.bg} border-b ${c.border} px-8 py-5 flex items-center justify-between`}>
        <div className="flex items-center gap-4">
          <div className={`p-2.5 rounded-xl bg-white shadow-sm`}>
            <Icon name="folder_open" size={28} className={c.icon} filled />
          </div>
          <div>
            <h3 className="font-bold text-xl text-on-surface">{version.name}</h3>
            <p className="text-sm text-on-surface-variant mt-0.5">{vJobs.length} job{vJobs.length !== 1 ? 's' : ''} matched · {version.tagline}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {version.resume_pdf_path && (
            <>
              <a
                href={api.getVersionPdf(version.id)}
                target="_blank" rel="noopener"
                className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 text-sm font-medium text-on-surface rounded-lg hover:bg-slate-50 transition-all shadow-sm"
              >
                <Icon name="visibility" size={16} /> Preview Resume
              </a>
              <a
                href={api.getVersionPdf(version.id)}
                download={`Resume_${version.name.replace(/ /g, '_')}.pdf`}
                className={`flex items-center gap-2 px-4 py-2 text-white text-sm font-semibold rounded-lg transition-all active:scale-95 shadow-sm ${c.active}`}
              >
                <Icon name="download" size={16} /> Download PDF
              </a>
            </>
          )}
          {!version.resume_pdf_path && (
            <span className="flex items-center gap-1.5 text-xs text-slate-400 italic">
              <Icon name="info" size={14} /> No PDF yet
            </span>
          )}
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-slate-700 hover:bg-white rounded-lg transition-all"
          >
            <Icon name="close" size={20} />
          </button>
        </div>
      </div>

      {/* Skills chips */}
      {version.skills.length > 0 && (
        <div className="px-8 py-4 bg-white border-b border-slate-100 flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mr-1">Resume focus:</span>
          {version.skills.map(s => (
            <span key={s} className={`px-2.5 py-1 rounded-full text-xs font-semibold ${c.badge}`}>{s}</span>
          ))}
        </div>
      )}

      {/* Job list */}
      {vJobs.length > 0 ? (
        <div className="bg-white">
          <div className="px-8 py-3 bg-slate-50 border-b border-slate-100 grid grid-cols-12 gap-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
            <div className="col-span-5">Company & Role</div>
            <div className="col-span-2">Match</div>
            <div className="col-span-2">Status</div>
            <div className="col-span-2">Posted</div>
            <div className="col-span-1 text-right">Apply</div>
          </div>
          <div className="divide-y divide-slate-100">
            {vJobs.map((j, i) => {
              const pct = Math.round(j.ats * 10)
              return (
                <div key={j.id} className="px-8 py-4 grid grid-cols-12 gap-4 items-center hover:bg-slate-50 transition-colors group">
                  {/* Company + Role */}
                  <div className="col-span-5 flex items-center gap-3 min-w-0">
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center font-bold text-sm flex-shrink-0 text-white ${c.active}`}>
                      {j.company[0]}
                    </div>
                    <div className="min-w-0">
                      <div className="font-semibold text-sm text-on-surface truncate group-hover:text-primary transition-colors">
                        {j.company}
                      </div>
                      <div className="text-xs text-on-surface-variant truncate">{j.title}</div>
                    </div>
                  </div>

                  {/* Match score */}
                  <div className="col-span-2 flex items-center gap-2">
                    <div className="flex-1 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${c.bar}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${scoreBadge(pct)}`}>{pct}%</span>
                  </div>

                  {/* Status */}
                  <div className="col-span-2">
                    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold capitalize
                      ${j.status === 'applied'   ? 'bg-blue-50 text-blue-700' :
                        j.status === 'interview' ? 'bg-emerald-50 text-emerald-700' :
                        j.status === 'rejected'  ? 'bg-red-50 text-red-700' :
                        'bg-slate-100 text-slate-600'}`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${statusDot(j.status)}`} />
                      {j.status}
                    </span>
                  </div>

                  {/* Posted */}
                  <div className="col-span-2 text-xs text-on-surface-variant">{j.posted} ago</div>

                  {/* Apply button */}
                  <div className="col-span-1 text-right">
                    <a
                      href={j.application_url}
                      target="_blank"
                      rel="noopener"
                      className={`inline-flex items-center gap-1 px-3 py-1.5 text-white text-xs font-semibold rounded-lg transition-all active:scale-95 hover:opacity-90 ${c.active}`}
                      onClick={e => e.stopPropagation()}
                    >
                      Apply <Icon name="open_in_new" size={12} />
                    </a>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        <div className="bg-white px-8 py-12 text-center text-on-surface-variant">
          <Icon name="work_off" size={32} className="opacity-30 mb-3 mx-auto" />
          <p className="text-sm">No jobs assigned to this branch yet.</p>
          <p className="text-xs mt-1 text-slate-400">Run the pipeline to match jobs against this resume version.</p>
        </div>
      )}
    </div>
  )
}

// ── Empty state: no versions yet ──────────────────────────────────────────
function EmptyState({ jobs, onAssign, assigning }) {
  const unassigned = jobs.filter(j => j.tailored_resume_path && !j.version)
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center px-8">
      <div className="w-24 h-24 rounded-3xl bg-primary-fixed flex items-center justify-center mb-6 shadow-lg">
        <Icon name="folder_open" size={48} className="text-primary" />
      </div>
      <h2 className="text-2xl font-bold text-on-surface mb-2">No resume branches yet</h2>
      <p className="text-on-surface-variant max-w-md mb-2">
        {unassigned.length > 0
          ? `You have ${unassigned.length} tailored resumes ready to be clustered into branches.`
          : 'Run the full pipeline first — the AI will discover jobs, score them, and tailor resumes.'}
      </p>
      <p className="text-sm text-on-surface-variant max-w-md mb-8">
        Each branch is a resume version (e.g. "Backend SWE", "ML Engineer"). Jobs scoring ≥ threshold get placed in the right folder automatically.
      </p>
      {unassigned.length > 0 && (
        <button
          onClick={onAssign}
          disabled={assigning}
          className="flex items-center gap-3 bg-primary text-white px-8 py-4 rounded-xl font-semibold text-base shadow-xl hover:bg-primary-dark transition-all active:scale-95 disabled:opacity-60"
        >
          <Icon name="auto_awesome" size={22} filled />
          {assigning ? 'Creating branches…' : 'Create Resume Branches'}
        </button>
      )}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────
export default function VersionsPage({ versions, jobs, onRefreshVersions }) {
  const toast = useToast()
  const [openId, setOpenId] = useState(null)
  const [assigning, setAssigning] = useState(false)

  const handleAssign = async () => {
    setAssigning(true)
    try {
      await api.assignVersions(false)
      toast('Creating resume branches — this takes a minute', { kind: 'info', icon: 'auto_awesome' })
      setTimeout(onRefreshVersions, 8000)
    } catch (e) {
      toast('Error: ' + e.message, { kind: 'err', icon: 'error' })
    } finally {
      setAssigning(false)
    }
  }

  const toggleFolder = (id) => setOpenId(prev => prev === id ? null : id)

  const totalJobs = versions.reduce((s, v) => s + jobs.filter(j => j.version === v.id).length, 0)
  const unassigned = jobs.filter(j => !j.version && j.tailored_resume_path).length

  return (
    <div className="p-8 max-w-[1440px] mx-auto">
      {/* Header */}
      <div className="flex items-end justify-between mb-8">
        <div>
          <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-1">Resume Board</p>
          <h1 className="text-3xl font-bold text-on-surface tracking-tight">Resume Branches</h1>
          <p className="text-on-surface-variant mt-1">
            Each folder is a resume version. Jobs scoring above your threshold get placed automatically.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {unassigned > 0 && (
            <span className="text-xs font-semibold px-3 py-1.5 bg-amber-50 text-amber-700 border border-amber-200 rounded-full">
              {unassigned} unassigned
            </span>
          )}
          <button
            onClick={handleAssign}
            disabled={assigning}
            className="flex items-center gap-2 px-5 py-2.5 bg-primary text-white font-semibold text-sm rounded-xl hover:bg-primary-dark transition-all active:scale-95 disabled:opacity-60 shadow-sm"
          >
            <Icon name="auto_awesome" size={17} filled />
            {assigning ? 'Creating…' : 'Run Assignment'}
          </button>
        </div>
      </div>

      {/* Stats strip */}
      {versions.length > 0 && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="bg-white border border-outline-variant rounded-xl p-4 flex items-center gap-3 shadow-sm">
            <div className="p-2 bg-primary-fixed rounded-lg">
              <Icon name="folder" size={20} className="text-primary" filled />
            </div>
            <div>
              <p className="text-xs text-on-surface-variant font-medium">Resume Branches</p>
              <p className="text-2xl font-bold text-on-surface">{versions.length}</p>
            </div>
          </div>
          <div className="bg-white border border-outline-variant rounded-xl p-4 flex items-center gap-3 shadow-sm">
            <div className="p-2 bg-secondary-container rounded-lg">
              <Icon name="work" size={20} className="text-secondary" />
            </div>
            <div>
              <p className="text-xs text-on-surface-variant font-medium">Jobs Assigned</p>
              <p className="text-2xl font-bold text-on-surface">{totalJobs}</p>
            </div>
          </div>
          <div className="bg-white border border-outline-variant rounded-xl p-4 flex items-center gap-3 shadow-sm">
            <div className="p-2 bg-tertiary-fixed rounded-lg">
              <Icon name="analytics" size={20} className="text-tertiary" />
            </div>
            <div>
              <p className="text-xs text-on-surface-variant font-medium">Avg Match</p>
              <p className="text-2xl font-bold text-on-surface">
                {versions.length
                  ? Math.round(versions.reduce((s, v) => s + Math.round(v.avg_score * 10), 0) / versions.length)
                  : 0}%
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {versions.length === 0 && (
        <EmptyState jobs={jobs} onAssign={handleAssign} assigning={assigning} />
      )}

      {/* Folder grid */}
      {versions.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
          {versions.map((v, i) => (
            <>
              <FolderCard
                key={v.id}
                version={v}
                jobs={jobs}
                colorIdx={i}
                isOpen={openId === v.id}
                onClick={() => toggleFolder(v.id)}
              />
              {/* Inline expand — full row after clicked folder */}
              {openId === v.id && (
                <FolderDetail
                  key={`detail-${v.id}`}
                  version={v}
                  jobs={jobs}
                  colorIdx={i}
                  onClose={() => setOpenId(null)}
                />
              )}
            </>
          ))}

          {/* Add new branch placeholder */}
          <button
            onClick={handleAssign}
            disabled={assigning}
            className="group border-2 border-dashed border-slate-200 rounded-2xl flex flex-col items-center justify-center p-8 text-center hover:border-primary/40 hover:bg-surface-container-low transition-all min-h-[220px] disabled:opacity-50"
          >
            <div className="w-14 h-14 rounded-2xl bg-slate-100 group-hover:bg-primary-fixed flex items-center justify-center mb-3 transition-colors">
              <Icon name="add" size={28} className="text-slate-400 group-hover:text-primary transition-colors" />
            </div>
            <p className="font-semibold text-slate-500 group-hover:text-primary transition-colors text-sm">
              {assigning ? 'Creating branches…' : 'New Branch'}
            </p>
            <p className="text-slate-400 text-xs mt-1">Run assignment pipeline</p>
          </button>
        </div>
      )}
    </div>
  )
}
