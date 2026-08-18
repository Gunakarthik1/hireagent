import { useState, useEffect, useCallback } from 'react'
import Sidebar from './components/Sidebar.jsx'
import DashboardPage from './components/DashboardPage.jsx'
import JobsPage from './components/JobsPage.jsx'
import VersionsPage from './components/VersionsPage.jsx'
import Settings from './components/Settings.jsx'
import TailorModal from './components/TailorModal.jsx'
import ProfileWizard from './components/ProfileWizard.jsx'
import Icon from './components/Icon.jsx'
import { useToast } from './components/UI.jsx'
import { api } from './api.js'
import { mapJob, mapVersion, buildCompanies } from './utils.js'

const DEFAULT_PROFILE = {
  firstName: 'Guna',
  lastName: 'Lanka',
  email: 'gunakarthik29@gmail.com',
  phone: '+1 (469) 555-0192',
  linkedin: 'linkedin.com/in/gunakarthik',
  github: 'github.com/guna29',
  lengthCap: '1 page',
  tone: 'Direct, metrics-first',
  threshold: '7.5',
  defaultLocation: 'United States',
  anthropicKey: '',
  about: 'Full-stack engineer building AI-powered products.',
  targetCountries: ['US', 'CA', 'GB', 'SG'],
  targetRoles: ['Software Engineer', 'Full Stack Developer', 'ML Engineer', 'Backend Engineer'],
  experienceLevel: 'mid',
  skills: ['Python', 'TypeScript', 'React', 'Node.js', 'FastAPI', 'PostgreSQL', 'Docker', 'AWS', 'LLMs', 'Next.js'],
  coverLetter: '',
}

export default function App() {
  const toast = useToast()
  const [page, setPage] = useState('dashboard')
  const [scanning, setScanning] = useState(false)
  const [tailorOpen, setTailorOpen] = useState(false)

  const [jobs, setJobs] = useState([])
  const [versions, setVersions] = useState([])
  const [companies, setCompanies] = useState([])
  const [stats, setStats] = useState(null)
  const [profile, setProfile] = useState(DEFAULT_PROFILE)
  const [loading, setLoading] = useState(true)

  const fetchJobs = useCallback(async () => {
    try {
      const data = await api.getJobs({ limit: 500 })
      const mapped = (data.jobs || []).map(mapJob)
      setJobs(mapped)
      setCompanies(buildCompanies(mapped))
    } catch (e) { console.error('fetchJobs:', e) }
  }, [])

  const fetchVersions = useCallback(async () => {
    try {
      const data = await api.getVersions()
      setVersions((data.versions || []).map(mapVersion))
    } catch (e) { console.error('fetchVersions:', e) }
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      setStats(await api.getStats())
    } catch (e) { console.error('fetchStats:', e) }
  }, [])

  useEffect(() => {
    Promise.all([fetchJobs(), fetchVersions(), fetchStats()])
      .finally(() => setLoading(false))
    const id = setInterval(fetchStats, 30_000)
    return () => clearInterval(id)
  }, [fetchJobs, fetchVersions, fetchStats])

  const handleRunScan = useCallback(async () => {
    setScanning(true)
    try {
      await api.triggerScan()
      toast('Scan started — this takes a few minutes', { kind: 'ok', icon: 'check_circle' })
    } catch (e) {
      toast(e.message, { kind: 'err', icon: 'error' })
    } finally {
      setTimeout(() => setScanning(false), 2000)
    }
  }, [toast])

  const handleMark = useCallback(async (job, status) => {
    setJobs(prev => prev.map(j => j.id === job.id ? { ...j, status } : j))
    try {
      if (status === 'applied') {
        await api.markApplied(job.url)
        toast(`Marked "${job.title}" applied`, { kind: 'ok', icon: 'check_circle' })
      } else {
        await api.markUnapplied(job.url)
        toast(`Reset "${job.title}"`, { kind: 'info', icon: 'refresh' })
      }
      fetchStats()
    } catch (e) {
      setJobs(prev => prev.map(j => j.id === job.id ? { ...j, status: job.status } : j))
      toast('Error: ' + e.message, { kind: 'err', icon: 'error' })
    }
  }, [toast, fetchStats])

  const handleTailored = useCallback((decision) => {
    toast(
      decision.kind === 'reuse'
        ? `Reusing Version ${decision.versionId}`
        : `Creating Version ${decision.versionId}…`,
      { kind: 'info', icon: 'auto_awesome' }
    )
    setTimeout(fetchVersions, 5000)
  }, [toast, fetchVersions])

  const handleWizardComplete = useCallback((data) => {
    setProfile(data)
    setPage('dashboard')
    toast('Profile saved!', { kind: 'ok', icon: 'check_circle' })
  }, [toast])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-paper flex-col gap-4">
        <div className="w-6 h-6 rounded-full border-2 border-cobalt/20 border-t-cobalt animate-spin" />
        <span className="text-sm text-stone font-medium">Starting up…</span>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-paper overflow-hidden">
      <Sidebar
        active={page}
        setActive={setPage}
        onRunScan={handleRunScan}
        scanning={scanning}
      />

      <div className="flex-1 ml-60 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          {page === 'dashboard' && (
            <DashboardPage
              stats={stats}
              jobs={jobs}
              versions={versions}
              onGoToJobs={() => setPage('jobs')}
              onRunScan={handleRunScan}
              scanning={scanning}
            />
          )}
          {page === 'jobs' && (
            <JobsPage
              jobs={jobs}
              versions={versions}
              companies={companies}
              onMark={handleMark}
              onRefreshJobs={fetchJobs}
              onTailor={versions.length > 0 ? () => setTailorOpen(true) : null}
            />
          )}
          {page === 'versions' && (
            <VersionsPage
              versions={versions}
              jobs={jobs}
              companies={companies}
              onRefreshVersions={fetchVersions}
            />
          )}
          {page === 'profile' && (
            <div className="p-10 max-w-3xl mx-auto">
              <div className="mb-10">
                <h1 className="font-serif text-4xl text-ink mb-2">Your profile</h1>
                <p className="text-stone">Tell the agent who you are. It uses this to find and tailor roles for you.</p>
              </div>
              <div className="bg-white border border-zinc-200 rounded-2xl p-8 shadow-sm">
                <ProfileWizard
                  profile={profile}
                  onComplete={handleWizardComplete}
                  onSkip={() => setPage('dashboard')}
                  inline
                />
              </div>
            </div>
          )}
          {page === 'settings' && (
            <Settings profile={profile} setProfile={setProfile} />
          )}
        </div>
      </div>

      <TailorModal
        open={tailorOpen}
        onClose={() => setTailorOpen(false)}
        versions={versions}
        onCreated={handleTailored}
      />
    </div>
  )
}
