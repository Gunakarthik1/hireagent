import { useState } from 'react'
import Icon from './Icon.jsx'
import { useToast } from './UI.jsx'

function Field({ label, value, onChange, type = 'text', hint }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">{label}</span>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-all"
      />
      {hint && <span className="text-xs text-on-surface-variant/70">{hint}</span>}
    </label>
  )
}

export default function Settings({ profile, setProfile }) {
  const [draft, setDraft] = useState(profile)
  const toast = useToast()
  const update = (k, v) => setDraft(d => ({ ...d, [k]: v }))

  const save = () => {
    setProfile(draft)
    toast('Profile saved', { kind: 'ok', icon: 'check_circle' })
  }

  const Section = ({ title, children }) => (
    <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm mb-4">
      <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-5">{title}</p>
      {children}
    </div>
  )

  return (
    <div className="p-8 max-w-3xl">
      <div className="mb-8">
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-1">Settings</p>
        <h1 className="text-3xl font-bold text-on-surface tracking-tight">Profile & Preferences</h1>
        <p className="text-on-surface-variant mt-1">Source data the tailor uses when building new resume versions.</p>
      </div>

      <Section title="Identity">
        <div className="grid grid-cols-2 gap-4">
          <Field label="First name"  value={draft.firstName}  onChange={v => update('firstName', v)} />
          <Field label="Last name"   value={draft.lastName}   onChange={v => update('lastName', v)} />
          <Field label="Email"       value={draft.email}      onChange={v => update('email', v)} />
          <Field label="Phone"       value={draft.phone}      onChange={v => update('phone', v)} />
          <Field label="LinkedIn"    value={draft.linkedin}   onChange={v => update('linkedin', v)} />
          <Field label="GitHub"      value={draft.github}     onChange={v => update('github', v)} />
        </div>
      </Section>

      <Section title="Tailor Preferences">
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Resume length cap"
            value={draft.lengthCap}
            onChange={v => update('lengthCap', v)}
            hint="e.g. '1 page' or '2 pages'"
          />
          <Field
            label="Tone"
            value={draft.tone}
            onChange={v => update('tone', v)}
            hint="e.g. 'Direct, metrics-first'"
          />
          <Field
            label="ATS reuse threshold"
            value={draft.threshold}
            onChange={v => update('threshold', v)}
            hint="Reuse version if score ≥ this"
          />
          <Field
            label="Default location"
            value={draft.defaultLocation}
            onChange={v => update('defaultLocation', v)}
          />
        </div>
      </Section>

      <Section title="API Keys">
        <div className="grid grid-cols-1 gap-4 max-w-sm">
          <Field
            label="Anthropic API key"
            value={draft.anthropicKey}
            onChange={v => update('anthropicKey', v)}
            type="password"
          />
        </div>
      </Section>

      <div className="flex justify-end gap-3 mt-2">
        <button
          onClick={() => setDraft(profile)}
          className="px-4 py-2 border border-outline-variant text-on-surface text-sm font-medium rounded-lg hover:bg-slate-50 transition-all"
        >
          Reset
        </button>
        <button
          onClick={save}
          className="px-5 py-2 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-dark transition-all active:scale-95 flex items-center gap-1.5"
        >
          <Icon name="check_circle" size={16} /> Save changes
        </button>
      </div>
    </div>
  )
}
