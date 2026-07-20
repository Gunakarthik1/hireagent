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

  // Data
  const [jobs, setJobs] = useState([])
  const [versions, setVersions] = useState([])
  const [companies, setCompanies] = useState([])
  const [stats, setStats] = useState(null)
  const [profile, setProfile] = useState(DEFAULT_PROFILE)
  const [loading, setLoading] = useState(true)

  // Fetch
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

  // Actions
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
      <div className="flex items-center justify-center h-screen bg-surface flex-col gap-3 text-on-surface-variant">
        <div className="w-8 h-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
        <span className="text-sm font-medium">Loading pipeline…</span>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      <Sidebar
        active={page}
        setActive={setPage}
        onRunScan={handleRunScan}
        scanning={scanning}
      />

      {/* Main area */}
      <div className="flex-1 ml-64 flex flex-col overflow-hidden">
        {/* Top header */}
        <TopBar onNewApplication={() => setTailorOpen(true)} />

        {/* Page content */}
        <div className="flex-1 overflow-y-auto">
          {page === 'dashboard' && (
            <DashboardPage
              stats={stats}
              jobs={jobs}
              versions={versions}
              onGoToJobs={() => setPage('jobs')}
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
            <div className="p-8 max-w-3xl mx-auto">
              <div className="mb-8">
                <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-1">Profile</p>
                <h1 className="text-3xl font-bold text-on-surface tracking-tight">Setup your profile</h1>
                <p className="text-on-surface-variant mt-1">Configure how the agent targets jobs and tailors your resume.</p>
              </div>
              <div className="bg-white border border-outline-variant rounded-2xl p-8 shadow-sm">
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

function TopBar({ onNewApplication }) {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white/80 backdrop-blur-md flex justify-between items-center h-16 px-8 shadow-sm flex-shrink-0">
      <div className="flex items-center gap-6">
        <span className="hidden md:block text-lg font-black text-primary">HireAgent</span>
        <div className="relative">
          <Icon name="search" size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            className="pl-10 pr-4 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-sm w-64 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-all"
            placeholder="Search jobs, companies…"
            type="text"
          />
        </div>
        <nav className="hidden lg:flex items-center gap-5">
          <span className="text-slate-400 text-sm font-medium">Analytics</span>
          <span className="text-slate-400 text-sm font-medium">Inbox</span>
        </nav>
      </div>
      <div className="flex items-center gap-3">
        <button className="p-2 text-slate-500 hover:bg-slate-50 rounded-md transition-all">
          <Icon name="notifications" size={20} />
        </button>
        <button className="p-2 text-slate-500 hover:bg-slate-50 rounded-md transition-all">
          <Icon name="history" size={20} />
        </button>
        <button
          onClick={onNewApplication}
          className="px-4 py-2 bg-primary text-white font-semibold text-sm rounded-lg hover:bg-primary-dark transition-all active:scale-95 shadow-sm"
        >
          New Application
        </button>
        <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-primary font-bold text-sm">
          G
        </div>
      </div>
    </header>
  )
}
