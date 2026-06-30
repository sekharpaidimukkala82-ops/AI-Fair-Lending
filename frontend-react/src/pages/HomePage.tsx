import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { useDatasetStore } from '../store/datasetStore'
import {
  Upload, BarChart3, Brain, MessageSquare, Search, FileText,
  ArrowRight, TrendingUp, Shield, Database
} from 'lucide-react'

const features = [
  { to: '/upload', icon: Upload, color: 'bg-blue-500', title: 'Upload & Process', desc: 'Ingest CSV, XLSX, JSON datasets with auto schema detection and HMDA code translation.' },
  { to: '/fairness', icon: BarChart3, color: 'bg-red-500', title: 'Fairness Audit', desc: '4/5ths disparate impact analysis across race, gender, age, and ethnicity groups.' },
  { to: '/chat', icon: MessageSquare, color: 'bg-green-500', title: 'AI Assistant', desc: 'RAG-powered conversational AI grounded in your actual lending data.' },
  { to: '/ml', icon: Brain, color: 'bg-amber-500', title: 'ML Engine', desc: 'RandomForest approval prediction, anomaly detection, and applicant segmentation.' },
  { to: '/search', icon: Search, color: 'bg-purple-500', title: 'Semantic Search', desc: 'Vector similarity search across applicants, loans, and policy documents.' },
  { to: '/reports', icon: FileText, color: 'bg-teal-500', title: 'Compliance Reports', desc: 'Download PDF/JSON fairness, compliance, risk, and executive summary reports.' },
]

export default function HomePage() {
  const { user } = useAuthStore()
  const { datasets } = useDatasetStore()

  const { data: monitoring } = useQuery({
    queryKey: ['monitoring-home'],
    queryFn: () => { const base = import.meta.env.VITE_API_URL || ''; return fetch(`${base}/monitoring/dashboard`).then(r => r.json()) },
    refetchInterval: 30000,
  })

  const completedDatasets = datasets.filter(d => d.status === 'completed')

  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className="bg-gradient-to-r from-navy-900 to-blue-700 rounded-2xl p-8 text-white">
        <div className="flex items-center gap-3 mb-4">
          <Shield className="w-10 h-10 text-blue-300" />
          <div>
            <h1 className="text-2xl font-bold">Fair Lending Intelligence Platform</h1>
            <p className="text-blue-200 text-sm">Welcome back, {user?.full_name || user?.username}</p>
          </div>
        </div>
        <p className="text-blue-100 max-w-2xl mb-6">
          AI-powered HMDA analysis, disparate impact detection, semantic search, and compliance reporting —
          built for enterprise fair lending compliance teams.
        </p>
        <div className="flex gap-3 flex-wrap">
          <Link to="/upload" className="flex items-center gap-2 bg-white text-navy-900 px-5 py-2.5 rounded-lg font-semibold hover:bg-blue-50 transition-colors">
            <Upload className="w-4 h-4" /> Upload Dataset
          </Link>
          <Link to="/chat" className="flex items-center gap-2 bg-blue-500/30 text-white border border-blue-400/40 px-5 py-2.5 rounded-lg font-semibold hover:bg-blue-500/50 transition-colors">
            <MessageSquare className="w-4 h-4" /> Ask AI Assistant
          </Link>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Datasets Uploaded', value: completedDatasets.length, icon: Database, color: 'text-blue-600' },
          { label: 'Total Queries', value: monitoring?.total_queries ?? 0, icon: MessageSquare, color: 'text-green-600' },
          {
            label: 'Avg Fairness Score',
            value: monitoring?.average_fairness_score != null
              ? (monitoring.average_fairness_score as number).toFixed(1)
              : '—',
            icon: TrendingUp,
            color: 'text-amber-600',
          },
          {
            label: 'Open Alerts',
            value: ((monitoring?.recent_alerts as any[]) || []).filter((a: any) => !a.resolved).length,
            icon: Shield,
            color: 'text-red-600',
          },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="card p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</span>
              <Icon className={`w-5 h-5 ${color}`} />
            </div>
            <div className="text-3xl font-bold text-gray-900">{value}</div>
          </div>
        ))}
      </div>

      {/* Features */}
      <div>
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Platform Capabilities</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {features.map(({ to, icon: Icon, color, title, desc }) => (
            <Link key={to} to={to} className="card p-5 hover:shadow-md transition-shadow group">
              <div className={`w-10 h-10 ${color} rounded-xl flex items-center justify-center mb-3`}>
                <Icon className="w-5 h-5 text-white" />
              </div>
              <h3 className="font-semibold text-gray-900 mb-1 group-hover:text-navy-900">{title}</h3>
              <p className="text-sm text-gray-500 leading-relaxed">{desc}</p>
              <div className="flex items-center gap-1 text-navy-900 text-sm font-medium mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
                Open <ArrowRight className="w-4 h-4" />
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* Quick Start */}
      {completedDatasets.length === 0 && (
        <div className="card p-6 border-dashed border-2 border-blue-200 bg-blue-50/30">
          <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <span className="w-6 h-6 bg-navy-900 text-white rounded-full flex items-center justify-center text-xs font-bold">!</span>
            Quick Start — Upload your first dataset
          </h3>
          <div className="grid grid-cols-4 gap-4">
            {['Upload CSV/XLSX dataset', 'Auto schema detection', 'Run Fairness Audit', 'Download Reports'].map((step, i) => (
              <div key={step} className="text-center">
                <div className="w-8 h-8 bg-navy-900 text-white rounded-full flex items-center justify-center font-bold text-sm mx-auto mb-2">
                  {i + 1}
                </div>
                <p className="text-sm text-gray-600">{step}</p>
              </div>
            ))}
          </div>
          <Link to="/upload" className="btn-primary mt-5 inline-flex items-center gap-2">
            <Upload className="w-4 h-4" /> Upload Now
          </Link>
        </div>
      )}
    </div>
  )
}
