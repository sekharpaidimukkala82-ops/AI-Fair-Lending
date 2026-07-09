import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useDatasetStore } from '../store/datasetStore'
import api from '../lib/api'
import { safeFormatDistance } from '../lib/utils'
import toast from 'react-hot-toast'
import { FileText, Download, Loader2, Info, CheckCircle, BarChart3, Shield, TrendingUp, Users } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

const _unused = formatDistanceToNow // suppress unused warning

interface ReportRecord {
  report_id?: string
  id?: string
  dataset_filename: string
  report_type: string
  format: string
  file_size?: number
  created_at: string
  download_url?: string
}

const REPORT_TYPES = [
  {
    type: 'fairness',
    label: 'Fairness Report',
    desc: 'Disparate impact analysis, approval rates by protected class, ECOA/FHA findings.',
    icon: BarChart3,
    color: 'bg-blue-500',
  },
  {
    type: 'compliance',
    label: 'Compliance Report',
    desc: 'HMDA regulatory compliance checklist, data quality, required field coverage.',
    icon: Shield,
    color: 'bg-green-500',
  },
  {
    type: 'risk',
    label: 'Risk Report',
    desc: 'Credit risk analysis, denial reasons, income/DTI distribution analysis.',
    icon: TrendingUp,
    color: 'bg-amber-500',
  },
  {
    type: 'executive',
    label: 'Executive Summary',
    desc: 'C-suite overview: portfolio performance, fairness KPIs, key recommendations.',
    icon: Users,
    color: 'bg-purple-500',
  },
]

export default function ReportsPage() {
  const { selectedId, getSelected } = useDatasetStore()
  const selected = getSelected()
  const [selectedFormat, setSelectedFormat] = useState<'pdf' | 'json'>('pdf')
  const [generatingType, setGeneratingType] = useState<string | null>(null)

  const { data: recentReports = [] } = useQuery<ReportRecord[]>({
    queryKey: ['reports', selectedId],
    queryFn: async () => [],  // No list endpoint — return empty
    enabled: false,
  })

  const generateMutation = useMutation({
    mutationFn: async ({ reportType, format }: { reportType: string; format: string }) => {
      if (!selectedId) throw new Error('No dataset selected')
      // Use axios api instance so VITE_API_URL is respected (fixes local dev port mismatch)
      const resp = await api.post(
        `/reports/${reportType}?format=${format}`,
        { dataset_id: selectedId },
        { responseType: 'blob' }
      )
      const blob = new Blob([resp.data], {
        type: format === 'pdf' ? 'application/pdf' : 'application/json'
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${reportType}_report_${selectedId?.slice(0, 8)}.${format}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      return { reportType, format }
    },
    onSuccess: (data, vars) => {
      toast.success(`${vars.reportType} report downloaded!`)
    },
    onError: (err: any) => {
      const msg = err.message || err.response?.data?.detail || 'Report generation failed'
      toast.error(msg)
      setGeneratingType(null)
    },
    onSettled: () => setGeneratingType(null),
  })

  const handleGenerate = (reportType: string) => {
    setGeneratingType(reportType)
    generateMutation.mutate({ reportType, format: selectedFormat })
  }

  const handleDownload = async (report: ReportRecord) => {
    const reportId = report.report_id || report.id
    if (!reportId) return
    try {
      const res = await api.get(`/reports/download/${reportId}`, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `${report.report_type}_report.${report.format}`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Download failed')
    }
  }

  function formatBytes(bytes?: number) {
    if (!bytes) return '—'
    if (bytes < 1024) return bytes + ' B'
    return (bytes / 1024).toFixed(1) + ' KB'
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Compliance Reports</h1>
        <p className="text-gray-500 mt-1">Generate and download PDF/JSON reports for regulators, auditors, and executives.</p>
      </div>

      {!selectedId && (
        <div className="card p-8 text-center">
          <Info className="w-10 h-10 text-blue-400 mx-auto mb-3" />
          <p className="text-gray-600">Select a dataset from the top bar to generate reports.</p>
        </div>
      )}

      {/* Format selector */}
      {selectedId && (
        <div className="flex items-center gap-4">
          <span className="text-sm font-medium text-gray-700">Output format:</span>
          {(['pdf', 'json'] as const).map(f => (
            <button
              key={f}
              onClick={() => setSelectedFormat(f)}
              className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                selectedFormat === f ? 'bg-navy-900 text-white border-navy-900' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
              }`}
            >
              {f.toUpperCase()}
            </button>
          ))}
          <span className="text-xs text-gray-400">Dataset: {selected?.filename}</span>
        </div>
      )}

      {/* Report cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {REPORT_TYPES.map(({ type, label, desc, icon: Icon, color }) => (
          <div key={type} className="card p-5">
            <div className="flex items-start gap-4">
              <div className={`w-10 h-10 ${color} rounded-xl flex items-center justify-center flex-shrink-0`}>
                <Icon className="w-5 h-5 text-white" />
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-gray-900 mb-1">{label}</h3>
                <p className="text-sm text-gray-500 leading-relaxed mb-4">{desc}</p>
                <button
                  onClick={() => handleGenerate(type)}
                  disabled={!selectedId || generatingType === type}
                  className="btn-primary flex items-center gap-2 text-sm py-2"
                >
                  {generatingType === type
                    ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Generating…</>
                    : <><FileText className="w-3.5 h-3.5" /> Generate {selectedFormat.toUpperCase()}</>
                  }
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Recent reports */}
      <div>
        <h2 className="text-lg font-semibold text-gray-800 mb-3">
          Recent Reports {selectedId && `— ${selected?.filename}`}
        </h2>
        {recentReports.length === 0 ? (
          <div className="card p-8 text-center text-gray-400">
            <FileText className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p>No reports generated yet. Use the buttons above to create your first report.</p>
          </div>
        ) : (
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Report</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Dataset</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Format</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600">Size</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Generated</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {recentReports.map((r, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <CheckCircle className="w-4 h-4 text-green-500" />
                        <span className="font-medium capitalize text-gray-900">{r.report_type}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs truncate max-w-32">{r.dataset_filename}</td>
                    <td className="px-4 py-3">
                      <span className="badge-blue uppercase">{r.format}</span>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-500 text-xs">{formatBytes(r.file_size)}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {safeFormatDistance(r.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleDownload(r)}
                        className="flex items-center gap-1 text-xs text-navy-900 hover:text-navy-700 font-medium"
                      >
                        <Download className="w-3.5 h-3.5" /> Download
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
