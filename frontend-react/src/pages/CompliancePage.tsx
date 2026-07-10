import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  ClipboardCheck, Download, FileSearch, MapPin, Clock,
  CheckCircle, XCircle, AlertTriangle, Info, Shield
} from 'lucide-react'
import { complianceApi } from '../lib/api'
import { useDataset } from '../hooks/useDataset'
import toast from 'react-hot-toast'

type CompTab = 'hmda' | 'cra' | 'exam' | 'audit'

const TABS = [
  { id: 'hmda' as CompTab,  label: 'HMDA Validation',  icon: ClipboardCheck, desc: 'Validate against FFIEC edit specs' },
  { id: 'cra' as CompTab,   label: 'CRA Analysis',      icon: MapPin,         desc: 'Community Reinvestment Act analysis' },
  { id: 'exam' as CompTab,  label: 'Exam Export',       icon: Download,       desc: 'Regulatory exam package ZIP' },
  { id: 'audit' as CompTab, label: 'Audit Trail',       icon: Clock,          desc: 'Complete action log' },
]

export default function CompliancePage() {
  const { activeDataset } = useDataset()
  const [tab, setTab] = useState<CompTab>('hmda')
  const [hmda, setHmda] = useState<any>(null)
  const [cra, setCra] = useState<any>(null)
  const [generatingExam, setGeneratingExam] = useState(false)

  const hmdaMutation = useMutation({
    mutationFn: () => complianceApi.validateHMDA(activeDataset!.file_id),
    onSuccess: d => setHmda(d),
    onError: (e: any) => toast.error(e.response?.data?.detail || 'HMDA validation failed'),
  })

  const craMutation = useMutation({
    mutationFn: () => complianceApi.craAnalysis(activeDataset!.file_id),
    onSuccess: d => setCra(d),
    onError: (e: any) => toast.error(e.response?.data?.detail || 'CRA analysis failed'),
  })

  const examExport = async () => {
    if (!activeDataset) return
    setGeneratingExam(true)
    try {
      const resp = await complianceApi.examExport(activeDataset.file_id)
      const blob = new Blob([resp.data], { type: 'application/zip' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `exam_package_${activeDataset.file_id.slice(0, 8)}.zip`; a.click()
      URL.revokeObjectURL(url)
      toast.success('Exam package downloaded')
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Export failed')
    } finally { setGeneratingExam(false) }
  }

  const { data: auditLogs = [], isLoading: logsLoading } = useQuery({
    queryKey: ['audit-trail'],
    queryFn: () => complianceApi.auditTrail(200),
    enabled: tab === 'audit',
    refetchInterval: 30000,
  })

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Compliance</h1>
        <p className="text-gray-500 mt-1 text-sm">HMDA validation · CRA analysis · Regulatory exam export · Audit trail</p>
      </div>

      {!activeDataset && (
        <div className="card p-8 text-center">
          <Shield className="w-10 h-10 text-blue-400 mx-auto mb-3" />
          <p className="text-gray-600">Select a dataset from the top bar to run compliance checks.</p>
        </div>
      )}

      {/* Tab bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {TABS.map(({ id, label, icon: Icon, desc }) => (
          <button key={id} onClick={() => setTab(id)}
            className={`card p-4 text-left transition-all ${tab === id ? 'border-navy-900 bg-blue-50' : 'hover:border-gray-300'}`}>
            <Icon className={`w-5 h-5 mb-2 ${tab === id ? 'text-navy-900' : 'text-gray-400'}`} />
            <div className={`text-sm font-semibold ${tab === id ? 'text-navy-900' : 'text-gray-700'}`}>{label}</div>
            <div className="text-xs text-gray-400 mt-0.5">{desc}</div>
          </button>
        ))}
      </div>

      {/* ── HMDA Validation ── */}
      {tab === 'hmda' && (
        <div className="space-y-5">
          <div className="card p-6">
            <h2 className="font-semibold text-gray-900 text-lg mb-1">HMDA LAR File Validation</h2>
            <p className="text-sm text-gray-500 mb-4 max-w-xl">
              Validates your dataset against FFIEC HMDA edit specifications — the same checks
              regulators run before submission. Identifies errors, warnings, and field-level issues
              that would cause your LAR filing to be rejected.
            </p>
            <div className="flex flex-wrap gap-2 mb-5">
              {['Syntactical Edits','Validity Edits','Quality Edits','Macro Quality Edits'].map(e => (
                <span key={e} className="text-xs bg-blue-50 text-blue-700 px-2.5 py-1 rounded-full border border-blue-100">{e}</span>
              ))}
            </div>
            <button onClick={() => hmdaMutation.mutate()} disabled={!activeDataset || hmdaMutation.isPending}
              className="btn-primary flex items-center gap-2">
              {hmdaMutation.isPending ? <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"/>Validating…</> : <><FileSearch className="w-4 h-4"/>Validate HMDA</>}
            </button>
          </div>

          {hmda && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                  { label: 'Total Records', val: hmda.total_records?.toLocaleString(), color: 'text-gray-900' },
                  { label: 'Valid Records', val: hmda.valid_records?.toLocaleString(), color: 'text-green-600' },
                  { label: 'Errors', val: hmda.error_count, color: hmda.error_count > 0 ? 'text-red-600' : 'text-green-600' },
                  { label: 'Pass Rate', val: `${((hmda.pass_rate || 0) * 100).toFixed(1)}%`, color: (hmda.pass_rate || 0) >= 0.99 ? 'text-green-600' : 'text-amber-600' },
                ].map(s => (
                  <div key={s.label} className="card p-4 text-center">
                    <div className={`text-3xl font-bold ${s.color}`}>{s.val}</div>
                    <div className="text-xs text-gray-500 mt-1">{s.label}</div>
                  </div>
                ))}
              </div>

              <div className={`card p-4 flex items-center gap-3 ${hmda.ffiec_ready ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
                {hmda.ffiec_ready
                  ? <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
                  : <XCircle className="w-5 h-5 text-red-600 flex-shrink-0" />}
                <div>
                  <p className={`font-semibold text-sm ${hmda.ffiec_ready ? 'text-green-800' : 'text-red-800'}`}>
                    {hmda.ffiec_ready ? 'FFIEC Ready — No critical errors found' : 'Not FFIEC Ready — Errors must be corrected before submission'}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">Reference: FFIEC HMDA Filing Instructions Guide 2024</p>
                </div>
              </div>

              {(hmda.warnings || []).length > 0 && (
                <div className="card p-5">
                  <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-500" /> Warnings ({hmda.warnings.length})
                  </h3>
                  <div className="space-y-2">
                    {hmda.warnings.map((w: any, i: number) => (
                      <div key={i} className="flex items-start justify-between bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                        <span className="text-sm text-amber-800">{w.message}</span>
                        <span className="text-xs text-gray-400 ml-3 flex-shrink-0">{w.ffiec_edit}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(hmda.errors || []).length > 0 && (
                <div className="card overflow-hidden">
                  <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between bg-red-50">
                    <h3 className="font-semibold text-red-800 flex items-center gap-2">
                      <XCircle className="w-4 h-4" /> Errors (showing up to 50 of {hmda.error_count})
                    </h3>
                  </div>
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 border-b border-gray-200">
                      <tr>
                        <th className="text-left px-4 py-2 font-semibold text-gray-600">Row</th>
                        <th className="text-left px-4 py-2 font-semibold text-gray-600">Field</th>
                        <th className="text-left px-4 py-2 font-semibold text-gray-600">Message</th>
                        <th className="text-left px-4 py-2 font-semibold text-gray-600">Edit Code</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {hmda.errors.slice(0, 50).map((e: any, i: number) => (
                        <tr key={i} className="hover:bg-gray-50">
                          <td className="px-4 py-2 font-mono text-gray-500">{e.row}</td>
                          <td className="px-4 py-2 text-amber-600 font-medium">{e.field}</td>
                          <td className="px-4 py-2 text-gray-700">{e.message}</td>
                          <td className="px-4 py-2 text-gray-400">{e.ffiec_edit}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── CRA Analysis ── */}
      {tab === 'cra' && (
        <div className="space-y-5">
          <div className="card p-6">
            <h2 className="font-semibold text-gray-900 text-lg mb-1">CRA Analysis</h2>
            <p className="text-sm text-gray-500 mb-4 max-w-xl">
              Community Reinvestment Act analysis — examines lending patterns in low and moderate-income
              census tracts. Regulators use this to assess whether banks are meeting the credit needs
              of all communities, including underserved ones.
            </p>
            <button onClick={() => craMutation.mutate()} disabled={!activeDataset || craMutation.isPending}
              className="btn-primary flex items-center gap-2">
              {craMutation.isPending ? <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"/>Analyzing…</> : <><MapPin className="w-4 h-4"/>Run CRA Analysis</>}
            </button>
          </div>
          {cra && (
            <div className="space-y-4">
              {cra.income_analysis && (
                <div className="card p-5">
                  <h3 className="font-semibold text-gray-800 mb-4">Income & LMI Analysis</h3>
                  <div className="grid grid-cols-3 gap-4">
                    {[
                      { label: 'LMI Applicants', val: cra.income_analysis.lmi_count, color: 'text-amber-600' },
                      { label: 'LMI %', val: `${cra.income_analysis.lmi_percentage}%`, color: 'text-amber-600' },
                      { label: 'Median Income', val: `$${Number(cra.income_analysis.median_income || 0).toLocaleString()}`, color: 'text-gray-900' },
                    ].map(s => (
                      <div key={s.label} className="card p-4 text-center">
                        <div className={`text-2xl font-bold ${s.color}`}>{s.val}</div>
                        <div className="text-xs text-gray-500 mt-1">{s.label}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {cra.overall_approval_rate != null && (
                <div className="card p-5">
                  <h3 className="font-semibold text-gray-800 mb-2">Overall Approval Rate</h3>
                  <div className="text-4xl font-bold text-navy-900">{(Number(cra.overall_approval_rate) * 100).toFixed(1)}%</div>
                </div>
              )}
              {cra.cra_notes?.length > 0 && (
                <div className="card p-5">
                  <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                    <Info className="w-4 h-4 text-blue-500" /> CRA Notes
                  </h3>
                  {cra.cra_notes.map((n: string, i: number) => (
                    <p key={i} className="text-sm text-gray-600 mb-1 flex items-start gap-2">
                      <span className="text-blue-500 mt-0.5">•</span>{n}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Exam Export ── */}
      {tab === 'exam' && (
        <div className="card p-6 space-y-5">
          <h2 className="font-semibold text-gray-900 text-lg">Regulatory Exam Export Package</h2>
          <p className="text-sm text-gray-500 max-w-xl">
            One-click ZIP package formatted for OCC, FDIC, and Federal Reserve examination teams.
            Contains all documentation an examiner needs to verify your fair lending compliance program.
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            {[
              ['00_metadata.json', 'Platform info, dataset details, export timestamp'],
              ['01_methodology.txt', 'Statistical methodology, regulatory references, findings summary'],
              ['02_statistical_results.json', 'All fairness audit results with scores and DI ratios'],
              ['03_audit_trail.csv', 'Complete action log: who accessed what, when, results'],
              ['04_remediation_plan_template.txt', 'Structured template for documenting remediation steps'],
            ].map(([file, desc]) => (
              <div key={file} className="bg-gray-50 border border-gray-200 rounded-xl p-3 space-y-1">
                <p className="font-mono text-xs text-blue-700 font-semibold">{file}</p>
                <p className="text-xs text-gray-500">{desc}</p>
              </div>
            ))}
          </div>
          <button onClick={examExport} disabled={!activeDataset || generatingExam}
            className="btn-primary flex items-center gap-2">
            {generatingExam ? <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"/>Generating…</> : <><Download className="w-4 h-4"/>Download Exam Package (ZIP)</>}
          </button>
          <p className="text-xs text-gray-400">Package includes all data required under 12 C.F.R. § 1003 (HMDA) and ECOA examination procedures.</p>
        </div>
      )}

      {/* ── Audit Trail ── */}
      {tab === 'audit' && (
        <div className="space-y-4">
          <div className="card p-4 flex items-center justify-between">
            <h2 className="font-semibold text-gray-800 flex items-center gap-2">
              <Clock className="w-4 h-4 text-blue-500" /> Audit Trail — Last 200 Actions
            </h2>
            <span className="text-xs text-gray-400">Updates every 30s · All actions are permanently logged</span>
          </div>
          {logsLoading ? (
            <div className="card p-8 text-center text-gray-400">Loading audit trail…</div>
          ) : (auditLogs as any[]).length > 0 ? (
            <div className="card overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="text-left px-4 py-3 font-semibold text-gray-600">Time</th>
                    <th className="text-left px-4 py-3 font-semibold text-gray-600">Action</th>
                    <th className="text-left px-4 py-3 font-semibold text-gray-600">User</th>
                    <th className="text-left px-4 py-3 font-semibold text-gray-600">Resource</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {(auditLogs as any[]).map((log, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5 font-mono text-gray-400">{new Date(log.created_at).toLocaleString()}</td>
                      <td className="px-4 py-2.5 text-blue-600 font-medium">{log.action}</td>
                      <td className="px-4 py-2.5 text-gray-500">{log.user_id?.slice(0, 8) || '—'}</td>
                      <td className="px-4 py-2.5 text-gray-400">{log.resource_type}: {log.resource_id?.slice(0, 8)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="card p-8 text-center text-gray-400">
              <Clock className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p>No audit entries yet — all platform actions will appear here.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
