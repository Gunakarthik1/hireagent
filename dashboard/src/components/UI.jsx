import { useState, useEffect, useCallback, createContext, useContext } from 'react'
import Icon from './Icon.jsx'

// ── Match Score Badge (used across components) ────────────────────────────────
export function MatchBadge({ score }) {
  const s = Number(score) || 0
  if (s >= 8) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
      {s.toFixed(1)}
    </span>
  )
  if (s >= 6) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-amber-50 text-amber-700 border border-amber-200">
      {s.toFixed(1)}
    </span>
  )
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-zinc-100 text-stone border border-zinc-200">
      {s.toFixed(1)}
    </span>
  )
}

// ── Match Score Box ───────────────────────────────────────────────────────────
export function MatchBox({ score }) {
  const s = Number(score) || 0
  const { bg, text } = s >= 8
    ? { bg: 'bg-emerald-50 border-emerald-200', text: 'text-emerald-700' }
    : s >= 6
    ? { bg: 'bg-amber-50 border-amber-200',   text: 'text-amber-700' }
    : { bg: 'bg-zinc-100 border-zinc-200',    text: 'text-stone' }
  return (
    <div className={`inline-flex flex-col items-center p-3 ${bg} border rounded-xl min-w-[60px]`}>
      <span className={`${text} font-bold text-xl leading-none tabular-nums`}>{s.toFixed(1)}</span>
      <span className={`${text} text-[9px] font-semibold uppercase tracking-tight opacity-60 mt-1`}>Score</span>
    </div>
  )
}

// ── Status Badge ──────────────────────────────────────────────────────────────
export function StatusBadge({ status, hasTailored }) {
  const s = status || 'pending'
  if (s === 'interview') return (
    <span className="px-2.5 py-0.5 bg-emerald-50 text-emerald-700 rounded-full text-[11px] font-semibold border border-emerald-200">Interviewing</span>
  )
  if (s === 'applied') return (
    <span className="px-2.5 py-0.5 bg-cobalt text-white rounded-full text-[11px] font-semibold">Applied</span>
  )
  if (s === 'rejected') return (
    <span className="px-2.5 py-0.5 bg-zinc-100 text-stone rounded-full text-[11px] font-semibold">Passed</span>
  )
  if (hasTailored) return (
    <span className="px-2.5 py-0.5 bg-emerald-50 text-emerald-700 rounded-full text-[11px] font-semibold border border-emerald-200">Tailored</span>
  )
  return (
    <span className="px-2.5 py-0.5 bg-cobalt-mid text-cobalt rounded-full text-[11px] font-semibold">New</span>
  )
}

// ── Company Avatar ────────────────────────────────────────────────────────────
export function CompanyAvatar({ company, size = 40 }) {
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

// ── StatusPip (compat alias) ──────────────────────────────────────────────────
export function StatusPip({ status }) {
  return <StatusBadge status={status} />
}

// ── Resume Modal ──────────────────────────────────────────────────────────────
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
        <div className="flex justify-between items-center px-6 py-4 border-b border-zinc-100 bg-paper flex-shrink-0">
          <span className="font-semibold text-sm text-ink">{title || 'Tailored Resume'}</span>
          <div className="flex gap-2">
            <a
              className="flex items-center gap-1.5 px-3 py-1.5 border border-zinc-200 rounded-lg text-sm text-ink hover:bg-paper transition-colors"
              href={pdfUrl} download target="_blank" rel="noopener"
            >
              <Icon name="download" size={15} /> Download
            </a>
            <button
              className="p-1.5 text-stone hover:text-ink hover:bg-zinc-50 rounded-lg transition-colors"
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

// ── Modal wrapper ─────────────────────────────────────────────────────────────
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

// ── Tooltip ───────────────────────────────────────────────────────────────────
export function Tooltip({ children, content, side = 'top' }) {
  const [open, setOpen] = useState(false)
  const posClass = side === 'left'
    ? 'right-full top-1/2 -translate-y-1/2 mr-2'
    : 'bottom-full left-1/2 -translate-x-1/2 mb-2'
  return (
    <span className="relative inline-block" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      {children}
      {open && (
        <span className={`absolute z-50 ${posClass} bg-ink text-paper text-xs rounded-lg px-3 py-2 shadow-xl whitespace-nowrap pointer-events-none`}>
          {content}
        </span>
      )}
    </span>
  )
}

// ── Score Breakdown ───────────────────────────────────────────────────────────
export function ScoreBreakdown({ kw, sk, ex, ed }) {
  const rows = [
    { label: 'Keywords',   value: kw },
    { label: 'Skills',     value: sk },
    { label: 'Experience', value: ex },
    { label: 'Education',  value: ed },
  ]
  return (
    <div className="flex flex-col gap-2 min-w-[200px]">
      {rows.map(r => (
        <div key={r.label} className="space-y-1">
          <div className="flex justify-between text-xs text-stone">
            <span>{r.label}</span>
            <span className="font-medium text-ink">{r.value || 0}%</span>
          </div>
          <div className="h-1.5 bg-zinc-100 rounded-full overflow-hidden">
            <div className="h-full bg-cobalt rounded-full" style={{ width: `${r.value || 0}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Version Badge ─────────────────────────────────────────────────────────────
export function VersionBadge({ id, tone, count, onClick }) {
  if (!id) return null
  const colors = {
    violet: 'bg-violet-100 text-violet-700 border-violet-200',
    emerald: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    sky:    'bg-sky-100 text-sky-700 border-sky-200',
    amber:  'bg-amber-100 text-amber-700 border-amber-200',
    rose:   'bg-rose-100 text-rose-700 border-rose-200',
    teal:   'bg-teal-100 text-teal-700 border-teal-200',
  }
  const colorCls = colors[tone] || colors.violet
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs font-semibold font-mono ${colorCls} ${onClick ? 'cursor-pointer hover:opacity-80' : 'cursor-default'}`}
    >
      <span className="w-4 h-4 rounded flex items-center justify-center text-[10px] font-bold bg-current/20">
        {id}
      </span>
      {count != null && <span className="opacity-70">· {count}</span>}
    </button>
  )
}

// ── Toast ─────────────────────────────────────────────────────────────────────
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
