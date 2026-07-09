import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useDatasetStore, type FairnessAuditResult } from '../store/datasetStore'
import api from '../lib/api'
import toast from 'react-hot-toast'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, LabelList, Cell
} from 'recharts'
import {
  BarChart3, Brain, Loader2, ChevronDown, ChevronUp,
  Info, Shield, Trash2, Clock, CheckCircle
} from 'lucide-react'

// ── Score card ──────────────────────────────────────────────────────────────
function ScoreCard({ label, value, subtitle, color }: { label: string; value: string | number; subtitle?: string; color: string }) {
  return (
    <div className="card p-4">
      <div className={`text-3xl font-bold ${color} mb-1`}>{value}</div>
      <div className="text-sm font-semibold text-gray-700">{label}</div>
      {subtitle && <div className="text-xs text-gray-400 mt-0.5">{subtitle}</div>}
    </div>
  )
}

// ── Single audit result card ────────────────────────────────────────────────
function AuditCard({ result, index, total }: { result: FairnessAuditResult; index: number; total: number }) {
  const [showExplain, setShowExplain] = useState(false)
  const score = result.score ?? 0
  const scoreColor = score >= 80 ? 'text-green-600' : score >= 60 ? 'text-amber-600' : 'text-red-600'

  const raceData = result.approval_rates_by_group?.race
    ? Object.entries(result.approval_rates_by_group.race).map(([g, r]) => ({ group: g, rate: Math.round((r as number) * 100) }))
    : []
  const genderData = result.approval_rates_by_group?.gender
    ? Object.entries(result.approval_rates_by_group.gender).map(([g, r]) => ({ group: g, rate: Math.round((r as number) * 100) }))
    : []

  return (
    <div className="card border-l-4 border-l-navy-900 space-y-4 p-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <span className="bg-navy-900 text-white text-xs px-2.5 py-1 rounded-full font-semibold">
            Run #{total - index}
          </span>
          <span className="text-xs text-gray-500 flex items-center gap-1">
            <Clock className="w-3 h-3" />{new Date(result.timestamp).toLocaleString()}
          </span>
          <span className="text-xs text-gray-400 truncate max-w-32">{result.dataset_name}</span>
        </div>
        <span className={`text-lg font-bold ${scoreColor}`}>{score.toFixed(1)}/100</span>
      </div>

      {/* Score cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <ScoreCard label="Fairness Score" value={score.toFixed(1)} subtitle="Higher is better (0-100)" color={scoreColor} />
        <ScoreCard label="Race DI" value={result.disparate_impact_ratios?.race != null ? result.disparate_impact_ratios.race.toFixed(3) : '—'} subtitle="≥0.8 passes 4/5ths" color={(result.disparate_impact_ratios?.race ?? 1) >= 0.8 ? 'text-green-600' : 'text-red-600'} />
        <ScoreCard label="Gender DI" value={result.disparate_impact_ratios?.gender != null ? result.disparate_impact_ratios.gender.toFixed(3) : '—'} subtitle="≥0.8 passes 4/5ths" color={(result.disparate_impact_ratios?.gender ?? 1) >= 0.8 ? 'text-green-600' : 'text-red-600'} />
        <ScoreCard label="Bias Indicators" value={result.bias_indicators?.length ?? 0} subtitle="Flagged concerns" color={(result.bias_indicators?.length ?? 0) === 0 ? 'text-green-600' : 'text-red-600'} />
      </div>

      {/* DI ratio tiles */}
      {Object.keys(result.disparate_impact_ratios || {}).length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {Object.entries(result.disparate_impact_ratios).map(([key, ratio]) => (
            <div key={key} className={`p-2.5 rounded-lg border text-center ${(ratio as number) >= 0.8 ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
              <div className={`text-xl font-bold ${(ratio as number) >= 0.8 ? 'text-green-700' : 'text-red-700'}`}>{(ratio as number).toFixed(3)}</div>
              <div className="text-xs font-medium text-gray-600 capitalize mt-0.5">{key}</div>
              <div className={`text-xs mt-0.5 ${(ratio as number) >= 0.8 ? 'text-green-600' : 'text-red-600'}`}>{(ratio as number) >= 0.8 ? '✓ Passes 4/5ths' : '✗ Below threshold'}</div>
            </div>
          ))}
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {raceData.length > 0 && (
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-1">Approval Rates by Race</p>
            <p className="text-xs text-gray-400 mb-2">Red = below 80% threshold</p>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={raceData} margin={{ top: 16, right: 8, left: 0, bottom: 30 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="group" tick={{ fontSize: 10 }} angle={-20} textAnchor="end" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} unit="%" />
                <Tooltip formatter={(v: number) => [`${v}%`, 'Approval Rate']} />
                <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '80%', fontSize: 9, fill: '#ef4444', position: 'right' }} />
                <Bar dataKey="rate" radius={[3, 3, 0, 0]}>
                  <LabelList dataKey="rate" position="top" formatter={(v: number) => `${v}%`} style={{ fontSize: 10, fontWeight: 600, fill: '#374151' }} />
                  {raceData.map((e, i) => <Cell key={i} fill={e.rate >= 80 ? '#1a237e' : '#ef4444'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        {genderData.length > 0 && (
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-1">Approval Rates by Gender</p>
            <p className="text-xs text-gray-400 mb-2">Red = below 80% threshold</p>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={genderData} margin={{ top: 16, right: 8, left: 0, bottom: 30 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="group" tick={{ fontSize: 10 }} angle={-20} textAnchor="end" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} unit="%" />
                <Tooltip formatter={(v: number) => [`${v}%`, 'Approval Rate']} />
                <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '80%', fontSize: 9, fill: '#ef4444', position: 'right' }} />
                <Bar dataKey="rate" radius={[3, 3, 0, 0]}>
                  <LabelList dataKey="rate" position="top" formatter={(v: number) => `${v}%`} style={{ fontSize: 10, fontWeight: 600, fill: '#374151' }} />
                  {genderData.map((e, i) => <Cell key={i} fill={e.rate >= 80 ? '#3f51b5' : '#ef4444'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Findings collapsible */}
      {(result.findings?.length ?? 0) > 0 && (
        <details>
          <summary className="cursor-pointer text-sm font-semibold text-gray-700 flex items-center gap-2 select-none list-none">
            <BarChart3 className="w-4 h-4 text-blue-500" /> Key Findings ({result.findings.length})
            <ChevronDown className="w-3.5 h-3.5 ml-auto" />
          </summary>
          <ul className="mt-2 space-y-1 pl-4">
            {result.findings.map((f, i) => <li key={i} className="text-sm text-gray-700"><span className="text-blue-500 font-bold mr-1">{i+1}.</span>{f}</li>)}
          </ul>
        </details>
      )}

      {/* AI explanation */}
      {result.ai_explanation && (
        <div>
          <button onClick={() => setShowExplain(!showExplain)} className="flex items-center gap-2 text-sm font-semibold text-gray-700">
            <Brain className="w-4 h-4 text-purple-500" /> AI Explanation
            {showExplain ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          {showExplain && <div className="mt-2 text-sm text-gray-700 bg-purple-50 rounded-lg p-3 whitespace-pre-line">{result.ai_explanation}</div>}
        </div>
      )}
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────
export default function FairnessPage() {
  const { selectedId, getSelected, fairnessHistory, addFairnessResult, clearFairnessHistory } = useDatasetStore()
  const selected = getSelected()
  const history = selectedId ? (fairnessHistory[selectedId] ?? []) : []

  // Auto-detect columns when dataset changes
  const detectQuery = useQuery({
    queryKey: ['detect-columns', selectedId],
    queryFn: async () => {
      if (!selectedId) return null
      try { const res = await api.get(`/fairness/detect-columns/${selectedId}`); return res.data }
      catch { return null }
    },
    enabled: !!selectedId,
  })

  const auditMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) throw new Error('No dataset selected')
      const res = await api.post('/fairness/audit', { dataset_id: selectedId })
      return res.data
    },
    onSuccess: (data) => {
      const entry: FairnessAuditResult = {
        id: `${selectedId}-${Date.now()}`,
        dataset_id: selectedId!,
        dataset_name: selected?.filename ?? selectedId!,
        timestamp: new Date().toISOString(),
        score: data.score,
        disparate_impact_ratios: data.disparate_impact_ratios ?? {},
        approval_rates_by_group: data.approval_rates_by_group ?? {},
        bias_indicators: data.bias_indicators ?? [],
        findings: data.findings ?? [],
        recommendations: data.recommendations ?? [],
      }
      addFairnessResult(entry)
      toast.success(`Audit complete — Score: ${data.score?.toFixed(1)}`)
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Audit failed'),
  })

  const explainMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) throw new Error('No dataset selected')
      const res = await api.post('/fairness/ai-explain', { dataset_id: selectedId })
      return res.data
    },
    onSuccess: (data) => {
      const report = data.report ?? {}
      const entry: FairnessAuditResult = {
        id: `${selectedId}-explain-${Date.now()}`,
        dataset_id: selectedId!,
        dataset_name: selected?.filename ?? selectedId!,
        timestamp: new Date().toISOString(),
        score: report.score ?? 0,
        disparate_impact_ratios: report.disparate_impact_ratios ?? {},
        approval_rates_by_group: report.approval_rates_by_group ?? {},
        bias_indicators: report.bias_indicators ?? [],
        findings: report.findings ?? [],
        recommendations: report.recommendations ?? [],
        ai_explanation: data.ai_explanation,
      }
      addFairnessResult(entry)
      toast.success('AI explanation complete')
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Explanation failed'),
  })

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Fairness Dashboard</h1>
          <p className="text-gray-500 mt-1">4/5ths disparate impact analysis · ECOA & FHA compliance</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {history.length > 0 && (
            <>
              <button
                onClick={() => explainMutation.mutate()}
                disabled={explainMutation.isPending || !selectedId}
                className="btn-secondary flex items-center gap-2 text-sm"
              >
                {explainMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
                AI Explain
              </button>
              <button
                onClick={() => { if (confirm('Clear all audit history for this dataset?')) clearFairnessHistory(selectedId!) }}
                className="flex items-center gap-1.5 text-xs text-red-600 border border-red-200 hover:bg-red-50 px-3 py-1.5 rounded-lg transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" /> Clear History
              </button>
            </>
          )}
          <button
            onClick={() => auditMutation.mutate()}
            disabled={auditMutation.isPending || !selectedId}
            className="btn-primary flex items-center gap-2"
          >
            {auditMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <BarChart3 className="w-4 h-4" />}
            {auditMutation.isPending ? 'Running Audit…' : 'Run Fairness Audit'}
          </button>
        </div>
      </div>

      {/* No dataset selected */}
      {!selectedId && (
        <div className="card p-8 text-center">
          <Info className="w-10 h-10 text-blue-400 mx-auto mb-3" />
          <p className="text-gray-600 font-medium">Select a dataset from the top bar to run a fairness audit.</p>
        </div>
      )}

      {/* Dataset selected, no history yet */}
      {selectedId && history.length === 0 && !auditMutation.isPending && (
        <div className="card p-8 text-center">
          <Shield className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 mb-2">No fairness audit has been run for <strong>{selected?.filename}</strong> yet.</p>
          {detectQuery.data && (
            <div className="mt-3 mb-4 text-left max-w-md mx-auto bg-gray-50 rounded-lg p-3 text-xs text-gray-600 space-y-1">
              <div className="font-semibold text-gray-700 mb-1">Detected columns in this dataset:</div>
              <div>📊 Outcome: <span className="font-mono bg-white px-1 rounded">{detectQuery.data.detected_outcome_column || 'Not found'}</span></div>
              {Object.entries(detectQuery.data.detected_protected_columns || {}).map(([k, v]: any) => (
                <div key={k}>👥 {k}: <span className="font-mono bg-white px-1 rounded">{v}</span></div>
              ))}
              <div className="text-gray-400 mt-1">{detectQuery.data.total_rows?.toLocaleString()} rows · {detectQuery.data.dataset_type}</div>
            </div>
          )}
          <button onClick={() => auditMutation.mutate()} className="btn-primary">Run Fairness Audit</button>
        </div>
      )}

      {/* Loading */}
      {auditMutation.isPending && (
        <div className="card p-8 text-center">
          <Loader2 className="w-10 h-10 animate-spin text-navy-900 mx-auto mb-3" />
          <p className="text-gray-600 font-medium">Running fairness analysis on {selected?.filename}…</p>
        </div>
      )}

      {/* History — all runs, newest first */}
      {history.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <CheckCircle className="w-4 h-4 text-green-500" />
            <span>{history.length} audit run{history.length > 1 ? 's' : ''} — scroll to see all · results persist across navigation</span>
          </div>
          {history.map((r, i) => (
            <AuditCard key={r.id} result={r} index={i} total={history.length} />
          ))}
        </div>
      )}
    </div>
  )
}
