import Icon from './Icon.jsx'

const NAV = [
  { id: 'dashboard', label: 'Overview',      icon: 'space_dashboard' },
  { id: 'jobs',      label: 'Job Feed',       icon: 'work_outline' },
  { id: 'versions',  label: 'Resume Boards',  icon: 'description' },
]

const NAV_BOTTOM = [
  { id: 'profile',  label: 'Profile',   icon: 'account_circle' },
  { id: 'settings', label: 'Settings',  icon: 'tune' },
]

export default function Sidebar({ active, setActive, onRunScan, scanning }) {
  return (
    <aside className="fixed left-0 top-0 h-screen w-60 bg-ink flex flex-col z-50">
      {/* Brand */}
      <div className="px-6 pt-7 pb-6 border-b border-white/5">
        <h1 className="font-serif text-2xl text-white leading-none">HireAgent</h1>
        <p className="text-white/30 text-xs mt-1.5 font-medium tracking-wide">Your job search, automated.</p>
      </div>

      {/* Run Scan */}
      <div className="px-4 pt-5">
        <button
          onClick={onRunScan}
          disabled={scanning}
          className="w-full bg-cobalt hover:bg-cobalt-dark disabled:opacity-60 text-white font-semibold py-2.5 rounded-xl transition-all active:scale-95 flex items-center justify-center gap-2 text-sm"
        >
          {scanning ? (
            <>
              <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
              Scanning…
            </>
          ) : (
            <>
              <Icon name="bolt" size={17} />
              Run Scan
            </>
          )}
        </button>
      </div>

      {/* Primary Nav */}
      <nav className="mt-6 px-2 space-y-0.5 flex-1">
        <p className="px-4 text-[10px] font-semibold text-white/25 uppercase tracking-widest mb-2">Navigation</p>
        {NAV.map(item => (
          <button
            key={item.id}
            onClick={() => setActive(item.id)}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-left transition-all duration-150 text-sm font-medium ${
              active === item.id
                ? 'bg-cobalt text-white'
                : 'text-white/45 hover:text-white/80 hover:bg-white/5'
            }`}
          >
            <Icon name={item.icon} size={18} />
            {item.label}
          </button>
        ))}
      </nav>

      {/* Bottom Nav */}
      <div className="border-t border-white/5 px-2 py-3 space-y-0.5">
        {NAV_BOTTOM.map(item => (
          <button
            key={item.id}
            onClick={() => setActive(item.id)}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-left transition-all duration-150 text-sm font-medium ${
              active === item.id
                ? 'bg-cobalt text-white'
                : 'text-white/40 hover:text-white/70 hover:bg-white/5'
            }`}
          >
            <Icon name={item.icon} size={18} />
            {item.label}
          </button>
        ))}
      </div>
    </aside>
  )
}
