import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useDatasetStore } from '../store/datasetStore'
import api from '../lib/api'
import toast from 'react-hot-toast'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine
} from 'recharts'
import {
  BarChart3, AlertTriangle, CheckCircle, Shield, Brain, Loader2,
  ChevronDown, ChevronUp, Info
} from 'lucide-react'

interface FairnessResult {
  score: number
  disparate_impact_ratios: Record<string, number>
  approval_rates_by_group: Record<string, Record<string, number>>
  bias_indicators: Array<{field: string; group: string; value: number; severity: string; description: string}>
  findings: string[]
  recommendations: string[]
  ai_explanation?: string
  outcome_column?: string
  protected_columns?: Record<string, string>
}

function ScoreCard({ label, value, subtitle, color }: { label: string; value: string | number; subtitle?: string; color: string }) {
  return (
    <div className="card p-4">
      <div className={`text-3xl font-bold ${color} mb-1`}>{value}</div>
      <div className="text-sm font-semibold text-gray-700">{label}</div>
      {subtitle && <div className="text-xs text-gray-400 mt-0.5">{subtitle}</div>}
    </div>
  )
}

export default function FairnessPage() {
  const { selectedId, getSelected } = useDatasetStore()
  const selected = getSelected()
  const [result, setResult] = useState<FairnessResult | null>(null)
  const [showExplain, setShowExplain] = useState(false)

  // (no auto-load query — /fairness/latest endpoint does not exist)

  const auditMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) throw new Error('No dataset selected')
      const res = await api.post('/fairness/audit', { dataset_id: selectedId })
      return res.data
    },
    onSuccess: (data) => {
      setResult(data)
      toast.success(`Fairness audit complete — score: ${data.score?.toFixed(1)}`)
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
      // Response: {report: {...}, ai_explanation: string, provider, model}
      const report = data.report || {}
      setResult(prev => prev
        ? { ...prev, ...report, ai_explanation: data.ai_explanation }
        : { ...report, ai_explanation: data.ai_explanation }
      )
      setShowExplain(true)
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Explanation failed'),
  })

  // Build chart data from approval rates
  const raceChartData = result?.approval_rates_by_group?.race
    ? Object.entries(result.approval_rates_by_group.race).map(([group, rate]) => ({
        group: group.replace('race_', '').replace(/_/g, ' '),
        rate: Math.round((rate as number) * 100),
      }))
    : []

  const genderChartData = result?.approval_rates_by_group?.gender
    ? Object.entries(result.approval_rates_by_group.gender).map(([group, rate]) => ({
        group: group.replace('gender_', '').replace(/_/g, ' '),
        rate: Math.round((rate as number) * 100),
      }))
    : []

  const score = result?.score ?? 0
  const scoreColor = score >= 80 ? 'text-green-600' : score >= 60 ? 'text-amber-600' : 'text-red-600'

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Fairness Dashboard</h1>
          <p className="text-gray-500 mt-1">4/5ths disparate impact analysis · ECOA & FHA compliance</p>
        </div>
        <div className="flex gap-3">
          {result && (
            <button
              onClick={() => explainMutation.mutate()}
              disabled={explainMutation.isPending}
              className="btn-secondary flex items-center gap-2"
            >
              {explainMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
              AI Explain
            </button>
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

      {!selectedId && (
        <div className="card p-8 text-center">
          <Info className="w-10 h-10 text-blue-400 mx-auto mb-3" />
          <p className="text-gray-600 font-medium">Select a dataset from the top bar to run a fairness audit.</p>
        </div>
      )}

      {selectedId && !result && !auditMutation.isPending && (
        <div className="card p-8 text-center">
          <Shield className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 mb-4">No fairness audit has been run for <strong>{selected?.filename}</strong> yet.</p>
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

      {result && (
        <>
          {/* Score cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <ScoreCard
              label="Overall Fairness Score"
              value={score.toFixed(1)}
              subtitle="Higher is better (0–100)"
              color={scoreColor}
            />
            <ScoreCard
              label="Race DI Ratio"
              value={result.disparate_impact_ratios?.race != null
                ? result.disparate_impact_ratios.race.toFixed(3)
                : '—'}
              subtitle="≥0.8 passes 4/5ths rule"
              color={result.disparate_impact_ratios?.race >= 0.8 ? 'text-green-600' : 'text-red-600'}
            />
            <ScoreCard
              label="Gender DI Ratio"
              value={result.disparate_impact_ratios?.gender != null
                ? result.disparate_impact_ratios.gender.toFixed(3)
                : '—'}
              subtitle="≥0.8 passes 4/5ths rule"
              color={result.disparate_impact_ratios?.gender >= 0.8 ? 'text-green-600' : 'text-red-600'}
            />
            <ScoreCard
              label="Bias Indicators"
              value={result.bias_indicators?.length ?? 0}
              subtitle="Flagged concerns"
              color={result.bias_indicators?.length === 0 ? 'text-green-600' : 'text-red-600'}
            />
          </div>

          {/* DI ratio table */}
          {Object.keys(result.disparate_impact_ratios || {}).length > 0 && (
            <div className="card p-5">
              <h3 className="font-semibold text-gray-800 mb-4">Disparate Impact Ratios by Protected Class</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {Object.entries(result.disparate_impact_ratios).map(([key, ratio]) => (
                  <div key={key} className={`p-3 rounded-lg border ${(ratio as number) >= 0.8 ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                    <div className={`text-2xl font-bold ${(ratio as number) >= 0.8 ? 'text-green-700' : 'text-red-700'}`}>
                      {(ratio as number).toFixed(3)}
                    </div>
                    <div className="text-xs font-medium text-gray-600 capitalize mt-0.5">{key}</div>
                    <div className={`text-xs mt-1 ${(ratio as number) >= 0.8 ? 'text-green-600' : 'text-red-600'}`}>
                      {(ratio as number) >= 0.8 ? '✓ Passes 4/5ths' : '✗ Below threshold'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {raceChartData.length > 0 && (
              <div className="card p-5">
                <h3 className="font-semibold text-gray-800 mb-4">Approval Rates by Race</h3>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={raceChartData} margin={{ top: 5, right: 10, left: 0, bottom: 40 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="group" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                    <Tooltip formatter={(v: number) => [`${v}%`, 'Approval Rate']} />
                    <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '4/5ths', position: 'right', fontSize: 10 }} />
                    <Bar dataKey="rate" fill="#1a237e" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            {genderChartData.length > 0 && (
              <div className="card p-5">
                <h3 className="font-semibold text-gray-800 mb-4">Approval Rates by Gender</h3>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={genderChartData} margin={{ top: 5, right: 10, left: 0, bottom: 40 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="group" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                    <Tooltip formatter={(v: number) => [`${v}%`, 'Approval Rate']} />
                    <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '4/5ths', position: 'right', fontSize: 10 }} />
                    <Bar dataKey="rate" fill="#3f51b5" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Bias indicators */}
          {result.bias_indicators && result.bias_indicators.length > 0 && (
            <div className="card p-5 border-red-200 bg-red-50/30">
              <h3 className="font-semibold text-red-800 mb-3 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" /> Bias Indicators ({result.bias_indicators.length})
              </h3>
              <ul className="space-y-1.5">
                {result.bias_indicators.map((b: any, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-red-700">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" /> {b.description || b}
                    {typeof b === 'string' ? b : b.description || `${b.field} — ${b.group}: ${b.value}`}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Findings & recommendations */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {result.findings && result.findings.length > 0 && (
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
            {result.recommendations && result.recommendations.length > 0 && (
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
              <button
                onClick={() => setShowExplain(!showExplain)}
                className="w-full flex items-center justify-between font-semibold text-gray-800"
              >
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
        </>
      )}
    </div>
  )
}
