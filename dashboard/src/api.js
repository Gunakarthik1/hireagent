const BASE = '/api'

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  // Jobs — use ?url= query param everywhere to avoid path encoding issues
  getJobs:      (params = {}) => {
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v !== 0))
    ).toString()
    return req(`/jobs${qs ? '?' + qs : ''}`)
  },
  getJob:       (url)  => req(`/job?url=${encodeURIComponent(url)}`),
  markApplied:  (url)  => req(`/job/apply?url=${encodeURIComponent(url)}`,  { method: 'POST', body: '{}' }),
  markUnapplied:(url)  => req(`/job/unapply?url=${encodeURIComponent(url)}`, { method: 'POST' }),
  getJobResume: (url)  => `${BASE}/job/resume?url=${encodeURIComponent(url)}`,
  reclassify:   ()     => req(`/jobs/reclassify`, { method: 'POST' }),

  // Versions
  getVersions:()            => req('/versions'),
  getVersionPdf:(vid)       => `${BASE}/resume/${vid}/pdf`,
  assignVersions:(forceNew) => req('/versions/assign', {
    method: 'POST',
    body: JSON.stringify({ force_new: forceNew }),
  }),

  // Stats
  getStats:   ()            => req('/stats'),

  // Scan
  getScanStatus: ()         => req('/scan/status'),
  triggerScan:   ()         => req('/scan/run', { method: 'POST' }),

  // Pipeline
  runStage:   (stage)       => req(`/pipeline/run?stage=${stage}`, { method: 'POST' }),
}
