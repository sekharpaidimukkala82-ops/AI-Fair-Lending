import { useState, useCallback, useEffect } from 'react'
import React from 'react'
import { useDropzone } from 'react-dropzone'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useDatasetStore } from '../store/datasetStore'
import { useNavigate } from 'react-router-dom'
import api from '../lib/api'
import { safeFormatDistance } from '../lib/utils'
import toast from 'react-hot-toast'
import {
  Upload, FileText, CheckCircle, XCircle, Clock, Loader2,
  Database, BarChart3, CheckSquare, Wifi, ShieldCheck, ChevronDown, ChevronUp, Rows3, Trash2
} from 'lucide-react'
import { useTaskProgress, type WSEvent } from '../hooks/useWebSocket'

interface UploadRecord {
  file_id: string
  filename: string
  original_filename: string
  file_size: number
  status: 'queued' | 'processing' | 'completed' | 'failed'
  total_rows?: number
  total_columns?: number
  mapped_columns?: number
  quality_score?: number
  duplicates_removed?: number
  dataset_type?: string
  error_message?: string
  uploaded_at: string
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'completed') return <span className="badge-green flex items-center gap-1"><CheckCircle className="w-3 h-3" /> Completed</span>
  if (status === 'failed') return <span className="badge-red flex items-center gap-1"><XCircle className="w-3 h-3" /> Failed</span>
  if (status === 'processing') return <span className="badge-yellow flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Processing</span>
  return <span className="badge-blue flex items-center gap-1"><Clock className="w-3 h-3" /> Queued</span>
}

// ── Live WebSocket progress bar for a single upload ─────────────────────────
function UploadProgressBar({ fileId, filename, onComplete, uploads }: {
  fileId: string
  filename: string
  onComplete: () => void
  uploads: Array<{ file_id: string; status: string }>
}) {
  const [progress, setProgress] = useState(5)
  const [step, setStep] = useState('Queued')
  const [done, setDone] = useState(false)
  const [failed, setFailed] = useState(false)

  // Poll uploads list as fallback when WebSocket isn't available
  useEffect(() => {
    if (done || failed) return
    const match = uploads.find(u => u.file_id === fileId)
    if (match?.status === 'completed') {
      setDone(true)
      setProgress(100)
      setTimeout(onComplete, 1500)
    } else if (match?.status === 'failed') {
      setFailed(true)
    }
  }, [uploads, fileId, done, failed, onComplete])

  useTaskProgress(fileId, {
    onMessage: (evt: WSEvent) => {
      if (evt.progress != null) setProgress(evt.progress as number)
      if (evt.step) setStep(evt.step as string)
      if (evt.event === 'processing.completed') {
        setDone(true)
        setProgress(100)
        setTimeout(onComplete, 1500)
      }
      if (evt.event === 'processing.failed') setFailed(true)
    },
  })

  if (done) return (
    <div className="card p-3 border-green-200 bg-green-50/30 flex items-center gap-2 text-sm text-green-700">
      <CheckCircle className="w-4 h-4" /> {filename} — processing complete!
    </div>
  )

  return (
    <div className={`card p-4 space-y-2 ${failed ? 'border-red-200 bg-red-50/30' : ''}`}>
      <div className="flex items-center gap-2 text-sm">
        {failed ? (
          <><XCircle className="w-4 h-4 text-red-500" /><span className="text-red-600">Processing failed — {filename}</span></>
        ) : (
          <>
            <Loader2 className="w-4 h-4 animate-spin text-navy-900" />
            <span className="font-medium text-gray-700">{filename}</span>
            <span className="ml-auto text-gray-500 text-xs flex items-center gap-1">
              <Wifi className="w-3 h-3 text-green-500" /> {step}
            </span>
          </>
        )}
      </div>
      {!failed && (
        <>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-navy-900 h-2 rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-gray-400">{progress}% complete</p>
        </>
      )}
    </div>
  )
}

export default function UploadPage() {
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<{ name: string; progress: number } | null>(null)
  const [activeWsUploads, setActiveWsUploads] = useState<Array<{ fileId: string; filename: string }>>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const { selectedId, setSelected } = useDatasetStore()
  const navigate = useNavigate()

  const { data: uploads = [], isLoading } = useQuery<UploadRecord[]>({
    queryKey: ['uploads-all'],
    queryFn: async () => {
      const res = await api.get('/upload/list')
      const list: UploadRecord[] = res.data.uploads || []
      // Auto-activate the most recently completed dataset if none is selected
      if (!selectedId) {
        const latest = list.find(u => u.status === 'completed')
        if (latest) setSelected(latest.file_id)
      }
      return list
    },
    refetchInterval: 3000,
  })

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    for (const file of acceptedFiles) {
      if (!file.name.match(/\.(csv|xlsx|xls|json)$/i)) {
        toast.error(`${file.name}: unsupported format (CSV, XLSX, JSON only)`)
        continue
      }
      setUploading(true)
      setUploadProgress({ name: file.name, progress: 0 })
      const formData = new FormData()
      formData.append('file', file)
      try {
        const res = await api.post('/upload/dataset', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          onUploadProgress: (evt) => {
            const pct = Math.round((evt.loaded * 100) / (evt.total || 1))
            setUploadProgress({ name: file.name, progress: pct })
          },
        })
        const fileId = res.data?.file_id
        toast.success(`${file.name} uploaded — processing started`)
        // Start WebSocket progress tracking if we got a file_id
        if (fileId) {
          setActiveWsUploads(prev => [...prev, { fileId, filename: file.name }])
        }
        queryClient.invalidateQueries({ queryKey: ['uploads-all'] })
        queryClient.invalidateQueries({ queryKey: ['datasets'] })
      } catch (err: any) {
        toast.error(err.response?.data?.detail || `Upload failed: ${file.name}`)
      } finally {
        setUploading(false)
        setUploadProgress(null)
      }
    }
  }, [queryClient])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'text/csv': ['.csv'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'], 'application/json': ['.json'] },
    multiple: true,
    disabled: uploading,
  })

  const completedUploads = uploads.filter(u => u.status === 'completed')

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Upload & Process Data</h1>
        <p className="text-gray-500 mt-1">Upload CSV, XLSX, or JSON lending datasets. Auto schema detection, HMDA code mapping, and quality analysis included.</p>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-2xl p-12 text-center transition-all cursor-pointer ${
          isDragActive ? 'border-navy-900 bg-blue-50' : 'border-gray-300 hover:border-navy-900 hover:bg-gray-50'
        } ${uploading ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <input {...getInputProps()} />
        <Upload className="w-12 h-12 text-gray-400 mx-auto mb-4" />
        {isDragActive ? (
          <p className="text-navy-900 font-semibold text-lg">Drop files here…</p>
        ) : (
          <>
            <p className="text-gray-700 font-semibold text-lg mb-1">Drag & drop files here, or click to browse</p>
            <p className="text-gray-400 text-sm">Supports CSV, XLSX, JSON · Multiple files allowed · Max 200 MB</p>
            <p className="text-xs text-gray-400 mt-1 flex items-center justify-center gap-1">
              <Wifi className="w-3 h-3 text-green-500" /> Real-time processing progress via WebSocket
            </p>
          </>
        )}
      </div>

      {/* HTTP upload progress */}
      {uploadProgress && (
        <div className="card p-4">
          <div className="flex items-center gap-3 mb-2">
            <Loader2 className="w-4 h-4 animate-spin text-navy-900" />
            <span className="text-sm font-medium text-gray-700">Uploading {uploadProgress.name}…</span>
            <span className="ml-auto text-sm text-gray-500">{uploadProgress.progress}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div className="bg-navy-900 h-2 rounded-full transition-all" style={{ width: `${uploadProgress.progress}%` }} />
          </div>
        </div>
      )}

      {/* WebSocket live processing progress */}
      {activeWsUploads.map(u => (
        <UploadProgressBar
          key={u.fileId}
          fileId={u.fileId}
          filename={u.filename}
          uploads={uploads}
          onComplete={() => {
            setActiveWsUploads(prev => prev.filter(x => x.fileId !== u.fileId))
            queryClient.invalidateQueries({ queryKey: ['uploads-all'] })
            queryClient.invalidateQueries({ queryKey: ['datasets'] })
            // Auto-activate the newly processed dataset
            setSelected(u.fileId)
            toast.success(`${u.filename} is now active`)
          }}
        />
      ))}

      {/* Datasets table */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-800">All Datasets ({uploads.length})</h2>
          {uploads.length > 0 && (
            <button
              onClick={async () => {
                if (!confirm('Delete all datasets? This cannot be undone.')) return
                try {
                  await api.delete('/upload/all')
                  toast.success('All datasets cleared')
                  queryClient.invalidateQueries({ queryKey: ['uploads-all'] })
                  queryClient.invalidateQueries({ queryKey: ['datasets'] })
                } catch {
                  toast.error('Failed to clear datasets')
                }
              }}
              className="flex items-center gap-1.5 text-xs text-red-600 border border-red-200 hover:bg-red-50 px-3 py-1.5 rounded-lg transition-colors"
            >
              <XCircle className="w-3.5 h-3.5" /> Clear All
            </button>
          )}
        </div>
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
          </div>
        ) : uploads.length === 0 ? (
          <div className="card p-12 text-center text-gray-400">
            <Database className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p>No datasets yet. Upload a file above to get started.</p>
          </div>
        ) : (
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">File</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Status</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600">Rows</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600">Columns</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600">Quality</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Type</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Uploaded</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {uploads.map(u => (
                  <React.Fragment key={u.file_id}><tr className={`hover:bg-gray-50 transition-colors ${selectedId === u.file_id ? 'bg-blue-50' : ''}`}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-gray-400 flex-shrink-0" />
                        <div>
                          <div className="font-medium text-gray-900 truncate max-w-48">{u.filename}</div>
                          <div className="text-xs text-gray-400">{formatBytes(u.file_size)}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={u.status} /></td>
                    <td className="px-4 py-3 text-right text-gray-700">{u.total_rows?.toLocaleString() || '—'}</td>
                    <td className="px-4 py-3 text-right text-gray-700">
                      {u.mapped_columns != null && u.total_columns != null
                        ? `${u.mapped_columns}/${u.total_columns}` : u.total_columns || '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {u.quality_score != null ? (
                        <span className={`font-semibold ${u.quality_score >= 80 ? 'text-green-600' : u.quality_score >= 60 ? 'text-amber-600' : 'text-red-600'}`}>
                          {u.quality_score.toFixed(0)}%
                        </span>
                      ) : '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{u.dataset_type || '—'}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">{safeFormatDistance(u.uploaded_at)}</td>
                    <td className="px-4 py-3">
                      {u.status === 'completed' && (
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => { setSelected(u.file_id); toast.success(`Active dataset: ${u.filename}`) }}
                            className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg font-medium transition-colors w-16 justify-center ${
                              selectedId === u.file_id ? 'bg-navy-900 text-white' : 'bg-blue-100 text-blue-700 hover:bg-blue-200'
                            }`}
                          >
                            <CheckSquare className="w-3 h-3" />
                            {selectedId === u.file_id ? 'Active' : 'Use'}
                          </button>
                          {u.status === 'completed' && (
                            <button
                              onClick={() => { setSelected(u.file_id); navigate('/fairness') }}
                              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg font-medium bg-green-100 text-green-700 hover:bg-green-200 transition-colors"
                              title="Run Fairness Audit"
                            >
                              <ShieldCheck className="w-3 h-3" /> Fairness
                            </button>
                          )}
                          <button
                            onClick={() => setExpandedId(expandedId === u.file_id ? null : u.file_id)}
                            className="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                            title="Dataset details"
                          >
                            {expandedId === u.file_id ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                          </button>
                          <button
                            onClick={async () => {
                              if (!confirm(`Delete "${u.filename}"? This cannot be undone.`)) return
                              try {
                                await api.delete(`/upload/dataset/${u.file_id}`)
                                toast.success(`${u.filename} deleted`)
                                if (selectedId === u.file_id) setSelected(null)
                                queryClient.invalidateQueries({ queryKey: ['uploads-all'] })
                                queryClient.invalidateQueries({ queryKey: ['datasets'] })
                              } catch { toast.error('Failed to delete dataset') }
                            }}
                            className="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg text-red-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                            title="Delete dataset"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}
                      {u.status === 'failed' && (
                        <div className="flex items-center gap-1.5">
                          {u.error_message && (
                            <span className="text-xs text-red-500 truncate max-w-28 block" title={u.error_message}>
                              {u.error_message.substring(0, 35)}…
                            </span>
                          )}
                          <button
                            onClick={async () => {
                              if (!confirm(`Delete "${u.filename}"?`)) return
                              try {
                                await api.delete(`/upload/dataset/${u.file_id}`)
                                toast.success('Deleted')
                                queryClient.invalidateQueries({ queryKey: ['uploads-all'] })
                              } catch { toast.error('Failed to delete') }
                            }}
                            className="flex items-center text-xs px-2 py-1.5 rounded-lg text-red-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                            title="Delete"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                  {/* Expandable detail panel */}
                  {expandedId === u.file_id && u.status === 'completed' && (
                    <tr>
                      <td colSpan={8} className="px-4 pb-4">
                        <div className="bg-gray-50 border border-gray-100 rounded-xl p-4 grid grid-cols-2 sm:grid-cols-4 gap-4">
                          <div className="text-center">
                            <div className="text-2xl font-bold text-navy-900">{u.total_rows?.toLocaleString() ?? '—'}</div>
                            <div className="text-xs text-gray-500 mt-0.5">Total Records</div>
                          </div>
                          <div className="text-center">
                            <div className="text-2xl font-bold text-navy-900">
                              {u.mapped_columns != null && u.total_columns != null ? `${u.mapped_columns}/${u.total_columns}` : u.total_columns ?? '—'}
                            </div>
                            <div className="text-xs text-gray-500 mt-0.5">Columns Mapped</div>
                          </div>
                          <div className="text-center">
                            <div className={`text-2xl font-bold ${u.quality_score != null ? (u.quality_score >= 80 ? 'text-green-600' : u.quality_score >= 60 ? 'text-amber-600' : 'text-red-600') : 'text-gray-400'}`}>
                              {u.quality_score != null ? `${u.quality_score.toFixed(0)}%` : '—'}
                            </div>
                            <div className="text-xs text-gray-500 mt-0.5">Data Quality</div>
                          </div>
                          <div className="text-center">
                            <div className="text-2xl font-bold text-navy-900">{safeFormatDistance(u.uploaded_at)}</div>
                            <div className="text-xs text-gray-500 mt-0.5">Uploaded</div>
                          </div>
                          <div className="col-span-2 sm:col-span-4 flex gap-2 pt-2 border-t border-gray-200">
                            <button onClick={() => { setSelected(u.file_id); navigate('/fairness') }}
                              className="flex items-center gap-1.5 text-xs bg-navy-900 text-white px-4 py-2 rounded-lg hover:bg-navy-800 transition-colors font-medium">
                              <ShieldCheck className="w-3.5 h-3.5" /> Run Fairness Audit
                            </button>
                            <button onClick={() => { setSelected(u.file_id); navigate('/ml') }}
                              className="flex items-center gap-1.5 text-xs bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 transition-colors font-medium">
                              <BarChart3 className="w-3.5 h-3.5" /> ML Engine
                            </button>
                            <button onClick={() => { setSelected(u.file_id); navigate('/search') }}
                              className="flex items-center gap-1.5 text-xs bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors font-medium">
                              <Rows3 className="w-3.5 h-3.5" /> Search Records
                            </button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Stats row */}
      {completedUploads.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <div className="card p-4 text-center">
            <Database className="w-6 h-6 text-blue-600 mx-auto mb-1" />
            <div className="text-2xl font-bold text-gray-900">{completedUploads.length}</div>
            <div className="text-xs text-gray-500">Ready Datasets</div>
          </div>
          <div className="card p-4 text-center">
            <BarChart3 className="w-6 h-6 text-green-600 mx-auto mb-1" />
            <div className="text-2xl font-bold text-gray-900">
              {completedUploads.reduce((sum, u) => sum + (u.total_rows || 0), 0).toLocaleString()}
            </div>
            <div className="text-xs text-gray-500">Total Records</div>
          </div>
          <div className="card p-4 text-center">
            <CheckCircle className="w-6 h-6 text-amber-600 mx-auto mb-1" />
            <div className="text-2xl font-bold text-gray-900">
              {completedUploads.length > 0
                ? (completedUploads.reduce((sum, u) => sum + (u.quality_score || 0), 0) / completedUploads.length).toFixed(0) + '%'
                : '—'}
            </div>
            <div className="text-xs text-gray-500">Avg Quality Score</div>
          </div>
        </div>
      )}
    </div>
  )
}
