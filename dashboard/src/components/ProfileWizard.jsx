import { useState } from 'react'
import Icon from './Icon.jsx'

// ── Data ────────────────────────────────────────────────────────────────
const COUNTRIES = [
  { code: 'US', flag: '🇺🇸', name: 'United States' },
  { code: 'CA', flag: '🇨🇦', name: 'Canada' },
  { code: 'GB', flag: '🇬🇧', name: 'United Kingdom' },
  { code: 'DE', flag: '🇩🇪', name: 'Germany' },
  { code: 'AU', flag: '🇦🇺', name: 'Australia' },
  { code: 'NL', flag: '🇳🇱', name: 'Netherlands' },
  { code: 'SG', flag: '🇸🇬', name: 'Singapore' },
  { code: 'IN', flag: '🇮🇳', name: 'India' },
  { code: 'FR', flag: '🇫🇷', name: 'France' },
  { code: 'JP', flag: '🇯🇵', name: 'Japan' },
  { code: 'CH', flag: '🇨🇭', name: 'Switzerland' },
  { code: 'SE', flag: '🇸🇪', name: 'Sweden' },
  { code: 'NO', flag: '🇳🇴', name: 'Norway' },
  { code: 'AE', flag: '🇦🇪', name: 'UAE' },
  { code: 'IE', flag: '🇮🇪', name: 'Ireland' },
  { code: 'NZ', flag: '🇳🇿', name: 'New Zealand' },
  { code: 'BR', flag: '🇧🇷', name: 'Brazil' },
  { code: 'MX', flag: '🇲🇽', name: 'Mexico' },
]

const ROLES = [
  'Software Engineer', 'Full Stack Developer', 'Frontend Engineer',
  'Backend Engineer', 'Data Scientist', 'Data Engineer', 'ML Engineer',
  'DevOps / Platform Engineer', 'Engineering Manager', 'Product Manager',
  'Solutions Architect', 'Cloud Engineer', 'Mobile Developer',
  'Security Engineer', 'QA / SDET', 'Site Reliability Engineer',
  'Research Scientist', 'Technical Program Manager',
]

const EXP_LEVELS = [
  { id: 'intern',    label: 'Intern',     years: '0–1 yr' },
  { id: 'junior',    label: 'Junior',     years: '1–3 yrs' },
  { id: 'mid',       label: 'Mid',        years: '3–6 yrs' },
  { id: 'senior',    label: 'Senior',     years: '6–10 yrs' },
  { id: 'principal', label: 'Principal',  years: '10+ yrs' },
  { id: 'executive', label: 'Executive',  years: 'Dir / VP+' },
]

const SKILL_SUGGESTIONS = [
  'Python', 'JavaScript', 'TypeScript', 'React', 'Node.js', 'Go', 'Rust',
  'Java', 'Kotlin', 'Swift', 'C++', 'SQL', 'PostgreSQL', 'MongoDB',
  'AWS', 'GCP', 'Azure', 'Docker', 'Kubernetes', 'Terraform', 'CI/CD',
  'Machine Learning', 'Deep Learning', 'PyTorch', 'TensorFlow', 'LLMs',
  'GraphQL', 'REST APIs', 'Microservices', 'System Design', 'Redis',
  'React Native', 'Flutter', 'iOS', 'Android', 'Next.js', 'FastAPI',
]

// ── Field helpers ────────────────────────────────────────────────────────
function Field({ label, hint, children }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
        {label}
        {hint && <span className="ml-1 text-slate-400 normal-case font-normal tracking-normal">· {hint}</span>}
      </span>
      {children}
    </label>
  )
}

const inputCls = "bg-white border border-outline-variant rounded-lg px-3 py-2.5 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-all"

// ── Step: Personal ───────────────────────────────────────────────────────
function StepPersonal({ data, onChange }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Field label="First name">
        <input className={inputCls} value={data.firstName} onChange={e => onChange('firstName', e.target.value)} placeholder="Guna" />
      </Field>
      <Field label="Last name">
        <input className={inputCls} value={data.lastName} onChange={e => onChange('lastName', e.target.value)} placeholder="Lanka" />
      </Field>
      <Field label="Email">
        <input className={`${inputCls} col-span-2`} type="email" value={data.email} onChange={e => onChange('email', e.target.value)} placeholder="you@example.com" />
      </Field>
      <Field label="Phone">
        <input className={inputCls} value={data.phone} onChange={e => onChange('phone', e.target.value)} placeholder="+1 555 000 0000" />
      </Field>
      <Field label="LinkedIn">
        <input className={inputCls} value={data.linkedin} onChange={e => onChange('linkedin', e.target.value)} placeholder="linkedin.com/in/you" />
      </Field>
      <Field label="GitHub">
        <input className={inputCls} value={data.github} onChange={e => onChange('github', e.target.value)} placeholder="github.com/you" />
      </Field>
      <div className="col-span-2">
        <Field label="Short bio" hint="used in cover letter intro">
          <textarea
            className={`${inputCls} resize-y min-h-[80px]`}
            value={data.about}
            onChange={e => onChange('about', e.target.value)}
            placeholder="I'm a full-stack engineer with 5 years building scalable systems…"
            rows={3}
          />
        </Field>
      </div>
    </div>
  )
}

// ── Step: Location ───────────────────────────────────────────────────────
function StepLocation({ data, onChange }) {
  const [search, setSearch] = useState('')
  const selected = data.targetCountries || []

  const toggle = (code) => {
    const next = selected.includes(code)
      ? selected.filter(c => c !== code)
      : [...selected, code]
    onChange('targetCountries', next)
  }

  const filtered = COUNTRIES.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-4">
      <div className="relative">
        <Icon name="search" size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          className={`${inputCls} w-full pl-9`}
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search country…"
          autoFocus
        />
      </div>
      <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto pr-1">
        {filtered.map(c => (
          <button
            key={c.code}
            onClick={() => toggle(c.code)}
            className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm text-left transition-all ${
              selected.includes(c.code)
                ? 'bg-primary-fixed border-primary/40 text-primary font-semibold'
                : 'bg-white border-outline-variant text-on-surface hover:border-primary/30 hover:bg-slate-50'
            }`}
          >
            <span className="text-base">{c.flag}</span>
            <span className="flex-1 truncate">{c.name}</span>
            {selected.includes(c.code) && <Icon name="check" size={14} className="text-primary flex-shrink-0" />}
          </button>
        ))}
      </div>
      {selected.length > 0 && (
        <div className="flex items-center gap-2 text-sm text-on-surface-variant bg-surface-container-low px-4 py-2 rounded-lg">
          <span>{COUNTRIES.filter(c => selected.includes(c.code)).map(c => c.flag).join(' ')}</span>
          <span className="font-medium">{selected.length} market{selected.length !== 1 ? 's' : ''} selected</span>
        </div>
      )}
    </div>
  )
}

// ── Step: Role ───────────────────────────────────────────────────────────
function StepRole({ data, onChange }) {
  const selected = data.targetRoles || []
  const level = data.experienceLevel || 'mid'

  const toggleRole = (r) => {
    const next = selected.includes(r)
      ? selected.filter(x => x !== r)
      : [...selected, r]
    onChange('targetRoles', next)
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-3">
          Target roles <span className="ml-1 text-slate-400 normal-case font-normal tracking-normal">· pick all that apply</span>
        </p>
        <div className="flex flex-wrap gap-2">
          {ROLES.map(r => (
            <button
              key={r}
              onClick={() => toggleRole(r)}
              className={`px-3 py-1.5 rounded-full border text-sm font-medium transition-all ${
                selected.includes(r)
                  ? 'bg-primary text-white border-primary shadow-sm'
                  : 'bg-white border-outline-variant text-on-surface hover:border-primary/40 hover:bg-slate-50'
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>
      <div>
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-3">Experience level</p>
        <div className="grid grid-cols-3 gap-2">
          {EXP_LEVELS.map(l => (
            <button
              key={l.id}
              onClick={() => onChange('experienceLevel', l.id)}
              className={`p-3 rounded-xl border text-left transition-all ${
                level === l.id
                  ? 'bg-primary-fixed border-primary/40 shadow-sm'
                  : 'bg-white border-outline-variant hover:border-primary/30 hover:bg-slate-50'
              }`}
            >
              <div className={`font-semibold text-sm ${level === l.id ? 'text-primary' : 'text-on-surface'}`}>{l.label}</div>
              <div className="text-xs text-on-surface-variant mt-0.5">{l.years}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Tag Input ────────────────────────────────────────────────────────────
function TagInput({ tags, onChange, suggestions }) {
  const [input, setInput] = useState('')
  const [showSug, setShowSug] = useState(false)

  const addTag = (tag) => {
    const t = tag.trim()
    if (t && !tags.includes(t)) onChange([...tags, t])
    setInput('')
    setShowSug(false)
  }

  const removeTag = (tag) => onChange(tags.filter(t => t !== tag))

  const filtered = input.length > 0
    ? suggestions.filter(s =>
        s.toLowerCase().includes(input.toLowerCase()) && !tags.includes(s)
      ).slice(0, 7)
    : []

  return (
    <div className="relative">
      <div className="min-h-[48px] flex flex-wrap gap-1.5 p-2 bg-white border border-outline-variant rounded-lg focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary/40 transition-all">
        {tags.map(t => (
          <span key={t} className="flex items-center gap-1 px-2.5 py-1 bg-primary/10 text-primary border border-primary/20 rounded-full text-xs font-semibold">
            {t}
            <button onClick={() => removeTag(t)} className="hover:text-primary-dark transition-colors">
              <Icon name="close" size={12} />
            </button>
          </span>
        ))}
        <input
          className="flex-1 min-w-[140px] text-sm text-on-surface bg-transparent outline-none px-1"
          value={input}
          onChange={e => { setInput(e.target.value); setShowSug(true) }}
          onKeyDown={e => {
            if ((e.key === 'Enter' || e.key === ',') && input) {
              e.preventDefault(); addTag(input)
            }
            if (e.key === 'Backspace' && !input && tags.length) removeTag(tags[tags.length - 1])
          }}
          onFocus={() => setShowSug(true)}
          onBlur={() => setTimeout(() => setShowSug(false), 150)}
          placeholder={tags.length === 0 ? 'Type a skill and press Enter…' : '+ add more'}
        />
      </div>
      {showSug && filtered.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-outline-variant rounded-lg shadow-lg z-10 overflow-hidden">
          {filtered.map(s => (
            <button
              key={s}
              className="w-full text-left px-3 py-2 text-sm text-on-surface hover:bg-surface-container-low transition-colors"
              onMouseDown={() => addTag(s)}
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Step: Skills ─────────────────────────────────────────────────────────
function StepSkills({ data, onChange }) {
  const threshold = parseFloat(data.threshold) || 7

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-3">Your skills</p>
        <TagInput
          tags={data.skills || []}
          onChange={v => onChange('skills', v)}
          suggestions={SKILL_SUGGESTIONS}
        />
        <p className="text-xs text-on-surface-variant mt-2">
          Type any skill and press <kbd className="px-1.5 py-0.5 bg-surface-container border border-outline-variant rounded text-[10px] font-mono">Enter</kbd>. Used for ATS keyword matching.
        </p>
      </div>

      <div>
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-3">ATS score threshold</p>
        <div className="space-y-3">
          <input
            type="range" min="5" max="10" step="0.5"
            value={threshold}
            onChange={e => onChange('threshold', e.target.value)}
            className="w-full accent-primary cursor-pointer"
          />
          <div className="flex justify-between items-center text-xs text-on-surface-variant">
            <span>5.0 — more versions</span>
            <span className="px-3 py-1 bg-primary-fixed text-primary font-bold rounded-full text-sm">{threshold.toFixed(1)}</span>
            <span>10.0 — fewer versions</span>
          </div>
          <p className="text-xs text-on-surface-variant bg-surface-container-low px-3 py-2 rounded-lg">
            If a JD scores ≥ {threshold.toFixed(1)} against an existing version, it reuses that version. Otherwise a new version is created.
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Step: Done ───────────────────────────────────────────────────────────
function StepDone({ data }) {
  const selected = data.targetCountries || []
  const flags = COUNTRIES.filter(c => selected.includes(c.code)).map(c => c.flag)

  return (
    <div className="text-center py-4">
      <div className="w-20 h-20 rounded-full bg-emerald-50 border-4 border-emerald-200 flex items-center justify-center mx-auto mb-6">
        <Icon name="check_circle" size={40} className="text-emerald-500" filled />
      </div>
      <h3 className="text-2xl font-bold text-on-surface mb-1">You're all set, {data.firstName || 'there'}!</h3>
      <p className="text-on-surface-variant mb-8">Your profile is saved and ready.</p>

      <div className="grid grid-cols-2 gap-4 text-left">
        {flags.length > 0 && (
          <div className="bg-surface-container-low border border-outline-variant rounded-xl p-4">
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">Markets</p>
            <div className="text-2xl">{flags.join(' ')}</div>
          </div>
        )}
        {(data.targetRoles || []).length > 0 && (
          <div className="bg-surface-container-low border border-outline-variant rounded-xl p-4">
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">Target roles</p>
            <div className="flex flex-wrap gap-1">
              {(data.targetRoles || []).slice(0, 3).map(r => (
                <span key={r} className="px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full font-medium">{r}</span>
              ))}
              {(data.targetRoles || []).length > 3 && (
                <span className="px-2 py-0.5 bg-slate-100 text-slate-500 text-xs rounded-full">+{(data.targetRoles || []).length - 3}</span>
              )}
            </div>
          </div>
        )}
        {data.experienceLevel && (
          <div className="bg-surface-container-low border border-outline-variant rounded-xl p-4">
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">Level</p>
            <p className="font-semibold text-on-surface capitalize">{data.experienceLevel}</p>
          </div>
        )}
        {(data.skills || []).length > 0 && (
          <div className="bg-surface-container-low border border-outline-variant rounded-xl p-4">
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">Skills ({(data.skills || []).length})</p>
            <div className="flex flex-wrap gap-1">
              {(data.skills || []).slice(0, 5).map(s => (
                <span key={s} className="px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full font-medium">{s}</span>
              ))}
              {(data.skills || []).length > 5 && (
                <span className="px-2 py-0.5 bg-slate-100 text-slate-500 text-xs rounded-full">+{(data.skills || []).length - 5}</span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Wizard shell ─────────────────────────────────────────────────────────
const STEPS = [
  { id: 'personal', title: 'Personal info',      subtitle: "Let's start with the basics." },
  { id: 'location', title: 'Target markets',     subtitle: 'Where do you want to work?' },
  { id: 'role',     title: 'Role & level',        subtitle: 'What kind of role are you targeting?' },
  { id: 'skills',   title: 'Skills & threshold',  subtitle: 'What tech do you know? When to create a new resume version?' },
  { id: 'done',     title: "You're all set!",     subtitle: 'Profile built and ready to go.' },
]

export default function ProfileWizard({ profile, onComplete, onSkip, inline = false }) {
  const [step, setStep] = useState(0)
  const [data, setData] = useState({
    ...profile,
    about:           profile.about           || '',
    targetCountries: profile.targetCountries || [],
    targetRoles:     profile.targetRoles     || [],
    experienceLevel: profile.experienceLevel || 'mid',
    skills:          profile.skills          || [],
  })

  const update = (key, val) => setData(d => ({ ...d, [key]: val }))
  const isLast = step === STEPS.length - 1
  const pct = Math.round((step / (STEPS.length - 1)) * 100)

  const handleNext = () => {
    if (isLast) onComplete(data)
    else setStep(s => s + 1)
  }

  const stepContent = [
    <StepPersonal key="personal" data={data} onChange={update} />,
    <StepLocation key="location" data={data} onChange={update} />,
    <StepRole     key="role"     data={data} onChange={update} />,
    <StepSkills   key="skills"   data={data} onChange={update} />,
    <StepDone     key="done"     data={data} />,
  ]

  const inner = (
    <div className="w-full max-w-2xl mx-auto">
      {/* Progress bar */}
      <div className="h-1 bg-surface-container-high rounded-full mb-8 overflow-hidden">
        <div
          className="h-full bg-primary rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Step dots */}
      <div className="flex items-center gap-2 mb-8">
        {STEPS.map((s, i) => (
          <button
            key={s.id}
            onClick={() => i < step && setStep(i)}
            className={`transition-all duration-200 rounded-full ${
              i === step
                ? 'w-6 h-2 bg-primary'
                : i < step
                ? 'w-2 h-2 bg-primary/50 hover:bg-primary/70 cursor-pointer'
                : 'w-2 h-2 bg-outline-variant cursor-default'
            }`}
            title={s.title}
          />
        ))}
        <span className="ml-auto text-xs text-on-surface-variant">
          Step {step + 1} of {STEPS.length}
        </span>
      </div>

      {/* Header */}
      <div className="mb-6">
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-1">{STEPS[step].subtitle}</p>
        <h2 className="text-2xl font-bold text-on-surface">{STEPS[step].title}</h2>
      </div>

      {/* Body */}
      <div className="mb-8">
        {stepContent[step]}
      </div>

      {/* Footer */}
      <div className="flex justify-between items-center border-t border-outline-variant pt-6">
        <div>
          {step > 0 && (
            <button
              onClick={() => setStep(s => s - 1)}
              className="px-4 py-2 text-on-surface text-sm font-medium border border-outline-variant rounded-lg hover:bg-slate-50 transition-all"
            >
              Back
            </button>
          )}
        </div>
        <div className="flex items-center gap-3">
          {!isLast && (
            <button
              onClick={onSkip}
              className="text-sm text-on-surface-variant hover:text-on-surface transition-colors"
            >
              Skip for now
            </button>
          )}
          <button
            onClick={handleNext}
            className="flex items-center gap-2 px-6 py-2.5 bg-primary text-white font-semibold text-sm rounded-lg hover:bg-primary-dark transition-all active:scale-95 shadow-sm"
          >
            {isLast
              ? <><Icon name="check_circle" size={16} /> Finish setup</>
              : <>Continue <Icon name="arrow_forward" size={16} /></>
            }
          </button>
        </div>
      </div>
    </div>
  )

  if (inline) return inner

  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="bg-white rounded-2xl shadow-2xl border border-outline-variant p-10 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {inner}
      </div>
    </div>
  )
}
