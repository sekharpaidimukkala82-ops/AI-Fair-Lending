import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { useDatasetStore } from '../store/datasetStore'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'
import {
  Home, Upload, MessageSquare, Search, BarChart3, Brain,
  FileText, Activity, Settings, LogOut, Database, Scale,
  ShieldCheck, ShieldAlert, ClipboardCheck
} from 'lucide-react'

const navItems = [
  { to: '/', icon: Home, label: 'Home', exact: true },
  { to: '/upload', icon: Upload, label: 'Upload Data' },
  { to: '/chat', icon: MessageSquare, label: 'AI Assistant' },
  { to: '/search', icon: Search, label: 'Semantic Search' },
  { to: '/fairness', icon: BarChart3, label: 'Fairness Dashboard' },
  { to: '/fairness/advanced', icon: ShieldCheck, label: 'Advanced Fairness' },
  { to: '/cases', icon: ShieldAlert, label: 'Cases' },
  { to: '/compliance', icon: ClipboardCheck, label: 'Compliance' },
  { to: '/ml', icon: Brain, label: 'ML Engine' },
  { to: '/reports', icon: FileText, label: 'Reports' },
  { to: '/monitoring', icon: Activity, label: 'Monitoring' },
  { to: '/settings', icon: Settings, label: 'AI Settings' },
]

export default function Layout() {
  const { user, logout } = useAuthStore()
  const { datasets, selectedId, setDatasets, setSelected } = useDatasetStore()
  const navigate = useNavigate()

  // Load datasets
  useQuery({
    queryKey: ['datasets'],
    queryFn: async () => {
      const res = await api.get('/upload/list')
      const completed = (res.data.uploads || []).filter((d: any) => d.status === 'completed')
      setDatasets(completed)
      if (!selectedId && completed.length > 0) setSelected(completed[0].file_id)
      return completed
    },
    refetchInterval: 15000,
  })

  // Health check
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => { const base = import.meta.env.VITE_API_URL || ''; return fetch(`${base}/health`).then(r => r.json()) },
    refetchInterval: 30000,
  })

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-navy-900 flex flex-col flex-shrink-0">
        {/* Brand */}
        <div className="flex items-center gap-3 px-5 py-5 border-b border-white/10">
          <Scale className="w-8 h-8 text-blue-300 flex-shrink-0" />
          <div>
            <div className="text-white font-bold text-base leading-tight">FairLend AI</div>
            <div className="text-blue-300 text-xs">Enterprise Platform</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {navItems.map(({ to, icon: Icon, label, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-navy-600 text-white border-l-2 border-blue-300'
                    : 'text-blue-100 hover:bg-navy-800 hover:text-white'
                }`
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* User footer */}
        <div className="px-4 py-4 border-t border-white/10">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
              {user?.username?.[0]?.toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-white text-sm font-medium truncate">{user?.full_name || user?.username}</div>
              <div className="text-blue-300 text-xs capitalize">{user?.role}</div>
            </div>
            <button onClick={handleLogout} className="text-blue-300 hover:text-white transition-colors" title="Logout">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
          <div className="mt-3">
            <div className={`flex items-center gap-1.5 text-xs ${health?.status === 'healthy' ? 'text-green-400' : 'text-red-400'}`}>
              <div className={`w-2 h-2 rounded-full ${health?.status === 'healthy' ? 'bg-green-400' : 'bg-red-400'}`} />
              API {health?.status === 'healthy' ? 'Online' : 'Offline'}
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Topbar */}
        <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-4 flex-shrink-0">
          <h1 className="text-lg font-semibold text-gray-800 flex-1">Dashboard</h1>

          {/* Global dataset selector */}
          <div className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
            <Database className="w-4 h-4 text-blue-600 flex-shrink-0" />
            <span className="text-xs font-semibold text-blue-700 whitespace-nowrap">Dataset:</span>
            <select
              value={selectedId || ''}
              onChange={e => setSelected(e.target.value || null)}
              className="text-sm bg-transparent border-none outline-none text-gray-700 max-w-48"
            >
              <option value="">— Select dataset —</option>
              {datasets.map(d => (
                <option key={d.file_id} value={d.file_id}>
                  {d.filename} {d.total_rows ? `(${d.total_rows.toLocaleString()} rows)` : ''}
                </option>
              ))}
            </select>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
