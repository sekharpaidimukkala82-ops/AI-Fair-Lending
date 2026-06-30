import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ClipboardCheck, Download, FileSearch, MapPin, Clock, CheckCircle, XCircle } from 'lucide-react'
import { complianceApi } from '../lib/api'
import { Alert, Spinner, EmptyState } from '../components/ui'
import { useDataset } from '../hooks/useDataset'
import clsx from 'clsx'

type CompTab = 'hmda' | 'cra' | 'exam' | 'audit'

const TABS: { id: CompTab; label: string; icon: React.ReactNode }[] = [
  { id: 'hmda',  label: 'HMDA Validation',   icon: <ClipboardCheck className="w-3.5 h-3.5" /> },
  { id: 'cra',   label: 'CRA Analysis',       icon: <MapPin className="w-3.5 h-3.5" /> },
  { id: 'exam',  label: 'Exam Export',        icon: <Download className="w-3.5 h-3.5" /> },
  { id: 'audit', label: 'Audit Trail',        icon: <Clock className="w-3.5 h-3.5" /> },
]

interface HMDAResult {
  total_records: number
  valid_records: number
  error_count: number
  warning_count: number
  errors: Array<{ row: number; field: string; message: string; ffiec_edit: string; severity: string }>
  warnings: Array<{ type: string; message: string; severity: string; ffiec_edit: string }>
  pass_rate: number
  ffiec_ready: boolean
}

export default function CompliancePage() {
  const { activeDataset } = useDataset()
  const [tab, setTab] = useState<CompTab>('hmda')
  const [error, setError] = useState('')
  const [hmda, setHmda] = useState<HMDAResult | null>(null)
  const [cra, setCra] = useState<Record<string, unknown> | null>(null)
  const [generatingExam, setGeneratingExam] = useState(false)

  const hmdaMutation = useMutation({
    mutationFn: () => complianceApi.validateHMDA(activeDataset!.file_id),
    onSuccess: d => { setHmda(d); setError('') },
    onError: (e: unknown) => setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Validation failed'),
  })

  const craMutation = useMutation({
    mutationFn: () => complianceApi.craAnalysis(activeDataset!.file_id),
    onSuccess: d => { setCra(d); setError('') },
    onError: (e: unknown) => setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'CRA analysis failed'),
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
    } catch (e: unknown) {
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Export failed')
    } finally {
      setGeneratingExam(false)
    }
  }

  const { data: auditLogs, isLoading: logsLoading } = useQuery({
    queryKey: ['audit-trail'],
    queryFn: () => complianceApi.auditTrail(200),
    enabled: tab === 'audit',
    refetchInterval: 30_000,
  })

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div>
        <h1 className="text-2xl font-semibold text-white">Compliance</h1>
        <p className="text-gray-500 text-sm mt-1">HMDA validation · CRA analysis · Regulatory exam export · Audit trail</p>
      </div>

      {!activeDataset && <Alert type="warning">Select a dataset from the top bar.</Alert>}
      {error && <Alert type="error" onClose={() => setError('')}>{error}</Alert>}

      <div className="flex gap-1 flex-wrap">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={clsx('flex items-center gap-2 px-3 py-1.5 rounded text-sm transition-colors',
              tab === t.id ? 'bg-accent text-white' : 'bg-surface-2 border border-white/5 text-gray-400 hover:text-gray-200')}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* HMDA Validation */}
      {tab === 'hmda' && (
        <div className="space-y-5">
          <div className="card p-5 space-y-3">
            <p className="section-header">HMDA LAR File Validation</p>
            <p className="text-sm text-gray-400">
              Validates dataset against FFIEC HMDA edit specifications — exactly what regulators check before
              submission. Checks field validity, code values, and logical consistency.
            </p>
            <button onClick={() => hmdaMutation.mutate()} disabled={!activeDataset || hmdaMutation.isPending} className="btn-primary">
              {hmdaMutation.isPending ? <Spinner size="sm" /> : <FileSearch className="w-4 h-4" />} Validate HMDA
            </button>
          </div>

          {hmda && (
            <div className="space-y-4">
              {/* Summary cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                  { label: 'Total Records', val: hmda.total_records.toLocaleString(), cls: 'text-white' },
                  { label: 'Valid Records', val: hmda.valid_records.toLocaleString(), cls: 'text-success' },
                  { label: 'Errors', val: hmda.error_count, cls: hmda.error_count > 0 ? 'text-danger' : 'text-success' },
                  { label: 'Pass Rate', val: `${(hmda.pass_rate * 100).toFixed(1)}%`, cls: hmda.pass_rate >= 0.99 ? 'text-success' : 'text-warning' },
                ].map(s => (
                  <div key={s.label} className="stat-card">
                    <span className="text-gray-500 text-xs uppercase tracking-wide">{s.label}</span>
                    <span className={`text-2xl font-bold ${s.cls}`}>{s.val}</span>
                  </div>
                ))}
              </div>

              <div className="card p-4 flex items-center gap-3">
                {hmda.ffiec_ready
                  ? <CheckCircle className="w-5 h-5 text-success shrink-0" />
                  : <XCircle className="w-5 h-5 text-danger shrink-0" />}
                <div>
                  <p className={`font-medium text-sm ${hmda.ffiec_ready ? 'text-success' : 'text-danger'}`}>
                    {hmda.ffiec_ready ? 'FFIEC Ready — No critical errors' : 'Not FFIEC Ready — Errors must be corrected'}
                  </p>
                  <p className="text-xs text-gray-500">Reference: FFIEC HMDA Filing Instructions Guide</p>
                </div>
              </div>

              {hmda.warnings.length > 0 && (
                <div className="card p-5">
                  <p className="section-header">Warnings ({hmda.warnings.length})</p>
                  <div className="space-y-2">
                    {hmda.warnings.map((w, i) => (
                      <div key={i} className="text-xs bg-warning/8 text-warning rounded px-3 py-2 flex justify-between">
                        <span>{w.message}</span>
                        <span className="text-gray-500">{w.ffiec_edit}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {hmda.errors.length > 0 && (
                <div className="card">
                  <div className="px-5 py-4 border-b border-white/5 flex items-center justify-between">
                    <p className="section-header mb-0">Errors (showing up to 50)</p>
                    <span className="badge-danger">{hmda.error_count} total</span>
                  </div>
                  <div className="divide-y divide-white/5">
                    <div className="grid grid-cols-4 px-5 py-2 text-xs text-gray-500 uppercase tracking-wide">
                      <span>Row</span><span>Field</span><span className="col-span-2">Message</span>
                    </div>
                    {hmda.errors.slice(0, 50).map((e, i) => (
                      <div key={i} className="table-row grid grid-cols-4 px-5 py-2.5 text-xs">
                        <span className="text-gray-500 font-mono">{e.row}</span>
                        <span className="text-warning">{e.field}</span>
                        <span className="col-span-2 text-gray-300">{e.message} <span className="text-gray-600">({e.ffiec_edit})</span></span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* CRA */}
      {tab === 'cra' && (
        <div className="space-y-5">
          <div className="card p-5 space-y-3">
            <p className="section-header">CRA Analysis</p>
            <p className="text-sm text-gray-400">
              Community Reinvestment Act analysis — examines lending patterns in low/moderate-income
              census tracts alongside HMDA data.
            </p>
            <button onClick={() => craMutation.mutate()} disabled={!activeDataset || craMutation.isPending} className="btn-primary">
              {craMutation.isPending ? <Spinner size="sm" /> : <MapPin className="w-4 h-4" />} Run CRA Analysis
            </button>
          </div>

          {cra && (
            <div className="space-y-4">
              {cra.income_analysis && (
                <div className="card p-5">
                  <p className="section-header">Income & LMI Analysis</p>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    {[
                      ['LMI Applicants', `${(cra.income_analysis as Record<string,unknown>).lmi_count ?? 0}`, 'text-warning'],
                      ['LMI %', `${(cra.income_analysis as Record<string,unknown>).lmi_percentage ?? 0}%`, 'text-warning'],
                      ['Median Income', `$${Number((cra.income_analysis as Record<string,unknown>).median_income ?? 0).toLocaleString()}`, 'text-white'],
                    ].map(([label, val, cls]) => (
                      <div key={label} className="stat-card">
                        <span className="text-gray-500 text-xs">{label}</span>
                        <span className={`text-xl font-bold ${cls}`}>{String(val)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {cra.overall_approval_rate != null && (
                <div className="card p-5">
                  <p className="section-header">Overall Approval Rate</p>
                  <p className="text-3xl font-bold text-white">{(Number(cra.overall_approval_rate) * 100).toFixed(1)}%</p>
                </div>
              )}
              {cra.cra_notes && (
                <div className="card p-5">
                  <p className="section-header">Notes</p>
                  {(cra.cra_notes as string[]).map((n, i) => (
                    <p key={i} className="text-sm text-gray-400 mb-1">• {n}</p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Exam Export */}
      {tab === 'exam' && (
        <div className="space-y-5">
          <div className="card p-5 space-y-4">
            <p className="section-header">Regulatory Exam Export Package</p>
            <p className="text-sm text-gray-400">
              One-click ZIP package formatted for OCC/FDIC/Federal Reserve examination. Includes:
            </p>
            <div className="grid sm:grid-cols-2 gap-3 text-sm">
              {[
                ['00_metadata.json', 'Platform info, dataset details, export context'],
                ['01_methodology.txt', 'Statistical methodology, regulatory references, findings summary'],
                ['02_statistical_results.json', 'All fairness audit results with scores and indicators'],
                ['03_audit_trail.csv', 'Complete action log: who accessed what, when, and results'],
                ['04_remediation_plan_template.txt', 'Structured template for examiner remediation documentation'],
              ].map(([file, desc]) => (
                <div key={file} className="bg-surface-3 rounded p-3 space-y-0.5">
                  <p className="font-mono text-xs text-accent-2">{file}</p>
                  <p className="text-xs text-gray-500">{desc}</p>
                </div>
              ))}
            </div>
            <button onClick={examExport} disabled={!activeDataset || generatingExam} className="btn-primary">
              {generatingExam ? <Spinner size="sm" /> : <Download className="w-4 h-4" />} Download Exam Package (ZIP)
            </button>
          </div>
        </div>
      )}

      {/* Audit Trail */}
      {tab === 'audit' && (
        <div className="space-y-4">
          <div className="card p-4 flex items-center justify-between">
            <p className="section-header mb-0">Audit Trail — Last 200 Actions</p>
            <span className="text-xs text-gray-500">Updates every 30s</span>
          </div>
          {logsLoading ? (
            <div className="flex justify-center py-8"><Spinner /></div>
          ) : auditLogs?.length > 0 ? (
            <div className="card divide-y divide-white/5">
              <div className="grid grid-cols-4 px-5 py-3 text-xs text-gray-500 uppercase tracking-wide">
                <span>Time</span><span>Action</span><span>User</span><span>Resource</span>
              </div>
              {(auditLogs as Array<{ action: string; user_id: string; resource_type: string; resource_id: string; created_at: string; details: unknown }>).map((log, i) => (
                <div key={i} className="table-row grid grid-cols-4 px-5 py-2.5 text-xs items-center">
                  <span className="text-gray-500 font-mono">{new Date(log.created_at).toLocaleTimeString()}</span>
                  <span className="text-accent-2">{log.action}</span>
                  <span className="text-gray-400 truncate">{log.user_id?.slice(0, 8) || '—'}</span>
                  <span className="text-gray-500 truncate">{log.resource_type}: {log.resource_id?.slice(0, 8)}</span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={<Clock className="w-10 h-10" />} title="No audit entries yet" description="All platform actions are logged here for compliance review" />
          )}
        </div>
      )}
    </div>
  )
}
