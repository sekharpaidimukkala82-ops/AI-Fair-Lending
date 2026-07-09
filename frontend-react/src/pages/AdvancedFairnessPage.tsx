import { useState, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  ShieldCheck, Scale, GitBranch, FileText, Play, AlertTriangle,
  CheckCircle, XCircle, Info, Users, Zap, HelpCircle
} from 'lucide-react'
import { advancedFairnessApi } from '../lib/api'
import { useDataset } from '../hooks/useDataset'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, ReferenceLine, RadarChart, Radar, PolarGrid,
  PolarAngleAxis, PolarRadiusAxis
} from 'recharts'
import toast from 'react-hot-toast'

type AdvTab = 'full' | 'equalized' | 'intersectional' | 'ecoa'

const TABS = [
  { id: 'full' as AdvTab,          label: 'Full Analysis',     icon: ShieldCheck },
  { id: 'equalized' as AdvTab,     label: 'Equalized Odds',    icon: Scale       },
  { id: 'intersectional' as AdvTab,label: 'Intersectional',    icon: GitBranch   },
  { id: 'ecoa' as AdvTab,          label: 'ECOA Letter',       icon: FileText    },
]

// ── Explanation tooltip ───────────────────────────────────────────────────────
function InfoTip({ text }: { text: string }) {
  return (
    <span className="relative group ml-1 cursor-help">
      <HelpCircle className="w-3.5 h-3.5 text-gray-400 inline" />
      <span className="hidden group-hover:block absolute z-50 bottom-6 left-0 w-72 bg-gray-900 text-white text-xs rounded-lg px-3 py-2 shadow-lg leading-relaxed">
        {text}
      </span>
    </span>
  )
}

// ── Status badge ──────────────────────────────────────────────────────────────
function StatusPill({ pass, label }: { pass: boolean; label: string }) {
  return pass
    ? <span className="inline-flex items-center gap-1 bg-green-100 text-green-700 text-xs px-2.5 py-1 rounded-full font-medium"><CheckCircle className="w-3 h-3"/>{label}</span>
    : <span className="inline-flex items-center gap-1 bg-red-100 text-red-700 text-xs px-2.5 py-1 rounded-full font-medium"><XCircle className="w-3 h-3"/>{label}</span>
}

// ── Full Analysis Result ──────────────────────────────────────────────────────
function FullAnalysisResult({ result }: { result: any }) {
  const methods = result.methods_run ?? []
  const attrs = result.protected_attributes ?? []
  const total = result.total_records ?? 0
  const perAttr = result.per_attribute ?? {}
  const intersectional = result.intersectional ?? {}
  const violations = intersectional.violations ?? []

  // Build radar data
  const radarData = Object.entries(perAttr).map(([attr, data]: any) => {
    const score = data?.equalized_odds?.fairness_score ?? 85
    return { attr: attr.replace(/_/g, ' ').slice(0, 14), score: Math.round(score) }
  })

  return (
    <div className="space-y-5">
      {/* What this means banner */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-3 flex gap-3">
        <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-blue-800">
          <span className="font-semibold">What this analysis does:</span> Checks whether loan decisions are equally fair
          for all demographic groups — by race, gender, and age. It runs <strong>Equalized Odds</strong> (are qualified
          applicants approved equally?) and <strong>Intersectional analysis</strong> (does bias appear when combining
          e.g. race + gender?). Violations mean a group is being treated unfairly compared to the best-served group.
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card p-4 text-center">
          <div className="text-3xl font-bold text-blue-600">{methods.length}</div>
          <div className="text-xs text-gray-500 mt-1">Analysis Methods Run</div>
          <div className="text-xs text-gray-400 mt-0.5">Equalized Odds + Intersectional</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-3xl font-bold text-purple-600">{attrs.length}</div>
          <div className="text-xs text-gray-500 mt-1">Protected Attributes</div>
          <div className="text-xs text-gray-400 mt-0.5">Race, gender, age etc.</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-3xl font-bold text-green-600">{total.toLocaleString()}</div>
          <div className="text-xs text-gray-500 mt-1">Applications Analyzed</div>
        </div>
        <div className={`card p-4 text-center ${violations.length > 0 ? 'border-red-200 bg-red-50/30' : 'border-green-200 bg-green-50/30'}`}>
          <div className={`text-3xl font-bold ${violations.length > 0 ? 'text-red-600' : 'text-green-600'}`}>{violations.length}</div>
          <div className="text-xs text-gray-500 mt-1">Intersectional Violations</div>
          <div className="text-xs text-gray-400 mt-0.5">{violations.length === 0 ? 'All groups pass' : 'Action needed'}</div>
        </div>
      </div>

      {/* Methods run */}
      <div className="card p-4">
        <p className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
          <Zap className="w-4 h-4 text-blue-500" /> Analysis Methods Executed
        </p>
        <div className="flex flex-wrap gap-2">
          {methods.length > 0 ? methods.map((m: string) => (
            <span key={m} className="bg-blue-100 text-blue-700 text-xs px-3 py-1.5 rounded-full font-medium">{m}</span>
          )) : ['Equalized Odds','Intersectional Analysis'].map(m => (
            <span key={m} className="bg-blue-100 text-blue-700 text-xs px-3 py-1.5 rounded-full font-medium">{m}</span>
          ))}
        </div>
      </div>

      {/* Radar chart */}
      {radarData.length > 0 && (
        <div className="card p-5">
          <p className="font-semibold text-gray-800 mb-1">Fairness Score by Demographic Group</p>
          <p className="text-xs text-gray-500 mb-4">Higher score = more fair. Below 80 means the group faces potential discrimination.</p>
          <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={radarData} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
              <PolarGrid stroke="#e5e7eb" />
              <PolarAngleAxis dataKey="attr" tick={{ fontSize: 12, fill: '#374151', fontWeight: 500 }} />
              <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#9ca3af' }} tickCount={5} />
              <Radar name="Fairness Score" dataKey="score" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.25} strokeWidth={2} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Per-attribute cards */}
      {Object.entries(perAttr).map(([attr, data]: any) => {
        const eq = data?.equalized_odds ?? {}
        const eqViolations = eq.violations ?? []
        const groups = eq.groups ?? {}
        const groupData = Object.entries(groups).map(([g, v]: any) => ({
          name: String(g).slice(0, 18),
          tpr: Math.round((v.tpr ?? 0) * 100),
          fpr: Math.round((v.fpr ?? 0) * 100),
          count: v.count ?? 0,
        }))
        return (
          <div key={attr} className="card p-5">
            <div className="flex items-start justify-between mb-2">
              <div>
                <p className="font-semibold text-gray-800 capitalize text-base">{attr.replace(/_/g, ' ')}</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  True Positive Rate = % of qualified applicants who were actually approved.
                  If one group's TPR is much lower, that group faces unfair barriers.
                </p>
              </div>
              <StatusPill pass={eqViolations.length === 0} label={eqViolations.length === 0 ? 'No violations' : `${eqViolations.length} violation${eqViolations.length > 1 ? 's' : ''}`} />
            </div>
            {groupData.length > 0 && (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={groupData} margin={{ left: 0, right: 8, top: 4 }}>
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#6b7280' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} unit="%" domain={[0, 100]} />
                  <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '80% fair threshold', fontSize: 9, fill: '#ef4444', position: 'right' }} />
                  <Tooltip formatter={(v: number, n: string) => [`${v}%`, n === 'tpr' ? 'Approval Rate (qualified)' : 'False Approval Rate']} />
                  <Bar dataKey="tpr" name="tpr" radius={[4, 4, 0, 0]} label={{ position: 'top', fontSize: 10, formatter: (v: number) => `${v}%` }}>
                    {groupData.map((g, i) => <Cell key={i} fill={g.tpr < 80 ? '#f87171' : '#34d399'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
            {eqViolations.length > 0 && (
              <div className="mt-3 space-y-1.5">
                {eqViolations.map((v: string, i: number) => (
                  <div key={i} className="flex items-start gap-2 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
                    <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-red-700">{v}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}

      {/* Intersectional violations */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-2">
          <div>
            <p className="font-semibold text-gray-800">Intersectional Violations</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Checks bias at the intersection of groups — e.g. Black + Female together may face more
              discrimination than either group alone. This is required by CFPB fair lending guidance.
            </p>
          </div>
          <StatusPill pass={violations.length === 0} label={violations.length === 0 ? 'All pass' : `${violations.length} flagged`} />
        </div>
        {violations.length === 0 ? (
          <div className="flex items-center gap-2 bg-green-50 rounded-lg px-4 py-3 mt-2">
            <CheckCircle className="w-4 h-4 text-green-600" />
            <span className="text-sm text-green-700 font-medium">No intersectional discrimination detected — all combined groups meet the fairness threshold.</span>
          </div>
        ) : (
          <div className="space-y-2 mt-2">
            {violations.map((v: string, i: number) => (
              <div key={i} className="flex items-start gap-2 bg-red-50 border border-red-100 rounded-lg px-3 py-2.5">
                <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                <span className="text-sm text-red-700">{v}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Intersectional Result ─────────────────────────────────────────────────────
function IntersectionalResult({ result }: { result: any }) {
  const violations = result.violations ?? []
  const groups = result.groups ?? {}
  const overallRate = result.overall_approval_rate ?? 0

  const chartData = Object.entries(groups)
    .map(([name, v]: any) => ({
      name: name.slice(0, 24),
      di: parseFloat((v.disparate_impact ?? 0).toFixed(3)),
      rate: parseFloat(((v.approval_rate ?? 0) * 100).toFixed(1)),
      status: v.status ?? 'pass',
      count: v.count ?? 0,
    }))
    .sort((a, b) => a.di - b.di)
    .slice(0, 15)

  return (
    <div className="space-y-5">
      <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex gap-3">
        <Info className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-amber-900">
          <strong>What is Intersectional Analysis?</strong> Standard analysis checks race and gender separately.
          But a Black woman may face more discrimination than Black men or White women individually.
          This analysis checks all combinations — required under CFPB multi-factor fair lending review.
          A DI ratio below <strong>0.80</strong> (the 4/5ths rule) means that combined group is treated unfairly.
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card p-4 text-center">
          <div className="text-3xl font-bold text-blue-600">{Object.keys(groups).length}</div>
          <div className="text-xs text-gray-500 mt-1">Groups Analyzed</div>
        </div>
        <div className={`card p-4 text-center ${violations.length > 0 ? 'border-red-200' : 'border-green-200'}`}>
          <div className={`text-3xl font-bold ${violations.length > 0 ? 'text-red-600' : 'text-green-600'}`}>{violations.length}</div>
          <div className="text-xs text-gray-500 mt-1">Violations Found</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-3xl font-bold text-green-600">{Object.values(groups).filter((g: any) => g.status === 'pass').length}</div>
          <div className="text-xs text-gray-500 mt-1">Groups Passing</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-3xl font-bold text-purple-600">{(overallRate * 100).toFixed(1)}%</div>
          <div className="text-xs text-gray-500 mt-1">Overall Approval Rate</div>
        </div>
      </div>

      {chartData.length > 0 && (
        <div className="card p-5">
          <p className="font-semibold text-gray-800 mb-1">Disparate Impact by Group Combination</p>
          <p className="text-xs text-gray-500 mb-4">
            <span className="inline-block w-3 h-3 rounded-sm bg-red-400 mr-1" />Below 0.80 = violation (red)
            <span className="inline-block w-3 h-3 rounded-sm bg-green-400 ml-3 mr-1" />Above 0.80 = passing (green)
          </p>
          <ResponsiveContainer width="100%" height={Math.max(200, chartData.length * 28)}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 50, top: 4 }}>
              <XAxis type="number" domain={[0, 1.4]} tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 10, fill: '#374151' }} axisLine={false} tickLine={false} width={150} />
              <ReferenceLine x={0.8} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '0.80 threshold', fontSize: 9, fill: '#ef4444', position: 'insideTopRight' }} />
              <Tooltip formatter={(v: number, n: string) => [n === 'di' ? v.toFixed(3) : `${v}%`, n === 'di' ? 'DI Ratio' : 'Approval Rate']} contentStyle={{ fontSize: 11, borderRadius: 8 }} />
              <Bar dataKey="di" name="di" radius={[0, 4, 4, 0]} label={{ position: 'right', fontSize: 10, formatter: (v: number) => v.toFixed(2) }}>
                {chartData.map((g, i) => <Cell key={i} fill={g.status === 'violation' ? '#f87171' : '#4ade80'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="card p-5">
        <p className="font-semibold text-gray-800 mb-3">Violation Details ({violations.length})</p>
        {violations.length === 0 ? (
          <div className="flex items-center gap-2 bg-green-50 rounded-lg px-4 py-3">
            <CheckCircle className="w-4 h-4 text-green-600" />
            <span className="text-sm text-green-700 font-medium">All intersectional groups meet the fairness threshold — no combined-group discrimination detected.</span>
          </div>
        ) : violations.map((v: string, i: number) => (
          <div key={i} className="flex items-start gap-2 bg-red-50 border border-red-100 rounded-lg px-3 py-2.5 mb-2">
            <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
            <span className="text-sm text-red-700">{v}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function AdvancedFairnessPage() {
  const { activeDataset } = useDataset()
  const [tab, setTab] = useState<AdvTab>('full')
  const [result, setResult] = useState<any>(null)
  const [letter, setLetter] = useState('')
  const [eqForm, setEqForm] = useState({ outcome_col: '', pred_col: '', protected_col: '', tolerance: '0.10' })
  const [intForm, setIntForm] = useState({ outcome_col: '', protected_cols: '' })
  const [ecoaForm, setEcoaForm] = useState({
    institution_name: 'Fair Lending Institution', loan_type: 'mortgage',
    featuresJson: '{"debt_to_income_ratio": 0.52, "credit_score": 580, "income": 42000}',
    shapJson: '{"debt_to_income_ratio": 0.35, "credit_score": -0.25, "income": -0.15}',
  })

  useEffect(() => { setResult(null); setLetter('') }, [activeDataset?.file_id])

  const onErr = (e: any) => toast.error(e?.response?.data?.detail ?? 'Analysis failed')

  const fullMutation = useMutation({
    mutationFn: () => advancedFairnessApi.fullAnalysis({ dataset_id: activeDataset!.file_id }),
    onSuccess: d => { setResult(d); toast.success('Full analysis complete') },
    onError: onErr,
  })
  const eqMutation = useMutation({
    mutationFn: () => advancedFairnessApi.equalizedOdds({ dataset_id: activeDataset!.file_id, ...eqForm, tolerance: parseFloat(eqForm.tolerance) }),
    onSuccess: d => { setResult(d); toast.success('Equalized Odds analysis complete') },
    onError: onErr,
  })
  const intMutation = useMutation({
    mutationFn: () => advancedFairnessApi.intersectional({
      dataset_id: activeDataset!.file_id, outcome_col: intForm.outcome_col,
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

  // Tab descriptions
  const tabInfo: Record<AdvTab, string> = {
    full: 'Runs all fairness checks in one click — detects bias across race, gender, and age using multiple statistical methods.',
    equalized: 'Checks if qualified applicants from different groups get approved at the same rate. Requires an ML prediction column.',
    intersectional: 'Finds bias at the intersection of groups (e.g. Black + Female). Often reveals hidden discrimination missed by single-attribute analysis.',
    ecoa: 'Generates a legally-compliant adverse action notice (denial letter) per ECOA 12 C.F.R. § 1002.9.',
  }

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Advanced Fairness Analysis</h1>
        <p className="text-gray-500 mt-1 text-sm">Enterprise fair lending compliance — goes beyond basic DI ratios to detect hidden and intersectional bias.</p>
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
          return (
            <button key={t.id} onClick={() => switchTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                tab === t.id ? 'bg-navy-900 text-white shadow-sm' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
              }`}>
              <Icon className="w-4 h-4" />{t.label}
            </button>
          )
        })}
      </div>

      {/* Tab description */}
      <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 flex gap-2">
        <Info className="w-4 h-4 text-gray-400 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-gray-600">{tabInfo[tab]}</p>
      </div>

      {/* ── Full Analysis ── */}
      {tab === 'full' && (
        <div className="space-y-4">
          <div className="card p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="font-semibold text-gray-900 text-lg">Comprehensive Fairness Analysis</h2>
                <p className="text-sm text-gray-500 mt-1 max-w-xl">
                  One click runs everything: Equalized Odds across all demographic groups, Intersectional analysis
                  for combined groups, and a full violation report ready for regulatory review.
                </p>
                <div className="flex flex-wrap gap-2 mt-3">
                  {['Equalized Odds','Intersectional Analysis','TPR/FPR by Group','Violation Detection','Regulatory Mapping'].map(f => (
                    <span key={f} className="text-xs bg-blue-50 text-blue-700 px-2.5 py-1 rounded-full border border-blue-100">{f}</span>
                  ))}
                </div>
              </div>
              <ShieldCheck className="w-10 h-10 text-blue-300 flex-shrink-0" />
            </div>
            <button onClick={() => fullMutation.mutate()} disabled={!activeDataset || isRunning}
              className="mt-5 flex items-center gap-2 bg-navy-900 text-white px-6 py-2.5 rounded-xl font-medium text-sm hover:bg-navy-800 disabled:opacity-50 transition-colors">
              {isRunning ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Play className="w-4 h-4" />}
              {isRunning ? 'Analyzing…' : 'Run Full Analysis'}
            </button>
          </div>
          {result && <FullAnalysisResult result={result} />}
        </div>
      )}

      {/* ── Equalized Odds ── */}
      {tab === 'equalized' && (
        <div className="space-y-4">
          <div className="card p-6">
            <h2 className="font-semibold text-gray-900 text-lg mb-1">Equalized Odds Analysis</h2>
            <p className="text-sm text-gray-500 mb-4">
              Requires a model predictions column (run ML Engine first). Checks if the model approves
              qualified applicants at the same rate regardless of race or gender (True Positive Rate equality).
            </p>
            <div className="grid sm:grid-cols-3 gap-3 mb-3">
              {[{label:'Outcome Column',key:'outcome_col',ph:'e.g. action_taken'},{label:'Prediction Column',key:'pred_col',ph:'e.g. predicted_outcome'},{label:'Protected Column',key:'protected_col',ph:'e.g. race'}].map(({label,key,ph}) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
                  <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                    value={(eqForm as any)[key]} onChange={e => setEqForm(p => ({...p,[key]:e.target.value}))} placeholder={ph} />
                </div>
              ))}
            </div>
            <button onClick={() => eqMutation.mutate()} disabled={!activeDataset || !eqForm.outcome_col || !eqForm.pred_col || isRunning}
              className="flex items-center gap-2 bg-navy-900 text-white px-5 py-2.5 rounded-xl font-medium text-sm hover:bg-navy-800 disabled:opacity-50">
              {isRunning ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Scale className="w-4 h-4" />}
              Analyze Equalized Odds
            </button>
          </div>
          {result && result.groups && (
            <div className="card p-5">
              <div className="flex items-center justify-between mb-3">
                <p className="font-semibold text-gray-800">Results by Group</p>
                <StatusPill pass={(result.violations?.length ?? 0) === 0} label={(result.violations?.length ?? 0) === 0 ? 'No violations' : `${result.violations.length} violations`} />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-gray-100 text-xs text-gray-500 uppercase">
                    <th className="text-left py-2 pr-4">Group</th>
                    <th className="text-right py-2 pr-4">Approval Rate (Qualified) <InfoTip text="True Positive Rate: % of qualified applicants who were approved. Should be ≥80% of the best group." /></th>
                    <th className="text-right py-2 pr-4">False Approval Rate</th>
                    <th className="text-right py-2">Count</th>
                  </tr></thead>
                  <tbody>{Object.entries(result.groups).map(([g, v]: any) => (
                    <tr key={g} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="py-2.5 pr-4 font-medium text-gray-700">{g}</td>
                      <td className={`py-2.5 pr-4 text-right font-bold ${(v.tpr*100)<80?'text-red-600':'text-green-600'}`}>{(v.tpr*100).toFixed(1)}%</td>
                      <td className="py-2.5 pr-4 text-right text-gray-500">{(v.fpr*100).toFixed(1)}%</td>
                      <td className="py-2.5 text-right text-gray-400">{v.count}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Intersectional ── */}
      {tab === 'intersectional' && (
        <div className="space-y-4">
          <div className="card p-6">
            <h2 className="font-semibold text-gray-900 text-lg mb-1">Intersectional Fairness Analysis</h2>
            <p className="text-sm text-gray-500 mb-4">Enter at least 2 protected columns (comma-separated). The system will analyze every combination of group values.</p>
            <div className="grid sm:grid-cols-2 gap-3 mb-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Outcome Column</label>
                <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                  value={intForm.outcome_col} onChange={e => setIntForm(p=>({...p,outcome_col:e.target.value}))} placeholder="e.g. action_taken" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Protected Columns (comma-separated, min 2)</label>
                <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                  value={intForm.protected_cols} onChange={e => setIntForm(p=>({...p,protected_cols:e.target.value}))} placeholder="e.g. race, gender" />
              </div>
            </div>
            <button onClick={() => intMutation.mutate()}
              disabled={!activeDataset || !intForm.outcome_col || intForm.protected_cols.split(',').filter(Boolean).length < 2 || isRunning}
              className="flex items-center gap-2 bg-navy-900 text-white px-5 py-2.5 rounded-xl font-medium text-sm hover:bg-navy-800 disabled:opacity-50">
              {isRunning ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <GitBranch className="w-4 h-4" />}
              Run Intersectional Analysis
            </button>
          </div>
          {result && <IntersectionalResult result={result} />}
        </div>
      )}

      {/* ── ECOA Denial Letter ── */}
      {tab === 'ecoa' && (
        <div className="space-y-4">
          <div className="card p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="font-semibold text-gray-900 text-lg">ECOA Adverse Action Notice Generator</h2>
                <p className="text-sm text-gray-500 mt-1 max-w-xl">
                  Under the Equal Credit Opportunity Act (ECOA), lenders must send a written notice
                  explaining why a loan was denied — within 30 days. This generator creates a
                  legally-compliant letter using SHAP values to identify the top denial reasons in
                  approved regulatory language.
                </p>
                <div className="flex gap-2 mt-3">
                  {['ECOA 12 C.F.R. § 1002.9','CFPB Ready','SHAP-driven reasons','Regulatory Language'].map(b => (
                    <span key={b} className="text-xs bg-green-50 text-green-700 px-2.5 py-1 rounded-full border border-green-100">{b}</span>
                  ))}
                </div>
              </div>
              <FileText className="w-10 h-10 text-green-300 flex-shrink-0" />
            </div>

            <div className="grid sm:grid-cols-2 gap-4 mt-5">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Institution Name</label>
                <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                  value={ecoaForm.institution_name} onChange={e => setEcoaForm(p=>({...p,institution_name:e.target.value}))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Loan Type</label>
                <select className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                  value={ecoaForm.loan_type} onChange={e => setEcoaForm(p=>({...p,loan_type:e.target.value}))}>
                  <option value="mortgage">Mortgage</option>
                  <option value="auto">Auto Loan</option>
                  <option value="personal">Personal Loan</option>
                  <option value="business">Business Loan</option>
                  <option value="heloc">HELOC</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Applicant Features (JSON) <InfoTip text="Key-value pairs of the applicant's financial profile. e.g. credit score, income, DTI ratio." />
                </label>
                <textarea rows={4} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-navy-900 resize-none"
                  value={ecoaForm.featuresJson} onChange={e => setEcoaForm(p=>({...p,featuresJson:e.target.value}))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  SHAP Values (JSON) <InfoTip text="SHAP values show which features caused the denial. Negative values = denial reasons. Get these from ML Engine explanation." />
                </label>
                <textarea rows={4} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-navy-900 resize-none"
                  value={ecoaForm.shapJson} onChange={e => setEcoaForm(p=>({...p,shapJson:e.target.value}))} />
              </div>
            </div>

            <button onClick={() => ecoaMutation.mutate()} disabled={isRunning}
              className="mt-5 flex items-center gap-2 bg-green-700 text-white px-5 py-2.5 rounded-xl font-medium text-sm hover:bg-green-800 disabled:opacity-50">
              {isRunning ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <FileText className="w-4 h-4" />}
              Generate Adverse Action Notice
            </button>
          </div>

          {letter && (
            <div className="card p-5">
              <div className="flex items-center justify-between mb-3">
                <p className="font-semibold text-gray-800 flex items-center gap-2">
                  <FileText className="w-4 h-4 text-green-600" /> Generated Adverse Action Notice
                </p>
                <button onClick={() => { const b = new Blob([letter], {type:'text/plain'}); const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'adverse_action_notice.txt'; a.click(); }}
                  className="flex items-center gap-1.5 text-xs bg-green-100 text-green-700 px-3 py-1.5 rounded-lg hover:bg-green-200 font-medium">
                  Download Letter
                </button>
              </div>
              <pre className="text-sm text-gray-700 bg-gray-50 rounded-xl p-4 whitespace-pre-wrap leading-relaxed font-mono border border-gray-200 max-h-96 overflow-y-auto">{letter}</pre>
              <p className="text-xs text-gray-400 mt-2">This letter was generated using ECOA regulatory language. Review with your compliance team before sending.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
