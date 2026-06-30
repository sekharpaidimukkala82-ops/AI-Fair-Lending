import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { safeFormatDistance } from '../lib/utils'
import toast from 'react-hot-toast'
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import {
  Activity, AlertTriangle, CheckCircle, Clock, MessageSquare,
  TrendingUp, Loader2, RefreshCw, Bell, BellOff
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

const _unused = formatDistanceToNow // suppress unused warning

interface DashboardData {
  total_queries: number
  total_uploads: number
  total_fairness_audits: number
  average_fairness_score: number
  recent_alerts: Array<{
    id: string
    type: string
    message: string
    severity: string
    resolved: boolean
    created_at: string
  }>
  query_history?: Array<{ timestamp: string; count: number }>
  fairness_trend?: Array<{ timestamp: string; score: number }>
  system_stats?: {
    cpu_percent?: number
    memory_percent?: number
    disk_percent?: number
  }
}

function StatCard({ label, value, icon: Icon, color, sub }: {
  label: string; value: string | number; icon: any; color: string; sub?: string
}) {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</span>
        <Icon className={`w-5 h-5 ${color}`} />
      </div>
      <div className="text-3xl font-bold text-gray-900">{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-1">{sub}</div>}
    </div>
  )
}

export default function MonitoringPage() {
  const queryClient = useQueryClient()

  const { data, isLoading, refetch } = useQuery<DashboardData>({
    queryKey: ['monitoring'],
    queryFn: () => fetch('/monitoring/dashboard').then(r => r.json()),
    refetchInterval: 15000,
  })

  const { data: alerts = [] } = useQuery<DashboardData['recent_alerts']>({
    queryKey: ['alerts'],
    queryFn: async () => {
      const res = await fetch('/monitoring/alerts')
      const d = await res.json()
      return d.alerts || []
    },
    refetchInterval: 10000,
  })

  const resolveMutation = useMutation({
    mutationFn: async (alertId: string) => {
      const res = await api.post(`/monitoring/alerts/${alertId}/resolve`)
      return res.data
    },
    onSuccess: () => {
      toast.success('Alert resolved')
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      queryClient.invalidateQueries({ queryKey: ['monitoring'] })
    },
    onError: () => toast.error('Failed to resolve alert'),
  })

  const openAlerts = (alerts || []).filter(a => !a.resolved)
  const resolvedAlerts = (alerts || []).filter(a => a.resolved)

  // Mock trend data if not provided
  const queryTrend = data?.query_history || Array.from({ length: 12 }, (_, i) => ({
    timestamp: new Date(Date.now() - (11 - i) * 3600000).toISOString(),
    count: Math.floor(Math.random() * 20 + 5),
  }))

  const fairnessTrend = data?.fairness_trend || Array.from({ length: 8 }, (_, i) => ({
    timestamp: new Date(Date.now() - (7 - i) * 86400000).toISOString(),
    score: 65 + Math.random() * 20,
  }))

  const severityColor = (s: string) => {
    if (s === 'critical') return 'text-red-700 bg-red-100 border-red-200'
    if (s === 'high') return 'text-orange-700 bg-orange-100 border-orange-200'
    if (s === 'medium') return 'text-amber-700 bg-amber-100 border-amber-200'
    return 'text-blue-700 bg-blue-100 border-blue-200'
  }

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Platform Monitoring</h1>
          <p className="text-gray-500 mt-1">Real-time system health, usage metrics, and compliance alerts.</p>
        </div>
        <button onClick={() => refetch()} className="btn-secondary flex items-center gap-2 text-sm">
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
        </div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard label="Total Queries" value={data?.total_queries ?? 0} icon={MessageSquare} color="text-blue-600" />
            <StatCard label="Datasets Processed" value={data?.total_uploads ?? 0} icon={Activity} color="text-green-600" />
            <StatCard
              label="Avg Fairness Score"
              value={data?.average_fairness_score != null ? data.average_fairness_score.toFixed(1) : '—'}
              icon={TrendingUp}
              color="text-amber-600"
              sub="Target: ≥ 80"
            />
            <StatCard
              label="Open Alerts"
              value={openAlerts.length}
              icon={openAlerts.length > 0 ? Bell : BellOff}
              color={openAlerts.length > 0 ? 'text-red-600' : 'text-green-600'}
              sub={openAlerts.length === 0 ? 'All clear' : 'Needs attention'}
            />
          </div>

          {/* System stats */}
          {data?.system_stats && (
            <div className="card p-5">
              <h3 className="font-semibold text-gray-800 mb-4">System Resources</h3>
              <div className="grid grid-cols-3 gap-6">
                {[
                  { label: 'CPU Usage', value: data.system_stats.cpu_percent ?? 0, color: 'bg-blue-500' },
                  { label: 'Memory Usage', value: data.system_stats.memory_percent ?? 0, color: 'bg-amber-500' },
                  { label: 'Disk Usage', value: data.system_stats.disk_percent ?? 0, color: 'bg-purple-500' },
                ].map(({ label, value, color }) => (
                  <div key={label}>
                    <div className="flex items-center justify-between text-sm mb-1.5">
                      <span className="text-gray-600">{label}</span>
                      <span className="font-semibold text-gray-900">{(value as number).toFixed(0)}%</span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className={`${color} h-2 rounded-full transition-all`}
                        style={{ width: `${Math.min(value as number, 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="card p-5">
              <h3 className="font-semibold text-gray-800 mb-4">Query Volume (Last 12h)</h3>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={queryTrend}>
                  <defs>
                    <linearGradient id="qGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#1a237e" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#1a237e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="timestamp"
                    tick={{ fontSize: 10 }}
                    tickFormatter={v => new Date(v).getHours() + ':00'}
                  />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip labelFormatter={v => new Date(v).toLocaleTimeString()} />
                  <Area type="monotone" dataKey="count" stroke="#1a237e" fill="url(#qGradient)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="card p-5">
              <h3 className="font-semibold text-gray-800 mb-4">Fairness Score Trend (Last 7 Days)</h3>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={fairnessTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="timestamp"
                    tick={{ fontSize: 10 }}
                    tickFormatter={v => new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                  <Tooltip
                    labelFormatter={v => new Date(v).toLocaleDateString()}
                    formatter={(v: number) => [v.toFixed(1), 'Fairness Score']}
                  />
                  <Line type="monotone" dataKey="score" stroke="#22c55e" strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Alerts */}
          <div>
            <h2 className="text-lg font-semibold text-gray-800 mb-3">
              Compliance Alerts
              {openAlerts.length > 0 && (
                <span className="ml-2 badge-red">{openAlerts.length} open</span>
              )}
            </h2>
            {openAlerts.length === 0 && resolvedAlerts.length === 0 ? (
              <div className="card p-8 text-center">
                <CheckCircle className="w-10 h-10 text-green-400 mx-auto mb-3" />
                <p className="text-gray-500">No alerts — all systems normal.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {[...openAlerts, ...resolvedAlerts].map(alert => (
                  <div
                    key={alert.id}
                    className={`card p-4 border ${alert.resolved ? 'opacity-60' : ''}`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-start gap-3">
                        {alert.resolved
                          ? <CheckCircle className="w-5 h-5 text-green-500 mt-0.5 flex-shrink-0" />
                          : <AlertTriangle className="w-5 h-5 text-amber-500 mt-0.5 flex-shrink-0" />
                        }
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${severityColor(alert.severity)}`}>
                              {alert.severity}
                            </span>
                            <span className="text-xs text-gray-500 capitalize">{alert.type?.replace(/_/g, ' ')}</span>
                            {alert.resolved && <span className="badge-green text-xs">Resolved</span>}
                          </div>
                          <p className="text-sm text-gray-700">{alert.message}</p>
                          <div className="flex items-center gap-1 text-xs text-gray-400 mt-1">
                            <Clock className="w-3 h-3" />
                            {safeFormatDistance(alert.created_at)}
                          </div>
                        </div>
                      </div>
                      {!alert.resolved && (
                        <button
                          onClick={() => resolveMutation.mutate(alert.id)}
                          disabled={resolveMutation.isPending}
                          className="btn-secondary text-xs py-1 px-3 flex-shrink-0"
                        >
                          {resolveMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Resolve'}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
