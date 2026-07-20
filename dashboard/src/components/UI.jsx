import { useState, useEffect, useCallback, createContext, useContext } from 'react'
import Icon from './Icon.jsx'

// ── Match Score Badge ─────────────────────────────────────────────────
export function MatchBadge({ score }) {
  const pct = Math.round(score * 10)
  const cls = pct >= 90
    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
    : pct >= 80
    ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
    : pct >= 70
    ? 'bg-amber-50 text-amber-700 border border-amber-200'
    : 'bg-slate-100 text-slate-600 border border-slate-200'
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-bold ${cls}`}>
      {pct >= 85 && <Icon name="verified" size={13} filled />}
      {pct}% Match
    </span>
  )
}

// ── Match Score Box (larger, for job cards) ───────────────────────────
export function MatchBox({ score }) {
  const pct = Math.round(score * 10)
  const { bg, text } = pct >= 90
    ? { bg: 'bg-primary-fixed', text: 'text-primary' }
    : pct >= 80
    ? { bg: 'bg-secondary-fixed', text: 'text-on-secondary-fixed-variant' }
    : { bg: 'bg-surface-container-high', text: 'text-on-surface-variant' }
  return (
    <div className={`inline-flex flex-col items-center p-3 ${bg} rounded-xl min-w-[60px]`}>
      <span className={`${text} font-black text-2xl leading-none`}>{pct}%</span>
      <span className={`${text} text-[9px] font-bold uppercase tracking-tighter opacity-70 mt-0.5`}>Match</span>
    </div>
  )
}

// ── Status Badge ──────────────────────────────────────────────────────
export function StatusBadge({ status, hasTailored }) {
  const s = status || 'pending'
  if (s === 'interview') return (
    <span className="px-2 py-0.5 bg-green-100 text-green-700 rounded-md text-[10px] font-bold uppercase tracking-wider">Interviewing</span>
  )
  if (s === 'applied') return (
    <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded-md text-[10px] font-bold uppercase tracking-wider">Applied</span>
  )
  if (s === 'rejected') return (
    <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded-md text-[10px] font-bold uppercase tracking-wider">Rejected</span>
  )
  if (hasTailored) return (
    <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-md text-[10px] font-bold uppercase tracking-wider">Tailored</span>
  )
  return (
    <span className="px-2 py-0.5 bg-blue-100 text-blue-700 border border-blue-200 rounded-md text-[10px] font-bold uppercase tracking-wider">Analyzing</span>
  )
}

// ── Company Avatar ────────────────────────────────────────────────────
export function CompanyAvatar({ company, size = 40 }) {
  const colors = [
    'bg-indigo-100 text-indigo-700',
    'bg-emerald-100 text-emerald-700',
    'bg-amber-100 text-amber-700',
    'bg-rose-100 text-rose-700',
    'bg-sky-100 text-sky-700',
    'bg-violet-100 text-violet-700',
  ]
  const idx = (company || '?').charCodeAt(0) % colors.length
  const colorCls = colors[idx]
  const letter = (company || '?')[0].toUpperCase()
  return (
    <div
      className={`flex items-center justify-center rounded-lg font-bold flex-shrink-0 ${colorCls}`}
      style={{ width: size, height: size, fontSize: size * 0.4 }}
    >
      {letter}
    </div>
  )
}

// ── StatusPip (kept for backward compat) ─────────────────────────────
export function StatusPip({ status }) {
  return <StatusBadge status={status} />
}

// ── Resume Modal ──────────────────────────────────────────────────────
export function ResumeModal({ open, onClose, pdfUrl, title }) {
  useEffect(() => {
    if (!open) return
    const onKey = e => e.key === 'Escape' && onClose?.()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="ha-modal-overlay" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden"
        style={{ width: 'min(90vw, 960px)', maxHeight: '90vh', animation: 'slideUp 200ms cubic-bezier(.2,.7,.2,1)' }}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex justify-between items-center px-6 py-4 border-b border-slate-100 bg-slate-50 flex-shrink-0">
          <span className="font-semibold text-sm text-slate-800">{title || 'Tailored Resume'}</span>
          <div className="flex gap-2">
            <a
              className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-white transition-colors"
              href={pdfUrl} download target="_blank" rel="noopener"
            >
              <Icon name="download" size={15} /> Download
            </a>
            <button
              className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              onClick={onClose}
            >
              <Icon name="close" size={18} />
            </button>
          </div>
        </div>
        <iframe src={pdfUrl} className="flex-1 border-none min-h-[600px] bg-white" title="Resume PDF" />
      </div>
    </div>
  )
}

// ── Modal wrapper ─────────────────────────────────────────────────────
export function Modal({ open, onClose, children, width = 720 }) {
  useEffect(() => {
    if (!open) return
    const onKey = e => e.key === 'Escape' && onClose?.()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="ha-modal-overlay" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-2xl overflow-hidden w-full"
        style={{ maxWidth: width, animation: 'slideUp 200ms cubic-bezier(.2,.7,.2,1)' }}
        onClick={e => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}

// ── Tooltip ───────────────────────────────────────────────────────────
export function Tooltip({ children, content, side = 'top' }) {
  const [open, setOpen] = useState(false)
  const posClass = side === 'left'
    ? 'right-full top-1/2 -translate-y-1/2 mr-2'
    : 'bottom-full left-1/2 -translate-x-1/2 mb-2'
  return (
    <span className="relative inline-block" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      {children}
      {open && (
        <span className={`absolute z-50 ${posClass} bg-slate-900 text-white text-xs rounded-lg px-3 py-2 shadow-xl whitespace-nowrap pointer-events-none`}>
          {content}
        </span>
      )}
    </span>
  )
}

// ── ScoreBreakdown ────────────────────────────────────────────────────
export function ScoreBreakdown({ kw, sk, ex, ed }) {
  const rows = [
    { label: 'Keywords',   weight: '40%', value: kw },
    { label: 'Skills',     weight: '30%', value: sk },
    { label: 'Experience', weight: '20%', value: ex },
    { label: 'Education',  weight: '10%', value: ed },
  ]
  return (
    <div className="flex flex-col gap-2 min-w-[200px]">
      {rows.map(r => (
        <div key={r.label} className="space-y-1">
          <div className="flex justify-between text-xs text-slate-500">
            <span>{r.label}</span>
            <span className="font-medium text-slate-700">{r.value || 0}%</span>
          </div>
          <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full bg-primary rounded-full" style={{ width: `${r.value || 0}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ── VersionBadge (kept for backward compat) ───────────────────────────
export function VersionBadge({ id, tone, count, onClick }) {
  if (!id) return null
  const colors = {
    violet: 'bg-violet-100 text-violet-700 border-violet-200',
    emerald: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    sky: 'bg-sky-100 text-sky-700 border-sky-200',
    amber: 'bg-amber-100 text-amber-700 border-amber-200',
    rose: 'bg-rose-100 text-rose-700 border-rose-200',
    teal: 'bg-teal-100 text-teal-700 border-teal-200',
  }
  const colorCls = colors[tone] || colors.violet
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs font-semibold font-mono ${colorCls} ${onClick ? 'cursor-pointer hover:opacity-80' : 'cursor-default'}`}
    >
      <span className="w-4 h-4 rounded flex items-center justify-center bg-current/20 text-[10px] font-bold"
        style={{ background: 'currentColor', color: 'white', opacity: 1 }}
      >{id}</span>
      {count != null && <span className="opacity-70">· {count}</span>}
    </button>
  )
}

// ── Toast ─────────────────────────────────────────────────────────────
const ToastCtx = createContext(null)

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((msg, opts = {}) => {
    const id = Math.random().toString(36).slice(2)
    setItems(xs => [...xs, { id, msg, ...opts }])
    setTimeout(() => setItems(xs => xs.filter(x => x.id !== id)), opts.duration || 3200)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="ha-toast-stack">
        {items.map(t => (
          <div key={t.id} className={`ha-toast${t.kind ? ` ha-toast--${t.kind}` : ''}`}>
            {t.icon && <Icon name={t.icon} size={15} />}
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
