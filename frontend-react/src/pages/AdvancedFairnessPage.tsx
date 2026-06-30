import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  ShieldCheck, Scale, GitBranch, FileText, Play, AlertTriangle,
  CheckCircle, XCircle, ChevronDown, ChevronUp, Download, Info,
  TrendingDown, TrendingUp, Users, BarChart2, Zap
} from 'lucide-react'
import { advancedFairnessApi } from '../lib/api'
import { useDataset } from '../hooks/useDataset'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, ReferenceLine, RadarChart, Radar, PolarGrid,
  PolarAngleAxis, PolarRadiusAxis, Legend
} from 'recharts'
import clsx from 'clsx'
import toast from 'react-hot-toast'

type AdvTab = 'full' | 'equalized' | 'intersectional' | 'ecoa'

const TABS = [
  { id: 'full' as AdvTab,          label: 'Full Analysis',     icon: ShieldCheck, color: 'blue' },
  { id: 'equalized' as AdvTab,     label: 'Equalized Odds',    icon: Scale,       color: 'purple' },
  { id: 'intersectional' as AdvTab,label: 'Intersectional',    icon: GitBranch,   color: 'amber' },
  { id: 'ecoa' as AdvTab,          label: 'ECOA Letter',       icon: FileText,    color: 'green' },
]

// ── Helper Components ─────────────────────────────────────────────────────────

function ScoreBadge({ score, label }: { score: number; label?: string }) {
  const color = score >= 80 ? 'text-green-600 bg-green-50 border-green-200'
    : score >= 60 ? 'text-amber-600 bg-amber-50 border-amber-200'
    : 'text-red-600 bg-red-50 border-red-200'
  return (
    <div className={`inline-flex flex-col items-center px-4 py-2 rounded-xl border ${color}`}>
      <span className="text-2xl font-bold">{score.toFixed(0)}</span>
      {label && <span className="text-xs font-medium">{label}</span>}
    </div>
  )
}

function ViolationBadge({ count }: { count: number }) {
  if (count === 0) return (
    <span className="flex items-center gap-1 text-green-600 text-sm font-medium">
      <CheckCircle className="w-4 h-4" /> No violations
    </span>
  )
  return (
    <span className="flex items-center gap-1 text-red-600 text-sm font-medium">
      <XCircle className="w-4 h-4" /> {count} violation{count > 1 ? 's' : ''}
    </span>
  )
}

function ViolationList({ violations }: { violations: string[] }) {
  if (!violations?.length) return (
    <div className="flex items-center gap-2 text-green-600 bg-green-50 rounded-lg px-4 py-3">
      <CheckCircle className="w-4 h-4 flex-shrink-0" />
      <span className="text-sm font-medium">No violations detected — this group meets the fairness threshold</span>
    </div>
  )
  return (
    <div className="space-y-2">
      {violations.map((v, i) => (
        <div key={i} className="flex items-start gap-2 bg-red-50 border border-red-100 rounded-lg px-3 py-2.5">
          <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
          <span className="text-sm text-red-700">{v}</span>
        </div>
      ))}
    </div>
  )
}

function StatCard({ label, value, sub, color = 'blue' }: {
  label: string; value: string | number; sub?: string; color?: string
}) {
  const colors: Record<string, string> = {
    blue: 'bg-blue-50 border-blue-100 text-blue-700',
    red: 'bg-red-50 border-red-100 text-red-700',
    green: 'bg-green-50 border-green-100 text-green-700',
    amber: 'bg-amber-50 border-amber-100 text-amber-700',
    purple: 'bg-purple-50 border-purple-100 text-purple-700',
  }
  return (
    <div className={`rounded-xl border p-4 ${colors[color] || colors.blue}`}>
      <div className="text-xs font-semibold uppercase tracking-wide opacity-70 mb-1">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
      {sub && <div className="text-xs opacity-60 mt-0.5">{sub}</div>}
    </div>
  )
}

// ── Full Analysis Result ──────────────────────────────────────────────────────

function FullAnalysisResult({ result }: { result: Record<string, unknown> }) {
  const methods = (result.methods_run as string[]) ?? []
  const attrs = (result.protected_attributes as string[]) ?? []
  const total = result.total_records as number ?? 0
  const perAttr = result.per_attribute as Record<string, Record<string, unknown>> ?? {}
  const intersectional = result.intersectional as Record<string, unknown> ?? {}
  const violations = (intersectional.violations as string[]) ?? []

  // Build radar data from per-attribute fairness scores
  const radarData = Object.entries(perAttr).map(([attr, data]) => {
    const eq = data.equalized_odds as Record<string, unknown> ?? {}
    const score = eq.fairness_score as number ?? 85
    return { attr: attr.replace(/_/g, ' ').slice(0, 16), score: Math.round(score) }
  })

  // Build bar data for DI ratios
  const diData: { name: string; di: number; violation: boolean }[] = []
  Object.entries(perAttr).forEach(([attr, data]) => {
    const eq = data.equalized_odds as Record<string, unknown> ?? {}
    const groups = eq.groups as Record<string, { tpr: number; count: number }> ?? {}
    Object.entries(groups).slice(0, 4).forEach(([grp, v]) => {
      diData.push({ name: `${attr.slice(0,8)}·${String(grp).slice(0,8)}`, di: v.tpr ?? 0.5, violation: (v.tpr ?? 1) < 0.8 })
    })
  })

  return (
    <div className="space-y-5">
      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Methods Run" value={methods.length} color="blue" />
        <StatCard label="Protected Attrs" value={attrs.length} color="purple" />
        <StatCard label="Total Records" value={total.toLocaleString()} color="green" />
        <StatCard label="Violations" value={violations.length} color={violations.length > 0 ? 'red' : 'green'} />
      </div>

      {/* Methods pills */}
      <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Methods Executed</p>
        <div className="flex flex-wrap gap-2">
          {methods.map(m => (
            <span key={m} className="flex items-center gap-1 bg-blue-100 text-blue-700 text-xs px-3 py-1 rounded-full font-medium">
              <Zap className="w-3 h-3" /> {m}
            </span>
          ))}
        </div>
      </div>

      {/* Radar chart */}
      {radarData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <p className="font-semibold text-gray-800 mb-4">Fairness Score by Protected Attribute</p>
          <ResponsiveContainer width="100%" height={240}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="#e5e7eb" />
              <PolarAngleAxis dataKey="attr" tick={{ fontSize: 11, fill: '#6b7280' }} />
              <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#9ca3af' }} />
              <Radar name="Score" dataKey="score" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.2} />
              <Tooltip formatter={(v: number) => [`${v}/100`, 'Fairness Score']} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Intersectional violations */}
      <div className="bg-white rounded-xl border border-gray-100 p-5">
        <div className="flex items-center justify-between mb-3">
          <p className="font-semibold text-gray-800">Intersectional Violations</p>
          <ViolationBadge count={violations.length} />
        </div>
        <ViolationList violations={violations} />
      </div>

      {/* Per-attribute breakdown */}
      {Object.entries(perAttr).map(([attr, data]) => {
        const eq = data.equalized_odds as Record<string, unknown> ?? {}
        const eqViolations = (eq.violations as string[]) ?? []
        const groups = eq.groups as Record<string, { tpr: number; fpr: number; count: number }> ?? {}
        const groupData = Object.entries(groups).map(([g, v]) => ({
          name: String(g).slice(0, 20), tpr: Math.round((v.tpr ?? 0) * 100), fpr: Math.round((v.fpr ?? 0) * 100), count: v.count
        }))
        return (
          <div key={attr} className="bg-white rounded-xl border border-gray-100 p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="font-semibold text-gray-800 uppercase tracking-wide text-sm">{attr.replace(/_/g, ' ')}</p>
                <p className="text-xs text-gray-400 mt-0.5">Protected attribute analysis</p>
              </div>
              <ViolationBadge count={eqViolations.length} />
            </div>
            {groupData.length > 0 && (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={groupData} margin={{ left: 0, right: 8 }}>
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={false} tickLine={false} unit="%" />
                  <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '80% threshold', fontSize: 9, fill: '#ef4444' }} />
                  <Tooltip formatter={(v: number, n: string) => [`${v}%`, n === 'tpr' ? 'True Positive Rate' : 'False Positive Rate']} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="tpr" name="TPR" fill="#3b82f6" radius={[4,4,0,0]}>
                    {groupData.map((g, i) => <Cell key={i} fill={g.tpr < 80 ? '#ef4444' : '#3b82f6'} />)}
                  </Bar>
                  <Bar dataKey="fpr" name="FPR" fill="#8b5cf6" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
            {eqViolations.length > 0 && <div className="mt-3"><ViolationList violations={eqViolations} /></div>}
          </div>
        )
      })}
    </div>
  )
}

// ── Intersectional Result ─────────────────────────────────────────────────────

function IntersectionalResult({ result }: { result: Record<string, unknown> }) {
  const violations = (result.violations as string[]) ?? []
  const groups = result.groups as Record<string, { approval_rate: number; disparate_impact: number; status: string; count: number }> ?? {}
  const overallRate = result.overall_approval_rate as number ?? 0

  const chartData = Object.entries(groups)
    .sort((a, b) => b[1].disparate_impact - a[1].disparate_impact)
    .slice(0, 15)
    .map(([name, v]) => ({
      name: name.slice(0, 22),
      di: parseFloat(v.disparate_impact.toFixed(3)),
      rate: parseFloat((v.approval_rate * 100).toFixed(1)),
      status: v.status,
      count: v.count,
    }))

  const violationCount = Object.values(groups).filter(g => g.status === 'violation').length
  const passCount = Object.values(groups).filter(g => g.status === 'pass').length

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Groups Analyzed" value={Object.keys(groups).length} color="blue" />
        <StatCard label="Violations" value={violationCount} color={violationCount > 0 ? 'red' : 'green'} />
        <StatCard label="Passing" value={passCount} color="green" />
        <StatCard label="Overall Approval" value={`${(overallRate * 100).toFixed(1)}%`} color="purple" />
      </div>

      {chartData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-4">
            <p className="font-semibold text-gray-800">Disparate Impact by Intersectional Group</p>
            <div className="flex items-center gap-3 text-xs text-gray-500">
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-red-400 inline-block" /> Violation</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-green-400 inline-block" /> Pass</span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={Math.max(220, chartData.length * 26)}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 4, right: 40 }}>
              <XAxis type="number" domain={[0, 1.4]} tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 10, fill: '#6b7280' }} axisLine={false} tickLine={false} width={140} />
              <ReferenceLine x={0.8} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '0.80', fontSize: 9, fill: '#ef4444', position: 'top' }} />
              <Tooltip formatter={(v: number, n: string) => [n === 'di' ? v.toFixed(3) : `${v}%`, n === 'di' ? 'DI Ratio' : 'Approval Rate']}
                contentStyle={{ fontSize: 11, borderRadius: 8 }} />
              <Bar dataKey="di" name="DI Ratio" radius={[0, 4, 4, 0]}>
                {chartData.map((g, i) => <Cell key={i} fill={g.status === 'violation' ? '#f87171' : '#4ade80'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="text-xs text-gray-400 mt-2">Red dashed line = 0.80 four-fifths rule threshold. Values below indicate potential discrimination.</p>
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-100 p-5">
        <p className="font-semibold text-gray-800 mb-3">Violations ({violations.length})</p>
        <ViolationList violations={violations} />
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AdvancedFairnessPage() {
  const { activeDataset } = useDataset()
  const [tab, setTab] = useState<AdvTab>('full')
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [letter, setLetter] = useState('')

  const [eqForm, setEqForm] = useState({ outcome_col: '', pred_col: '', protected_col: '', tolerance: '0.10' })
  const [intForm, setIntForm] = useState({ outcome_col: '', protected_cols: '' })
  const [ecoaForm, setEcoaForm] = useState({
    institution_name: 'Fair Lending Institution',
    loan_type: 'mortgage',
    featuresJson: '{"debt_to_income_ratio": 0.52, "credit_score": 580, "income": 42000}',
    shapJson: '{"debt_to_income_ratio": 0.35, "credit_score": -0.25, "income": -0.15}',
  })

  const onErr = (e: unknown) => {
    const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Analysis failed'
    toast.error(msg)
  }

  const fullMutation = useMutation({
    mutationFn: () => advancedFairnessApi.fullAnalysis({ dataset_id: activeDataset!.file_id }),
    onSuccess: d => { setResult(d); toast.success('Full analysis complete') },
    onError: onErr,
  })

  const eqMutation = useMutation({
    mutationFn: () => advancedFairnessApi.equalizedOdds({
      dataset_id: activeDataset!.file_id, ...eqForm, tolerance: parseFloat(eqForm.tolerance)
    }),
    onSuccess: d => { setResult(d); toast.success('Equalized Odds analysis complete') },
    onError: onErr,
  })

  const intMutation = useMutation({
    mutationFn: () => advancedFairnessApi.intersectional({
      dataset_id: activeDataset!.file_id,
      outcome_col: intForm.outcome_col,
      protected_cols: intForm.protected_cols.split(',').map(s => s.trim()).filter(Boolean),
    }),
    onSuccess: d => { setResult(d); toast.success('Intersectional analysis complete') },
    onError: onErr,
  })

  const ecoaMutation = useMutation({
    mutationFn: () => {
      let features = {}, shap = {}
      try { features = JSON.parse(ecoaForm.featuresJson) } catch { toast.error('Invalid features JSON'); throw new Error('bad json') }
      try { shap = JSON.parse(ecoaForm.shapJson) } catch { toast.error('Invalid SHAP JSON'); throw new Error('bad json') }
      return advancedFairnessApi.denialLetter({ applicant_features: features, shap_values: shap,
        institution_name: ecoaForm.institution_name, loan_type: ecoaForm.loan_type })
    },
    onSuccess: d => { setLetter(d.letter); toast.success('Adverse action notice generated') },
    onError: onErr,
  })

  const isRunning = fullMutation.isPending || eqMutation.isPending || intMutation.isPending || ecoaMutation.isPending

  const switchTab = (t: AdvTab) => { setTab(t); setResult(null); setLetter('') }

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Advanced Fairness</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Enterprise-grade fairness analysis — Equalized Odds · Intersectional · ECOA compliance
        </p>
      </div>

      {!activeDataset && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
          <Info className="w-5 h-5 text-amber-500 flex-shrink-0" />
          <p className="text-sm text-amber-700">Select a dataset from the top bar to run advanced fairness analysis.</p>
        </div>
      )}

      {/* Tab bar */}
      <div className="flex gap-2 flex-wrap">
        {TABS.map(t => {
          const Icon = t.icon
          const active = tab === t.id
          return (
            <button key={t.id} onClick={() => switchTab(t.id)}
              className={clsx('flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all',
                active ? 'bg-navy-900 text-white shadow-sm' : 'bg-white border border-gray-200 text-gray-600 hover:border-gray-300 hover:bg-gray-50'
              )}>
              <Icon className="w-4 h-4" />{t.label}
            </button>
          )
        })}
      </div>

      {/* ── Full Analysis ── */}
      {tab === 'full' && (
        <div className="space-y-5">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="font-semibold text-gray-900 text-lg">Comprehensive Advanced Fairness Analysis</h2>
                <p className="text-sm text-gray-500 mt-1 max-w-xl">
                  Automatically detects protected attributes, runs Equalized Odds across all groups,
                  performs Intersectional analysis, and produces a full violation report — all in one click.
                </p>
              </div>
              <ShieldCheck className="w-8 h-8 text-blue-400 flex-shrink-0 ml-4" />
            </div>
            <div className="flex flex-wrap gap-2 mt-4 mb-5">
              {['Equalized Odds','Intersectional','TPR/FPR by Group','Violation Detection','Regulatory Mapping'].map(f => (
                <span key={f} className="text-xs bg-blue-50 text-blue-700 px-3 py-1 rounded-full border border-blue-100">{f}</span>
              ))}
            </div>
            <button onClick={() => fullMutation.mutate()} disabled={!activeDataset || isRunning}
              className="flex items-center gap-2 bg-navy-900 text-white px-5 py-2.5 rounded-xl font-medium text-sm hover:bg-navy-800 disabled:opacity-50 transition-colors">
              {isRunning ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Play className="w-4 h-4" />}
              Run Full Analysis
            </button>
          </div>
          {result && <FullAnalysisResult result={result} />}
        </div>
      )}

      {/* ── Equalized Odds ── */}
      {tab === 'equalized' && (
        <div className="space-y-5">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="font-semibold text-gray-900 text-lg">Equalized Odds Analysis</h2>
                <p className="text-sm text-gray-500 mt-1 max-w-xl">
                  Checks whether True Positive Rate (TPR) and False Positive Rate (FPR) are equal across
                  protected groups. Requires a predictions column from ML Engine.
                </p>
              </div>
              <Scale className="w-8 h-8 text-purple-400 flex-shrink-0 ml-4" />
            </div>
            <div className="grid sm:grid-cols-3 gap-3 mt-5">
              {[
                { label: 'Outcome Column', key: 'outcome_col', placeholder: 'e.g. action_taken' },
                { label: 'Prediction Column', key: 'pred_col', placeholder: 'e.g. predicted_outcome' },
                { label: 'Protected Column', key: 'protected_col', placeholder: 'e.g. applicant_race_1' },
              ].map(({ label, key, placeholder }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
                  <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                    value={eqForm[key as keyof typeof eqForm]}
                    onChange={e => setEqForm(p => ({ ...p, [key]: e.target.value }))}
                    placeholder={placeholder} />
                </div>
              ))}
            </div>
            <div className="mt-3 w-40">
              <label className="block text-xs font-medium text-gray-600 mb-1">Tolerance</label>
              <input type="number" step="0.01" min="0" max="0.5"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                value={eqForm.tolerance} onChange={e => setEqForm(p => ({ ...p, tolerance: e.target.value }))} />
            </div>
            <button onClick={() => eqMutation.mutate()} disabled={!activeDataset || !eqForm.outcome_col || !eqForm.pred_col || isRunning}
              className="mt-5 flex items-center gap-2 bg-navy-900 text-white px-5 py-2.5 rounded-xl font-medium text-sm hover:bg-navy-800 disabled:opacity-50 transition-colors">
              {isRunning ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Scale className="w-4 h-4" />}
              Analyze Equalized Odds
            </button>
          </div>
          {result && (
            <div className="space-y-4">
              <div className="bg-white rounded-xl border border-gray-100 p-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="font-semibold text-gray-800">Violations</p>
                  <ViolationBadge count={(result.violations as string[])?.length ?? 0} />
                </div>
                <ViolationList violations={(result.violations as string[]) ?? []} />
              </div>
              {result.groups && (
                <div className="bg-white rounded-xl border border-gray-100 p-5">
                  <p className="font-semibold text-gray-800 mb-4">TPR / FPR by Group</p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
                        <th className="text-left py-2 pr-4">Group</th>
                        <th className="text-right py-2 pr-4">True Positive Rate</th>
                        <th className="text-right py-2 pr-4">False Positive Rate</th>
                        <th className="text-right py-2">Count</th>
                      </tr></thead>
                      <tbody>{Object.entries(result.groups as Record<string, { tpr: number; fpr: number; count: number }>).map(([g, v]) => (
                        <tr key={g} className="border-b border-gray-50 hover:bg-gray-50">
                          <td className="py-2.5 pr-4 font-medium text-gray-700">{g}</td>
                          <td className={clsx('py-2.5 pr-4 text-right font-semibold', (v.tpr * 100) < 80 ? 'text-red-600' : 'text-green-600')}>
                            {(v.tpr * 100).toFixed(1)}%</td>
                          <td className="py-2.5 pr-4 text-right text-gray-600">{(v.fpr * 100).toFixed(1)}%</td>
                          <td className="py-2.5 text-right text-gray-400">{v.count}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Intersectional ── */}
      {tab === 'intersectional' && (
        <div className="space-y-5">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="font-semibold text-gray-900 text-lg">Intersectional Fairness Analysis</h2>
                <p className="text-sm text-gray-500 mt-1 max-w-xl">
                  Analyzes fairness at the intersection of multiple protected attributes (e.g., race + gender).
                  CFPB guidance recognizes that single-attribute analysis misses intersectional discrimination.
                </p>
              </div>
              <GitBranch className="w-8 h-8 text-amber-400 flex-shrink-0 ml-4" />
            </div>
            <div className="grid sm:grid-cols-2 gap-3 mt-5">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Outcome Column</label>
                <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                  value={intForm.outcome_col} onChange={e => setIntForm(p => ({ ...p, outcome_col: e.target.value }))}
                  placeholder="e.g. action_taken" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Protected Columns (comma-separated, min 2)</label>
                <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                  value={intForm.protected_cols} onChange={e => setIntForm(p => ({ ...p, protected_cols: e.target.value }))}
                  placeholder="e.g. race, gender" />
              </div>
            </div>
            <button onClick={() => intMutation.mutate()}
              disabled={!activeDataset || !intForm.outcome_col || intForm.protected_cols.split(',').filter(Boolean).length < 2 || isRunning}
              className="mt-5 flex items-center gap-2 bg-navy-900 text-white px-5 py-2.5 rounded-xl font-medium text-sm hover:bg-navy-800 disabled:opacity-50 transition-colors">
              {isRunning ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <GitBranch className="w-4 h-4" />}
              Run Intersectional Analysis
            </button>
          </div>
          {result && <IntersectionalResult result={result} />}
        </div>
      )}

      {/* ── ECOA Denial Letter ── */}
      {tab === 'ecoa' && (
        <div className="space-y-5">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="font-semibold text-gray-900 text-lg">ECOA Adverse Action Notice Generator</h2>
                <p className="text-sm text-gray-500 mt-1 max-w-xl">
                  Generates a regulatory-compliant adverse action notice per ECOA 12 C.F.R. § 1002.9.
                  Uses SHAP values to identify and map top denial reasons to approved regulatory language.
                </p>
                <div className="flex gap-2 mt-3">
                  {['ECOA Compliant','CFPB Ready','SHAP-driven','Regulatory Language'].map(b => (
                    <span key={b} className="text-xs bg-green-50 text-green-700 px-2.5 py-1 rounded-full border border-green-100">{b}</span>
                  ))}
                </div>
              </div>
              <FileText className="w-8 h-8 text-green-400 flex-shrink-0 ml-4" />
            </div>
            <div className="grid sm:grid-cols-2 gap-4 mt-5">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Institution Name</label>
                <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                  value={ecoaForm.institution_name} onChange={e => setEcoaForm(p => ({ ...p, institution_name: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Loan Type</label>
                <select className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                  value={ecoaForm.loan_type} onChange={e => setEcoaForm(p => ({ ...p, loan_type: e.target.value }))}>
                  <option value="mortgage">Mortgage</option>
                  <option value="auto">Auto Loan</option>
                  <option value="personal">Personal Loan</option>
                  <option value="business">Business Loan</option>
                  <option value="heloc">HELOC</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Applicant Features (JSON)</label>
                <textarea rows={5} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-navy-900 resize-none"
                  value={ecoaForm.featuresJson} onChange={e => setEcoaForm(p => ({ ...p, featuresJson: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  SHAP Values (JSON) <span className="text-gray-400">— negative values = denial reasons</span>
                </label>
                <textarea rows={5} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-navy-900 resize-none"
                  value={ecoaForm.shapJson} onChange={e => setEcoaForm(p => ({ ...p, shapJson: e.target.value }))} />
              </div>
            </div>
            <button onClick={() => ecoaMutation.mutate()} disabled={isRunning}
              className="mt-5 flex items-center gap-2 bg-navy-900 text-white px-5 py-2.5 rounded-xl font-medium text-sm hover:bg-navy-800 disabled:opacity-50 transition-colors">
              {isRunning ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <FileText className="w-4 h-4" />}
              Generate Adverse Action Notice
            </button>
          </div>

          {letter && (
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="font-semibold text-gray-900">Generated Adverse Action Notice</p>
                  <p className="text-xs text-gray-400 mt-0.5">ECOA 12 C.F.R. § 1002.9 compliant</p>
                </div>
                <button onClick={() => {
                  const b = new Blob([letter], { type: 'text/plain' })
                  const u = URL.createObjectURL(b)
                  const a = document.createElement('a')
                  a.href = u; a.download = 'adverse_action_notice.txt'; a.click()
                  URL.revokeObjectURL(u)
                }} className="flex items-center gap-2 border border-gray-200 text-gray-600 hover:bg-gray-50 px-3 py-1.5 rounded-lg text-sm transition-colors">
                  <Download className="w-4 h-4" /> Download
                </button>
              </div>
              <pre className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap bg-gray-50 border border-gray-100 p-5 rounded-xl overflow-auto max-h-[500px] font-mono">
                {letter}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
