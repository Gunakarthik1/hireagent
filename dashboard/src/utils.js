export const cls = (...xs) => xs.filter(Boolean).join(' ')

export const scoreColor = (s) => {
  if (s >= 8.5) return 'var(--ok)'
  if (s >= 7) return 'var(--warn)'
  return 'var(--bad)'
}

export const toneVar = (tone) => `var(--tone-${tone})`

const TONES = ['violet', 'emerald', 'sky', 'amber', 'rose', 'teal']

export function versionTone(id) {
  const idx = id ? id.charCodeAt(0) - 65 : 0
  return TONES[idx % TONES.length]
}

export function timeAgo(isoStr) {
  if (!isoStr) return '—'
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return mins < 2 ? 'just now' : `${mins}m`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d`
  const weeks = Math.floor(days / 7)
  if (weeks < 5) return `${weeks}w`
  return `${Math.floor(weeks / 4)}mo`
}

function capitalize(s) {
  if (!s) return ''
  return s.split(/[\s-]+/).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

export function extractCompany(url, site) {
  try {
    // ATS platform patterns
    const gh = url.match(/greenhouse\.io\/([^/?#]+)/)
    if (gh) return capitalize(gh[1])
    const lever = url.match(/jobs\.lever\.co\/([^/?#]+)/)
    if (lever) return capitalize(lever[1])
    const wd = url.match(/([^.]+)\.wd\d+\.myworkdayjobs\.com/)
    if (wd) return capitalize(wd[1])
    const ashby = url.match(/jobs\.ashbyhq\.com\/([^/?#]+)/)
    if (ashby) return capitalize(ashby[1])
    const smartr = url.match(/([^.]+)\.smartrecruiters\.com/)
    if (smartr && smartr[1] !== 'www') return capitalize(smartr[1])
    const icims = url.match(/([^.]+)\.icims\.com/)
    if (icims && icims[1] !== 'careers') return capitalize(icims[1])

    // Known boards — use site label
    const hostname = new URL(url).hostname.replace('www.', '')
    if (hostname.includes('linkedin.com')) return 'LinkedIn'
    if (hostname.includes('indeed.com')) return 'Indeed'
    if (hostname.includes('glassdoor.com')) return 'Glassdoor'
    if (hostname.includes('wellfound.com')) return 'Wellfound'
    if (hostname.includes('builtin.com')) return 'BuiltIn'

    // Fall back to second-level domain
    const parts = hostname.split('.')
    const sld = parts.length >= 2 ? parts[parts.length - 2] : parts[0]
    return capitalize(sld)
  } catch {
    return capitalize(site || 'Unknown')
  }
}

const TECH_TERMS = [
  'Python','TypeScript','JavaScript','Go','Rust','Java','C++','C#','Ruby',
  'React','Vue','Angular','Node','Django','FastAPI','Flask','Rails',
  'PostgreSQL','MySQL','MongoDB','Redis','Kafka','RabbitMQ','Elasticsearch',
  'Kubernetes','Docker','AWS','GCP','Azure','Terraform','CI/CD','Helm',
  'PyTorch','TensorFlow','LLMs','CUDA','JAX','Triton','RAG',
  'GraphQL','REST','gRPC','Microservices','Distributed','Spark',
  'Airflow','Databricks','dbt','SQL','Scala','Hadoop',
  'LLVM','Compilers','Systems','Networking','Security','Crypto',
]

export function extractTags(scoreReasoning, descriptionPreview) {
  const text = ((scoreReasoning || '') + ' ' + (descriptionPreview || '')).toLowerCase()
  return TECH_TERMS.filter(t => text.includes(t.toLowerCase())).slice(0, 5)
}

// Map API job → design job format
export function mapJob(apiJob) {
  const ats = Number(apiJob.fit_score) || 0
  const atsPct = Math.round(ats * 10)
  const tags = extractTags(apiJob.score_reasoning, apiJob.description_preview)
  return {
    id: apiJob.url,
    url: apiJob.url,
    title: apiJob.title || 'Untitled',
    company: apiJob.company || extractCompany(apiJob.url, apiJob.site),
    location: apiJob.location || 'Remote',
    salary: apiJob.salary || '—',
    posted: timeAgo(apiJob.discovered_at),
    version: apiJob.resume_version_id || null,
    ats,
    kw: atsPct,
    sk: Math.round(atsPct * 0.9),
    ex: Math.round(atsPct * 0.85),
    ed: Math.round(atsPct * 0.95),
    status: apiJob.apply_status || 'pending',
    tags,
    application_url: apiJob.application_url || apiJob.url,
    tailored_resume_path: apiJob.tailored_resume_path,
    score_reasoning: apiJob.score_reasoning,
    site: apiJob.site,
  }
}

const TONE_BY_ID = { A: 'violet', B: 'emerald', C: 'sky', D: 'amber', E: 'rose' }

function clusterToName(cluster) {
  const map = {
    backend: 'Backend SWE', frontend: 'Frontend', fullstack: 'Full Stack',
    ml: 'ML / Research', data: 'Data Engineering', devops: 'DevOps / SRE',
    sre: 'SRE', mobile: 'Mobile', general: 'Generalist SWE', security: 'Security',
  }
  return map[(cluster || '').toLowerCase()] || capitalize(cluster || 'Generalist SWE')
}

function formatDate(isoStr) {
  if (!isoStr) return '—'
  return new Date(isoStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

// Map API version → design version format
export function mapVersion(apiVersion) {
  const id = apiVersion.version_id || '?'
  const idx = id.charCodeAt(0) - 65
  const tone = TONE_BY_ID[id] || TONES[Math.max(0, idx) % TONES.length]
  const keywords = (apiVersion.base_keywords || '').split(',').map(s => s.trim()).filter(Boolean)
  const cluster = apiVersion.role_cluster || 'general'
  const name = clusterToName(cluster)
  const topKws = keywords.slice(0, 3).join(', ')

  return {
    id,
    name,
    tagline: topKws || name,
    created: formatDate(apiVersion.created_at),
    updated: formatDate(apiVersion.last_used_at || apiVersion.created_at),
    skills: keywords.slice(0, 8),
    keywords,
    summary: `${name} variant. Tuned for roles emphasizing ${topKws || cluster}.`,
    tone,
    job_count: apiVersion.job_count || 0,
    avg_score: Number(apiVersion.avg_score) || 0,
    resume_pdf_path: apiVersion.resume_pdf_path,
    // version jobs already mapped by the API
    versionJobs: (apiVersion.jobs || []),
  }
}

// Build company palette from mapped jobs
export function buildCompanies(jobs) {
  const seen = new Set()
  const companies = []
  let i = 0
  for (const j of jobs) {
    if (!seen.has(j.company)) {
      seen.add(j.company)
      companies.push({
        name: j.company,
        logo: (j.company || '?').charAt(0).toUpperCase(),
        tone: TONES[i % TONES.length],
      })
      i++
    }
  }
  return companies
}
