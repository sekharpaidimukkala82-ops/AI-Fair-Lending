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
  Info, Shield, Trash2, CheckCircle, AlertTriangle
} from 'lucide-react'

function ScoreCard({ label, value, subtitle, color }: { label: string; value: string | number; subtitle?: string; color: string }) {
  return (
    <div className="card p-4">
      <div className={`text-3xl font-bold ${color} mb-1`}>{value}</div>
      <div className="text-sm font-semibold text-gray-700">{label}</div>
      {subtitle && <div className="text-xs text-gray-400 mt-0.5">{subtitle}</div>}
    </div>
  )
}

function AuditResult({ result }: { result: FairnessAuditResult }) {
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
    <div className="space-y-5">
      {/* Score cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <ScoreCard label="Overall Fairness Score" value={score.toFixed(1)} subtitle="Higher is better (0–100)" color={scoreColor} />
        <ScoreCard label="Race DI Ratio" value={result.disparate_impact_ratios?.race != null ? result.disparate_impact_ratios.race.toFixed(3) : '—'} subtitle="≥0.8 passes 4/5ths rule" color={(result.disparate_impact_ratios?.race ?? 1) >= 0.8 ? 'text-green-600' : 'text-red-600'} />
        <ScoreCard label="Gender DI Ratio" value={result.disparate_impact_ratios?.gender != null ? result.disparate_impact_ratios.gender.toFixed(3) : '—'} subtitle="≥0.8 passes 4/5ths rule" color={(result.disparate_impact_ratios?.gender ?? 1) >= 0.8 ? 'text-green-600' : 'text-red-600'} />
        <ScoreCard label="Bias Indicators" value={result.bias_indicators?.length ?? 0} subtitle="Flagged concerns" color={(result.bias_indicators?.length ?? 0) === 0 ? 'text-green-600' : 'text-red-600'} />
      </div>

      {/* No-bias notice */}
      {score === 100 && (result.bias_indicators?.length ?? 0) === 0 && (
        <div className="card p-4 border-green-200 bg-green-50 flex items-start gap-3">
          <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-semibold text-green-800">No bias detected in this dataset</div>
            <div className="text-sm text-green-700 mt-0.5">All demographic groups show similar approval rates.</div>
          </div>
        </div>
      )}

      {/* DI ratio tiles */}
      {Object.keys(result.disparate_impact_ratios || {}).length > 0 && (
        <div className="card p-5">
          <h3 className="font-semibold text-gray-800 mb-4">Disparate Impact Ratios by Protected Class</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(result.disparate_impact_ratios).map(([key, ratio]) => (
              <div key={key} className={`p-3 rounded-lg border text-center ${(ratio as number) >= 0.8 ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                <div className={`text-2xl font-bold ${(ratio as number) >= 0.8 ? 'text-green-700' : 'text-red-700'}`}>{(ratio as number).toFixed(3)}</div>
                <div className="text-xs font-medium text-gray-600 capitalize mt-0.5">{key}</div>
                <div className={`text-xs mt-0.5 ${(ratio as number) >= 0.8 ? 'text-green-600' : 'text-red-600'}`}>{(ratio as number) >= 0.8 ? '✓ Passes 4/5ths' : '✗ Below threshold'}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {raceData.length > 0 && (
          <div className="card p-5">
            <h3 className="font-semibold text-gray-800 mb-1">Approval Rates by Race</h3>
            <p className="text-xs text-gray-500 mb-4">Red bars are below the 80% fairness threshold</p>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={raceData} margin={{ top: 20, right: 10, left: 0, bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="group" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                <Tooltip formatter={(v: number) => [`${v}%`, 'Approval Rate']} />
                <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '80% threshold', position: 'right', fontSize: 10, fill: '#ef4444' }} />
                <Bar dataKey="rate" radius={[4, 4, 0, 0]}>
                  <LabelList dataKey="rate" position="top" formatter={(v: number) => `${v}%`} style={{ fontSize: 11, fontWeight: 600, fill: '#374151' }} />
                  {raceData.map((e, i) => <Cell key={i} fill={e.rate >= 80 ? '#1a237e' : '#ef4444'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        {genderData.length > 0 && (
          <div className="card p-5">
            <h3 className="font-semibold text-gray-800 mb-1">Approval Rates by Gender</h3>
            <p className="text-xs text-gray-500 mb-4">Red bars are below the 80% fairness threshold</p>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={genderData} margin={{ top: 20, right: 10, left: 0, bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="group" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                <Tooltip formatter={(v: number) => [`${v}%`, 'Approval Rate']} />
                <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '80% threshold', position: 'right', fontSize: 10, fill: '#ef4444' }} />
                <Bar dataKey="rate" radius={[4, 4, 0, 0]}>
                  <LabelList dataKey="rate" position="top" formatter={(v: number) => `${v}%`} style={{ fontSize: 11, fontWeight: 600, fill: '#374151' }} />
                  {genderData.map((e, i) => <Cell key={i} fill={e.rate >= 80 ? '#3f51b5' : '#ef4444'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Bias indicators */}
      {(result.bias_indicators?.length ?? 0) > 0 && (
        <div className="card p-5 border-red-200 bg-red-50/30">
          <h3 className="font-semibold text-red-800 mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> Bias Indicators ({result.bias_indicators.length})
          </h3>
          <ul className="space-y-1.5">
            {result.bias_indicators.map((b, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-red-700">
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" /> {b.description}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Findings & Recommendations */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {(result.findings?.length ?? 0) > 0 && (
          <div className="card p-5">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-blue-600" /> Key Findings
            </h3>
            <ul className="space-y-2">
              {result.findings.map((f, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                  <span className="w-5 h-5 bg-blue-100 text-blue-700 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold">{i + 1}</span>
                  {f}
                </li>
              ))}
            </ul>
          </div>
        )}
        {(result.recommendations?.length ?? 0) > 0 && (
          <div className="card p-5">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-green-600" /> Recommendations
            </h3>
            <ul className="space-y-2">
              {result.recommendations.map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                  <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" /> {r}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* AI Explanation */}
      {result.ai_explanation && (
        <div className="card p-5">
          <button onClick={() => setShowExplain(!showExplain)} className="w-full flex items-center justify-between font-semibold text-gray-800">
            <span className="flex items-center gap-2"><Brain className="w-4 h-4 text-purple-600" /> AI Explanation</span>
            {showExplain ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          {showExplain && (
            <div className="mt-4 text-sm text-gray-700 leading-relaxed whitespace-pre-line bg-purple-50 rounded-lg p-4">
              {result.ai_explanation}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function FairnessPage() {
  const { selectedId, getSelected, fairnessHistory, addFairnessResult, clearFairnessHistory } = useDatasetStore()
  const selected = getSelected()
  // Show only the LATEST result for the selected dataset
  const latestResult = selectedId ? (fairnessHistory[selectedId] ?? [])[0] ?? null : null

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
      // Replace previous result — only keep latest per dataset
      addFairnessResult({
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
      })
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
      addFairnessResult({
        id: `${selectedId}-${Date.now()}`,
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
      })
      toast.success('AI explanation added')
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Explanation failed'),
  })

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Fairness Dashboard</h1>
          <p className="text-gray-500 mt-1">4/5ths disparate impact analysis · ECOA & FHA compliance</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {latestResult && (
            <>
              <button onClick={() => explainMutation.mutate()} disabled={explainMutation.isPending || !selectedId}
                className="btn-secondary flex items-center gap-2 text-sm">
                {explainMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
                AI Explain
              </button>
              <button onClick={() => { if (confirm('Clear audit result for this dataset?')) clearFairnessHistory(selectedId!) }}
                className="flex items-center gap-1.5 text-xs text-red-600 border border-red-200 hover:bg-red-50 px-3 py-1.5 rounded-lg transition-colors">
                <Trash2 className="w-3.5 h-3.5" /> Clear
              </button>
            </>
          )}
          <button onClick={() => auditMutation.mutate()} disabled={auditMutation.isPending || !selectedId}
            className="btn-primary flex items-center gap-2">
            {auditMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <BarChart3 className="w-4 h-4" />}
            {auditMutation.isPending ? 'Running Audit…' : latestResult ? 'Re-run Audit' : 'Run Fairness Audit'}
          </button>
        </div>
      </div>

      {!selectedId && (
        <div className="card p-8 text-center">
          <Info className="w-10 h-10 text-blue-400 mx-auto mb-3" />
          <p className="text-gray-600 font-medium">Select a dataset from the top bar to run a fairness audit.</p>
        </div>
      )}

      {selectedId && !latestResult && !auditMutation.isPending && (
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

      {auditMutation.isPending && (
        <div className="card p-8 text-center">
          <Loader2 className="w-10 h-10 animate-spin text-navy-900 mx-auto mb-3" />
          <p className="text-gray-600 font-medium">Running fairness analysis on {selected?.filename}…</p>
          <p className="text-gray-400 text-sm mt-1">Calculating disparate impact ratios across all protected classes</p>
        </div>
      )}

      {latestResult && !auditMutation.isPending && <AuditResult result={latestResult} />}
    </div>
  )
}
