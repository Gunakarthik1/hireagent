import Icon from './Icon.jsx'

const NAV_PRIMARY = [
  { id: 'dashboard', label: 'Dashboard',       icon: 'dashboard' },
  { id: 'jobs',      label: 'Job Feed',         icon: 'work' },
]

const NAV_SECONDARY = [
  { id: 'profile',  label: 'Profile',   icon: 'account_circle' },
  { id: 'settings', label: 'Settings',  icon: 'settings' },
]

export default function Sidebar({ active, setActive, onRunScan, scanning }) {
  return (
    <aside className="fixed left-0 top-0 h-screen w-64 bg-slate-900 border-r border-slate-800 flex flex-col py-6 z-50">
      {/* Brand */}
      <div className="px-6 mb-8">
        <h1 className="text-xl font-bold text-white tracking-tight">HireAgent</h1>
        <p className="text-slate-500 text-xs mt-1">Autonomous Search</p>
      </div>

      {/* Primary Nav */}
      <nav className="space-y-1 px-2">
        {NAV_PRIMARY.map(item => (
          <button
            key={item.id}
            onClick={() => setActive(item.id)}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-all duration-150 ${
              active === item.id
                ? 'bg-[#2E3A8C] text-white shadow-lg shadow-indigo-900/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            <Icon name={item.icon} size={20} />
            <span className="text-sm font-medium">{item.label}</span>
          </button>
        ))}
      </nav>

      {/* Resume Branches — the main board */}
      <div className="px-2 mt-4">
        <div className="px-4 py-2 mb-1">
          <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Resume Board</p>
        </div>
        <button
          onClick={() => setActive('versions')}
          className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-all duration-150 ${
            active === 'versions'
              ? 'bg-[#2E3A8C] text-white shadow-lg shadow-indigo-900/20'
              : 'text-slate-300 hover:text-white hover:bg-slate-800 border border-slate-700'
          }`}
        >
          <Icon name="description" size={20} />
          <div className="flex-1">
            <span className="text-sm font-semibold">Resume Branches</span>
            <p className={`text-[10px] mt-0.5 ${active === 'versions' ? 'text-indigo-300' : 'text-slate-500'}`}>
              Versions · ATS board
            </p>
          </div>
          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide ${
            active === 'versions' ? 'bg-white/20 text-white' : 'bg-emerald-500/20 text-emerald-400'
          }`}>
            Main
          </span>
        </button>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Run Scan CTA */}
      <div className="px-4 mb-4">
        <button
          onClick={onRunScan}
          disabled={scanning}
          className="w-full bg-[#2E3A8C] hover:bg-[#3d4ea8] disabled:opacity-60 text-white font-semibold py-3 rounded-xl transition-all active:scale-95 flex items-center justify-center gap-2 text-sm shadow-lg shadow-indigo-900/20"
        >
          {scanning ? (
            <>
              <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
              Scanning…
            </>
          ) : (
            <>
              <Icon name="bolt" size={18} />
              Run Scan
            </>
          )}
        </button>
      </div>

      {/* Bottom Nav */}
      <div className="border-t border-slate-800 pt-3 px-2 space-y-1">
        {NAV_SECONDARY.map(item => (
          <button
            key={item.id}
            onClick={() => setActive(item.id)}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-left transition-all duration-150 ${
              active === item.id
                ? 'bg-[#2E3A8C] text-white'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            <Icon name={item.icon} size={18} />
            <span className="text-sm font-medium">{item.label}</span>
          </button>
        ))}
        <button className="w-full flex items-center gap-3 px-4 py-2.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors text-left">
          <Icon name="help" size={18} />
          <span className="text-sm">Help</span>
        </button>
      </div>
    </aside>
  )
}
