import Icon from './Icon.jsx'
import { scoreColor, toneVar } from '../utils.js'

function StatTile({ label, value, accent, sub }) {
  return (
    <div className="ha-stat-tile">
      <div className="ha-stat-label">{label}</div>
      <div className="ha-stat-row">
        <div className="ha-stat-value" style={accent ? { color: accent } : null}>{value ?? '—'}</div>
        {sub && <div className="ha-stat-sub">{sub}</div>}
      </div>
    </div>
  )
}

function BarChart({ data, height = 180, color = 'var(--accent)' }) {
  const max = Math.max(...data.map(d => d.value), 1)
  return (
    <div className="ha-bars" style={{ height }}>
      {data.map((d, i) => (
        <div key={i} className="ha-bars-col">
          <div className="ha-bars-bar" style={{ height: `${(d.value / max) * 100}%`, background: color }} />
          <div className="ha-bars-label">{d.label}</div>
        </div>
      ))}
    </div>
  )
}

function DonutChart({ data, size = 180 }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1
  const r = 64, stroke = 18, c = 2 * Math.PI * r
  let offset = 0
  return (
    <div className="ha-donut">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={stroke} />
        {data.map((d, i) => {
          const len = (d.value / total) * c
          const seg = (
            <circle key={i}
              cx={size/2} cy={size/2} r={r} fill="none"
              stroke={d.color} strokeWidth={stroke}
              strokeDasharray={`${len} ${c}`}
              strokeDashoffset={-offset}
              transform={`rotate(-90 ${size/2} ${size/2})`}
            />
          )
          offset += len
          return seg
        })}
        <text x={size/2} y={size/2 - 4} textAnchor="middle" className="ha-donut-num">{total}</text>
        <text x={size/2} y={size/2 + 14} textAnchor="middle" className="ha-donut-lbl">jobs</text>
      </svg>
      <div className="ha-donut-legend">
        {data.map(d => (
          <div key={d.label} className="ha-donut-legend-row">
            <span className="ha-donut-swatch" style={{ background: d.color }} />
            <span>{d.label}</span>
            <span className="ha-donut-legend-num">{d.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function StatsPage({ stats, versions, jobs }) {
  if (!stats) {
    return (
      <div className="ha-screen">
        <div className="ha-loading"><div className="ha-spinner" /><span>Loading stats…</span></div>
      </div>
    )
  }

  // Status breakdown from jobs
  const byStatus = { pending: 0, applied: 0, interview: 0, rejected: 0 }
  jobs.forEach(j => { if (byStatus[j.status] !== undefined) byStatus[j.status]++ })

  // Company distribution from jobs
  const byCompany = {}
  jobs.forEach(j => { byCompany[j.company] = (byCompany[j.company] || 0) + 1 })
  const companyData = Object.entries(byCompany)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([k, v]) => ({ label: k.split(' ')[0], value: v }))

  // Weekly discovery from API stats
  const weeklyData = (stats.weekly_discovery || []).map(w => ({
    label: w.week?.replace(/^\d{4}-/, '') || '—',
    value: w.count || 0,
  }))

  // Score distribution from API
  const scoreDist = (stats.score_distribution || []).map(s => ({
    label: String(s.score),
    value: s.count || 0,
  }))

  // Funnel
  const funnel = [
    { label: 'Tracked',   value: stats.total || 0,   color: 'var(--text-2)' },
    { label: 'Tailored',  value: stats.tailored || 0, color: 'var(--accent)' },
    { label: 'Applied',   value: stats.applied || 0,  color: 'var(--ok)' },
  ]

  const applyRate = stats.total ? Math.round((stats.applied / stats.total) * 100) : 0
  const tailorRate = stats.total ? Math.round((stats.tailored / stats.total) * 100) : 0

  return (
    <div className="ha-screen">
      <div className="ha-screen-head">
        <div>
          <div className="ha-eyebrow">Stats</div>
          <h1 className="ha-h1">Pipeline</h1>
          <p className="ha-sub">Where your applications stand and where time is going.</p>
        </div>
      </div>

      <div className="ha-stat-grid">
        <StatTile label="Total tracked"   value={stats.total || 0}    sub="jobs discovered" />
        <StatTile label="High fit (≥7)"   value={stats.high_fit || 0} accent="var(--ok)"     sub="scoring jobs" />
        <StatTile label="Tailored"        value={stats.tailored || 0} accent="var(--accent)"  sub={`${tailorRate}% of all`} />
        <StatTile label="Applied"         value={stats.applied || 0}  accent="var(--ok)"     sub={`${applyRate}% apply rate`} />
      </div>

      <div className="ha-stats-grid">
        <div className="ha-card-flat">
          <div className="ha-card-flat-head">
            <div className="ha-eyebrow">Funnel</div>
            <div className="ha-sub-tiny">tracked → applied</div>
          </div>
          <div className="ha-funnel">
            {funnel.map(f => {
              const pct = funnel[0].value ? (f.value / funnel[0].value) * 100 : 0
              return (
                <div key={f.label} className="ha-funnel-row">
                  <div className="ha-funnel-label">{f.label}</div>
                  <div className="ha-funnel-bar">
                    <div className="ha-funnel-fill" style={{ width: `${pct}%`, background: f.color }} />
                  </div>
                  <div className="ha-funnel-value">{f.value}</div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="ha-card-flat">
          <div className="ha-card-flat-head">
            <div className="ha-eyebrow">Status breakdown</div>
            <div className="ha-sub-tiny">{jobs.length} jobs</div>
          </div>
          <div className="ha-donut-wrap">
            <DonutChart data={[
              { label: 'Pending',   value: byStatus.pending,   color: 'var(--accent)' },
              { label: 'Applied',   value: byStatus.applied,   color: 'var(--ok)' },
              { label: 'Interview', value: byStatus.interview, color: 'var(--gold)' },
              { label: 'Rejected',  value: byStatus.rejected,  color: 'var(--bad)' },
            ]} />
          </div>
        </div>

        {companyData.length > 0 && (
          <div className="ha-card-flat ha-stats-wide">
            <div className="ha-card-flat-head">
              <div className="ha-eyebrow">Top companies</div>
              <div className="ha-sub-tiny">jobs tracked</div>
            </div>
            <BarChart data={companyData} />
          </div>
        )}

        {weeklyData.length > 0 && (
          <div className="ha-card-flat ha-stats-wide">
            <div className="ha-card-flat-head">
              <div className="ha-eyebrow">Discovery per week</div>
              <div className="ha-sub-tiny">last {weeklyData.length} weeks</div>
            </div>
            <BarChart data={weeklyData} color="var(--ok)" />
          </div>
        )}

        {scoreDist.length > 0 && (
          <div className="ha-card-flat ha-stats-wide">
            <div className="ha-card-flat-head">
              <div className="ha-eyebrow">Score distribution</div>
              <div className="ha-sub-tiny">fit score 0–10</div>
            </div>
            <BarChart data={scoreDist} color="var(--accent)" />
          </div>
        )}
      </div>

      {versions.length > 0 && (
        <div className="ha-card-flat">
          <div className="ha-card-flat-head">
            <div className="ha-eyebrow">Version performance</div>
            <div className="ha-sub-tiny">avg score by branch</div>
          </div>
          <div className="ha-vperf">
            {versions.map(v => {
              const vJobs = jobs.filter(j => j.version === v.id)
              const avg = vJobs.length ? vJobs.reduce((s, j) => s + j.ats, 0) / vJobs.length : 0
              return (
                <div key={v.id} className="ha-vperf-row" style={{ '--tone': toneVar(v.tone) }}>
                  <div className="ha-vperf-letter">{v.id}</div>
                  <div className="ha-vperf-name">{v.name}</div>
                  <div className="ha-vperf-bar">
                    <div className="ha-vperf-fill" style={{ width: `${avg * 10}%` }} />
                  </div>
                  <div className="ha-vperf-num">{avg.toFixed(1)}</div>
                  <div className="ha-vperf-jobs">{vJobs.length} jobs</div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
