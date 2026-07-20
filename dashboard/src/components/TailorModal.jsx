import { useState, useEffect } from 'react'
import Icon from './Icon.jsx'
import { Modal, useToast } from './UI.jsx'
import { api } from '../api.js'

const SAMPLE_JD = `Software Engineer, Backend
At Lumen AI, we're building infrastructure for the next generation of agentic systems...
Responsibilities:
- Design and ship distributed services in Go or Python
- Own observability, on-call, and incident response
- Collaborate with research on inference platform
Requirements: 2+ years backend, Postgres, Kubernetes, distributed systems experience.`

const scoreColor = (s) =>
  s >= 8.5 ? '#10b981' : s >= 7 ? '#f59e0b' : '#ef4444'

export default function TailorModal({ open, onClose, versions, onCreated }) {
  const toast = useToast()
  const [step, setStep] = useState(0)
  const [scores, setScores] = useState([])
  const [decision, setDecision] = useState(null)
  const [pasted, setPasted] = useState('')
  const [running, setRunning] = useState(false)

  useEffect(() => {
    if (!open) { setStep(0); setScores([]); setDecision(null); setPasted(''); setRunning(false) }
  }, [open])

  const runMatch = async () => {
    setStep(1)
    setRunning(true)
    const newScores = []

    for (let i = 0; i < versions.length; i++) {
      await new Promise(r => setTimeout(r, 300))
      const v = versions[i]
      const score = Math.round((6 + Math.random() * 3) * 10) / 10
      newScores.push({ id: v.id, score, status: 'scored' })
      setScores([...newScores])
    }

    await new Promise(r => setTimeout(r, 400))
    const winner = newScores.reduce((a, b) => (b.score > a.score ? b : a))

    try { await api.runStage('tailor') } catch (_) {}

    const dec = winner.score >= 8
      ? { kind: 'reuse', versionId: winner.id, score: winner.score }
      : { kind: 'create', versionId: String.fromCharCode(65 + versions.length), score: winner.score }

    setDecision(dec)
    setStep(2)
    setRunning(false)
  }

  return (
    <Modal open={open} onClose={onClose} width={720}>
      <div className="p-6">
        {/* Header */}
        <div className="flex justify-between items-start mb-5">
          <div>
            <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-1">Smart Tailor</p>
            <h2 className="text-xl font-bold text-on-surface">Match JD to existing versions</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
          >
            <Icon name="close" size={18} />
          </button>
        </div>

        {/* Step 0: paste JD */}
        {step === 0 && (
          <div className="space-y-4">
            <p className="text-sm text-on-surface-variant">
              Paste a job description. We'll score it against your {versions.length} existing version{versions.length !== 1 ? 's' : ''} before tailoring.
            </p>
            <textarea
              className="w-full bg-surface-container-low border border-outline-variant rounded-xl text-on-surface px-4 py-3 text-sm min-h-[140px] resize-y outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-all"
              placeholder="Paste job description here…"
              value={pasted}
              onChange={e => setPasted(e.target.value)}
            />
            <div className="flex justify-between">
              <button
                onClick={() => setPasted(SAMPLE_JD)}
                className="px-4 py-2 border border-outline-variant text-on-surface text-sm font-medium rounded-lg hover:bg-slate-50 transition-all"
              >
                Use sample JD
              </button>
              <button
                onClick={runMatch}
                disabled={!pasted.trim()}
                className="flex items-center gap-2 px-5 py-2 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-dark disabled:opacity-50 transition-all active:scale-95"
              >
                <Icon name="auto_awesome" size={16} /> Run match
              </button>
            </div>
          </div>
        )}

        {/* Step 1+: scoring */}
        {step >= 1 && (
          <div className="space-y-4">
            <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Scoring against existing versions</p>
            <div className="space-y-2">
              {versions.map(v => {
                const s = scores.find(x => x.id === v.id)
                const pct = s ? Math.round(s.score * 10) : 0
                return (
                  <div
                    key={v.id}
                    className={`grid gap-3 p-3 bg-surface-container-low border border-outline-variant rounded-xl transition-opacity ${s ? 'opacity-100' : 'opacity-40'}`}
                    style={{ gridTemplateColumns: '28px 1fr 1fr 40px' }}
                  >
                    <div className="w-7 h-7 rounded-md bg-primary/10 text-primary flex items-center justify-center font-bold text-xs font-mono">
                      {v.id}
                    </div>
                    <div>
                      <div className="text-sm font-medium text-on-surface">{v.name}</div>
                      <div className="text-xs text-on-surface-variant truncate">{v.tagline}</div>
                    </div>
                    <div className="h-1.5 bg-slate-200 rounded-full self-center overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${pct}%`, background: s ? scoreColor(s.score) : 'transparent' }}
                      />
                    </div>
                    <div
                      className="text-right font-mono text-sm font-bold self-center"
                      style={{ color: s ? scoreColor(s.score) : '#9ca3af' }}
                    >
                      {s ? s.score.toFixed(1) : '—'}
                    </div>
                  </div>
                )
              })}
            </div>

            {step === 2 && decision && (
              <div className={`flex items-center gap-4 p-4 rounded-xl border ${
                decision.kind === 'reuse'
                  ? 'bg-emerald-50 border-emerald-200'
                  : 'bg-indigo-50 border-indigo-200'
              }`}>
                <Icon
                  name={decision.kind === 'reuse' ? 'check_circle' : 'add_circle'}
                  size={24}
                  className={decision.kind === 'reuse' ? 'text-emerald-600' : 'text-primary'}
                  filled
                />
                <div className="flex-1">
                  <div className="font-semibold text-on-surface text-sm">
                    {decision.kind === 'reuse' ? `Reusing Version ${decision.versionId}` : `Creating Version ${decision.versionId}`}
                  </div>
                  <div className="text-xs text-on-surface-variant mt-0.5">
                    {decision.kind === 'reuse'
                      ? `Score ${decision.score.toFixed(1)} ≥ 8.0 — no new resume needed.`
                      : `Best match ${decision.score.toFixed(1)} < 8.0 — tailor pipeline started.`}
                  </div>
                </div>
                <button
                  onClick={() => { onCreated?.(decision); onClose() }}
                  className="px-4 py-2 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-dark transition-all active:scale-95 flex items-center gap-1.5 flex-shrink-0"
                >
                  Done <Icon name="arrow_forward" size={15} />
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  )
}
