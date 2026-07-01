import { useState, useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useDatasetStore } from '../store/datasetStore'
import api from '../lib/api'
import toast from 'react-hot-toast'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell
} from 'recharts'
import { Brain, Loader2, Target, TrendingUp, AlertTriangle, Users, Info, ChevronDown, ChevronUp } from 'lucide-react'

interface MLResult {
  accuracy: number
  model_id: string
  feature_importance: Record<string, number>
  training_rows: number
  features_used: string[]
  predictions_summary?: {
    approved: number
    denied: number
    approval_rate: number
  }
}

interface AnomalyResult {
  anomaly_count: number
  anomaly_rate: number
  anomalies: Array<{ index: number; score: number; reason?: string }>
}

interface ClusterResult {
  n_clusters: number
  cluster_sizes: Record<string, number>
  cluster_profiles: Record<string, Record<string, number>>
}

export default function MLPage() {
  const { selectedId, getSelected } = useDatasetStore()
  const selected = getSelected()
  const [mlResult, setMlResult] = useState<MLResult | null>(null)
  const [anomalyResult, setAnomalyResult] = useState<AnomalyResult | null>(null)
  const [clusterResult, setClusterResult] = useState<ClusterResult | null>(null)
  const [showFeatures, setShowFeatures] = useState(true)

  // Clear all results when dataset changes — never show stale data
  useEffect(() => {
    setMlResult(null)
    setAnomalyResult(null)
    setClusterResult(null)
  }, [selectedId])

  const trainMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) throw new Error('No dataset selected')
      const res = await api.post('/ml/train', { dataset_id: selectedId })
      return res.data
    },
    onSuccess: (data) => { setMlResult(data); toast.success(`Model trained — accuracy: ${(data.accuracy * 100).toFixed(1)}%`) },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Training failed'),
  })

  const anomalyMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) throw new Error('No dataset selected')
      const res = await api.post('/ml/anomalies', { dataset_id: selectedId })
      return res.data
    },
    onSuccess: (data) => {
      setAnomalyResult({
        anomaly_count: data.anomaly_count || 0,
        anomaly_rate: data.total_records ? data.anomaly_count / data.total_records : 0,
        anomalies: (data.anomaly_indices || []).slice(0, 20).map((idx: number) => ({ index: idx, score: 0 })),
      })
      toast.success(`Anomaly detection complete — ${data.anomaly_count} found`)
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Anomaly detection failed'),
  })

  const clusterMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) throw new Error('No dataset selected')
      const res = await api.post('/ml/segments', { dataset_id: selectedId })
      return res.data
    },
    onSuccess: (data) => {
      setClusterResult({
        n_clusters: data.num_clusters || 0,
        cluster_sizes: data.segment_sizes || {},
        cluster_profiles: data.cluster_profiles || {},
      })
      toast.success(`Clustering complete — ${data.num_clusters} segments found`)
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Clustering failed'),
  })

  // Feature importance chart data
  const featureData = mlResult?.feature_importance
    ? Object.entries(mlResult.feature_importance)
        .sort((a, b) => (b[1] as number) - (a[1] as number))
        .slice(0, 12)
        .map(([name, importance]) => ({
          name: name.replace(/_/g, ' ').substring(0, 20),
          importance: Math.round((importance as number) * 1000) / 10,
        }))
    : []

  const COLORS = ['#1a237e', '#283593', '#303f9f', '#3949ab', '#3f51b5', '#5c6bc0', '#7986cb', '#9fa8da', '#c5cae9', '#e8eaf6', '#bbdefb', '#90caf9']

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">ML Engine</h1>
        <p className="text-gray-500 mt-1">Train approval prediction models, detect anomalies, and segment applicants.</p>
      </div>

      {!selectedId && (
        <div className="card p-8 text-center">
          <Info className="w-10 h-10 text-blue-400 mx-auto mb-3" />
          <p className="text-gray-600">Select a dataset from the top bar to run ML analysis.</p>
        </div>
      )}

      {/* Action buttons */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card p-5">
          <Brain className="w-8 h-8 text-amber-500 mb-3" />
          <h3 className="font-semibold text-gray-800 mb-1">Approval Model</h3>
          <p className="text-xs text-gray-500 mb-4">Train RandomForest classifier to predict loan approvals and compute feature importance.</p>
          <button
            onClick={() => trainMutation.mutate()}
            disabled={trainMutation.isPending || !selectedId}
            className="btn-primary w-full flex items-center justify-center gap-2 text-sm"
          >
            {trainMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
            {trainMutation.isPending ? 'Training…' : 'Train Model'}
          </button>
        </div>
        <div className="card p-5">
          <AlertTriangle className="w-8 h-8 text-red-500 mb-3" />
          <h3 className="font-semibold text-gray-800 mb-1">Anomaly Detection</h3>
          <p className="text-xs text-gray-500 mb-4">Isolate outlier applications using Isolation Forest for unusual lending patterns.</p>
          <button
            onClick={() => anomalyMutation.mutate()}
            disabled={anomalyMutation.isPending || !selectedId}
            className="btn-secondary w-full flex items-center justify-center gap-2 text-sm"
          >
            {anomalyMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <AlertTriangle className="w-4 h-4" />}
            {anomalyMutation.isPending ? 'Detecting…' : 'Detect Anomalies'}
          </button>
        </div>
        <div className="card p-5">
          <Users className="w-8 h-8 text-purple-500 mb-3" />
          <h3 className="font-semibold text-gray-800 mb-1">Applicant Clustering</h3>
          <p className="text-xs text-gray-500 mb-4">K-Means segmentation to identify applicant profiles and risk groups.</p>
          <button
            onClick={() => clusterMutation.mutate()}
            disabled={clusterMutation.isPending || !selectedId}
            className="btn-secondary w-full flex items-center justify-center gap-2 text-sm"
          >
            {clusterMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Users className="w-4 h-4" />}
            {clusterMutation.isPending ? 'Clustering…' : 'Cluster Applicants'}
          </button>
        </div>
      </div>

      {/* ML Results */}
      {mlResult && (
        <div className="space-y-4">
          {/* Stats */}
          <div className="grid grid-cols-3 gap-4">
            <div className="card p-4 text-center">
              <div className="text-3xl font-bold text-green-600">{(mlResult.accuracy * 100).toFixed(1)}%</div>
              <div className="text-xs text-gray-500 mt-1">Model Accuracy</div>
            </div>
            <div className="card p-4 text-center">
              <div className="text-3xl font-bold text-blue-600">{mlResult.training_rows?.toLocaleString()}</div>
              <div className="text-xs text-gray-500 mt-1">Training Rows</div>
            </div>
            <div className="card p-4 text-center">
              <div className="text-3xl font-bold text-navy-900">{mlResult.features_used?.length || 0}</div>
              <div className="text-xs text-gray-500 mt-1">Features Used</div>
            </div>
          </div>

          {/* Feature importance */}
          {featureData.length > 0 && (
            <div className="card p-5">
              <button
                onClick={() => setShowFeatures(!showFeatures)}
                className="w-full flex items-center justify-between font-semibold text-gray-800 mb-3"
              >
                <span className="flex items-center gap-2"><TrendingUp className="w-4 h-4 text-amber-500" /> Feature Importance (Top {featureData.length})</span>
                {showFeatures ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
              {showFeatures && (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={featureData} layout="vertical" margin={{ top: 0, right: 20, left: 100, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 11 }} unit="%" domain={[0, 'auto']} />
                    <YAxis dataKey="name" type="category" tick={{ fontSize: 11 }} width={100} />
                    <Tooltip formatter={(v: number) => [`${v}%`, 'Importance']} />
                    <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
                      {featureData.map((_, index) => (
                        <Cell key={index} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          )}
        </div>
      )}

      {/* Anomaly Results */}
      {anomalyResult && (
        <div className="card p-5">
          <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-500" /> Anomaly Detection Results
          </h3>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div className="bg-red-50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-red-700">{anomalyResult.anomaly_count}</div>
              <div className="text-xs text-red-600">Anomalies Detected</div>
            </div>
            <div className="bg-amber-50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-amber-700">{(anomalyResult.anomaly_rate * 100).toFixed(1)}%</div>
              <div className="text-xs text-amber-600">Anomaly Rate</div>
            </div>
          </div>
          {anomalyResult.anomalies?.length > 0 && (
            <div className="max-h-48 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="text-left px-3 py-2 font-semibold text-gray-600">Row Index</th>
                    <th className="text-right px-3 py-2 font-semibold text-gray-600">Anomaly Score</th>
                    {anomalyResult.anomalies[0]?.reason && <th className="text-left px-3 py-2 font-semibold text-gray-600">Reason</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {anomalyResult.anomalies.slice(0, 20).map((a, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-3 py-2 text-gray-700">Row {a.index}</td>
                      <td className="px-3 py-2 text-right text-red-600 font-medium">{a.score.toFixed(4)}</td>
                      {a.reason && <td className="px-3 py-2 text-gray-500">{a.reason}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Cluster Results */}
      {clusterResult && (
        <div className="card p-5">
          <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <Users className="w-4 h-4 text-purple-500" /> Applicant Segments ({clusterResult.n_clusters} clusters)
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Object.entries(clusterResult.cluster_sizes).map(([cluster, size]) => (
              <div key={cluster} className="bg-purple-50 border border-purple-200 rounded-lg p-3">
                <div className="text-lg font-bold text-purple-700">{(size as number).toLocaleString()}</div>
                <div className="text-xs font-medium text-gray-600">{cluster}</div>
                {clusterResult.cluster_profiles?.[cluster] && (
                  <div className="mt-2 space-y-0.5">
                    {Object.entries(clusterResult.cluster_profiles[cluster]).slice(0, 3).map(([k, v]) => (
                      <div key={k} className="text-xs text-gray-500">
                        <span className="font-medium">{k.replace(/_/g, ' ')}:</span>{' '}
                        {typeof v === 'number'
                          ? v.toFixed(1)
                          : typeof v === 'object' && v !== null
                          ? Object.entries(v as Record<string, number>).map(([sk, sv]) =>
                              `${sk.replace(/_/g, ' ')}: ${typeof sv === 'number' ? sv.toFixed(1) : sv}`
                            ).join(', ')
                          : String(v)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
