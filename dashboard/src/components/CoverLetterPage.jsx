import { useState, useEffect, useCallback } from 'react'
import Icon from './Icon.jsx'
import { cls } from '../utils.js'

const TONES = [
  { id: 'professional', label: 'Professional' },
  { id: 'direct',       label: 'Direct' },
  { id: 'warm',         label: 'Warm & personal' },
  { id: 'bold',         label: 'Bold' },
  { id: 'storytelling', label: 'Storytelling' },
]

const DEFAULT_LETTER = `Dear Hiring Manager,

I am excited to apply for the [Role] position at [Company]. With [X] years of experience in [field], I bring a track record of [key strength] and a passion for [relevant domain].

At [Previous Company], I [specific achievement with metrics — e.g., led a team of 6 to ship X, reducing latency by 40%]. This experience taught me [lesson] and sharpened my ability to [transferable skill].

What draws me to [Company] is [specific reason — product, mission, engineering culture, or recent initiative]. I believe my background in [relevant skills] directly aligns with the challenges your team is solving.

I would love to discuss how I can contribute to [Company]'s goals. Thank you for your time.

Best regards,
[Your Name]`

function wordCount(text) {
  return text.trim() ? text.trim().split(/\s+/).length : 0
}
function charCount(text) { return text.length }
function readingTime(text) {
  const mins = Math.ceil(wordCount(text) / 200)
  return mins < 1 ? '<1 min' : `${mins} min`
}
function qualityLabel(wc) {
  if (wc < 100) return { label: 'Too short', color: 'var(--bad)' }
  if (wc < 200) return { label: 'Needs more', color: 'var(--warn)' }
  if (wc > 450) return { label: 'Too long', color: 'var(--warn)' }
  return { label: 'Good length', color: 'var(--ok)' }
}

// ── Preview renderer ──────────────────────────────────────────────────────
function LetterPreview({ text, profile }) {
  const paragraphs = text.split(/\n\n+/).filter(Boolean)
  const singleLines = text.split('\n')

  return (
    <div className="ha-cl-preview">
      <div className="ha-cl-preview-letterhead">
        <div className="ha-cl-preview-name">
          {profile.firstName} {profile.lastName}
        </div>
        <div className="ha-cl-preview-contact">
          {[profile.email, profile.phone, profile.linkedin, profile.github]
            .filter(Boolean)
            .map((v, i, arr) => (
              <span key={v}>
                {v}{i < arr.length - 1 && <span className="ha-cl-preview-sep"> · </span>}
              </span>
            ))}
        </div>
      </div>
      <div className="ha-cl-preview-divider" />
      <div className="ha-cl-preview-body">
        {paragraphs.map((p, i) => (
          <p key={i} className="ha-cl-preview-para">{p}</p>
        ))}
      </div>
    </div>
  )
}

// ── Quality bar ───────────────────────────────────────────────────────────
function QualityBar({ wc }) {
  const maxWords = 450
  const pct = Math.min((wc / maxWords) * 100, 100)
  const { label, color } = qualityLabel(wc)
  return (
    <div className="ha-cl-quality">
      <div className="ha-cl-quality-bar">
        <div className="ha-cl-quality-fill" style={{ width: `${pct}%`, background: color }} />
        {/* ideal zone marker */}
        <div className="ha-cl-quality-zone" style={{ left: `${(200/maxWords)*100}%`, width: `${(250/maxWords)*100}%` }} />
      </div>
      <div className="ha-cl-quality-labels">
        <span>0</span>
        <span style={{ color: 'var(--text-3)', fontSize: 10 }}>ideal 200–450</span>
        <span>450+</span>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────
export default function CoverLetterPage({ profile, onSave }) {
  const [text, setText] = useState(profile.coverLetter || DEFAULT_LETTER)
  const [tone, setTone] = useState('professional')
  const [mode, setMode] = useState('split') // 'edit' | 'split' | 'preview'
  const [saveState, setSaveState] = useState('saved') // 'saved' | 'unsaved' | 'saving'
  const [generating, setGenerating] = useState(false)

  // auto-save debounce
  useEffect(() => {
    setSaveState('unsaved')
    const t = setTimeout(() => {
      setSaveState('saving')
      onSave?.({ ...profile, coverLetter: text })
      setTimeout(() => setSaveState('saved'), 400)
    }, 1500)
    return () => clearTimeout(t)
  }, [text])

  const handleRegenerate = useCallback(async () => {
    setGenerating(true)
    // Stub — in production this calls the AI API
    await new Promise(r => setTimeout(r, 1200))
    setGenerating(false)
  }, [])

  const handleCopy = () => {
    navigator.clipboard?.writeText(text)
  }

  const wc  = wordCount(text)
  const cc  = charCount(text)
  const rt  = readingTime(text)
  const { label: ql, color: qc } = qualityLabel(wc)

  return (
    <div className="ha-screen" style={{ display: 'flex', flexDirection: 'column', gap: 0, padding: 0 }}>
      {/* ── Header ── */}
      <div className="ha-cl-header">
        <div>
          <div className="ha-eyebrow">Cover Letter</div>
          <h1 className="ha-h1" style={{ margin: 0 }}>Your cover letter</h1>
          <p className="ha-sub" style={{ margin: '4px 0 0' }}>
            Editable at any time. Used as the base for all applications.
          </p>
        </div>
        <div className="ha-cl-header-actions">
          <button className="ha-btn ha-btn--ghost" onClick={handleCopy}>
            <Icon name="copy" size={14} /> Copy
          </button>
          <button
            className="ha-btn ha-btn--ghost"
            onClick={handleRegenerate}
            disabled={generating}
          >
            <Icon name="wand" size={14} />
            {generating ? 'Generating…' : 'Regenerate'}
          </button>
          <div className={cls('ha-cl-save-badge', `ha-cl-save-badge--${saveState}`)}>
            {saveState === 'saved'   && <><Icon name="check" size={12} /> Saved</>}
            {saveState === 'unsaved' && 'Unsaved'}
            {saveState === 'saving'  && 'Saving…'}
          </div>
        </div>
      </div>

      {/* ── Toolbar ── */}
      <div className="ha-cl-toolbar">
        <div className="ha-cl-tone-row">
          <span className="ha-eyebrow" style={{ alignSelf: 'center', whiteSpace: 'nowrap' }}>Tone</span>
          {TONES.map(t => (
            <button
              key={t.id}
              className={cls('ha-cl-tone-chip', tone === t.id && 'is-active')}
              onClick={() => setTone(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="ha-cl-stats-row">
          <span className="ha-cl-stat">{wc} words</span>
          <span className="ha-cl-dot" />
          <span className="ha-cl-stat">{cc} chars</span>
          <span className="ha-cl-dot" />
          <span className="ha-cl-stat">{rt} read</span>
          <span className="ha-cl-dot" />
          <span className="ha-cl-stat" style={{ color: qc }}>{ql}</span>

          <div className="ha-cl-mode-switch">
            {['edit', 'split', 'preview'].map(m => (
              <button
                key={m}
                className={cls('ha-cl-mode-btn', mode === m && 'is-active')}
                onClick={() => setMode(m)}
              >
                {m === 'edit' && <Icon name="pencil" size={13} />}
                {m === 'split' && <Icon name="list" size={13} />}
                {m === 'preview' && <Icon name="eye" size={13} />}
                <span>{m.charAt(0).toUpperCase() + m.slice(1)}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Quality bar ── */}
      <div style={{ padding: '0 28px' }}>
        <QualityBar wc={wc} />
      </div>

      {/* ── Editor / Preview ── */}
      <div className={cls('ha-cl-workspace', `ha-cl-workspace--${mode}`)}>
        {(mode === 'edit' || mode === 'split') && (
          <div className="ha-cl-editor-pane">
            <div className="ha-cl-editor-label">
              <Icon name="pencil" size={12} /> Editor
            </div>
            <textarea
              className="ha-cl-editor"
              value={text}
              onChange={e => setText(e.target.value)}
              spellCheck
              placeholder="Write your cover letter here…"
            />
          </div>
        )}
        {(mode === 'preview' || mode === 'split') && (
          <div className="ha-cl-preview-pane">
            <div className="ha-cl-editor-label">
              <Icon name="eye" size={12} /> Preview
            </div>
            <LetterPreview text={text} profile={profile} />
          </div>
        )}
      </div>
    </div>
  )
}
