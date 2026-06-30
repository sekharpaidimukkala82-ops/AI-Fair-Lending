import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ShieldAlert, Plus, MessageSquare, ChevronRight, User,
  CheckCircle2, Clock, Search, AlertTriangle, X, Send
} from 'lucide-react'
import { casesApi, type Case, type CaseComment } from '../lib/api'
import { Alert, Spinner, EmptyState, Modal } from '../components/ui'
import { useDataset } from '../hooks/useDataset'
import { useAuth } from '../hooks/useAuth'
import clsx from 'clsx'

const SEVERITY_STYLES: Record<string, string> = {
  low:      'badge bg-gray-500/15 text-gray-400',
  medium:   'badge bg-warning/15 text-warning',
  high:     'badge bg-orange-500/15 text-orange-400',
  critical: 'badge bg-danger/15 text-danger',
}
const STATUS_STYLES: Record<string, string> = {
  open:          'badge-danger',
  investigating: 'badge-warning',
  resolved:      'badge-success',
  closed:        'badge-muted',
}
const STATUS_ICON: Record<string, React.ReactNode> = {
  open:          <AlertTriangle className="w-3 h-3" />,
  investigating: <Clock className="w-3 h-3" />,
  resolved:      <CheckCircle2 className="w-3 h-3" />,
  closed:        <X className="w-3 h-3" />,
}

function CaseCard({ c, onClick }: { c: Case; onClick: () => void }) {
  return (
    <div onClick={onClick} className="card p-4 cursor-pointer hover:border-white/15 transition-colors space-y-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-gray-200 leading-snug flex-1">{c.title}</p>
        <span className={SEVERITY_STYLES[c.severity]}>{c.severity}</span>
      </div>
      {c.description && (
        <p className="text-xs text-gray-500 line-clamp-2">{c.description}</p>
      )}
      <div className="flex items-center gap-3 pt-1">
        <span className={STATUS_STYLES[c.status] + ' flex items-center gap-1'}>
          {STATUS_ICON[c.status]} {c.status}
        </span>
        {c.fairness_score != null && (
          <span className="text-xs text-gray-500">Score: {(c.fairness_score * 100).toFixed(0)}%</span>
        )}
        <span className="text-xs text-gray-600 ml-auto">
          {new Date(c.created_at).toLocaleDateString()}
        </span>
      </div>
      {c.bias_indicators && c.bias_indicators.length > 0 && (
        <p className="text-xs text-danger/70 truncate">{c.bias_indicators[0]}</p>
      )}
    </div>
  )
}

function CommentTimeline({ caseId }: { caseId: string }) {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [text, setText] = useState('')

  const { data: comments, isLoading } = useQuery({
    queryKey: ['case-comments', caseId],
    queryFn: () => casesApi.comments(caseId),
  })

  const addComment = useMutation({
    mutationFn: (content: string) => casesApi.addComment(caseId, content),
    onSuccess: () => {
      setText('')
      qc.invalidateQueries({ queryKey: ['case-comments', caseId] })
    },
  })

  return (
    <div className="space-y-4">
      <p className="section-header">Activity Timeline</p>
      {isLoading ? <Spinner size="sm" /> : (
        <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
          {(comments || []).map((c: CaseComment) => (
            <div key={c.id} className="flex gap-3">
              <div className="w-6 h-6 rounded-full bg-surface-4 flex items-center justify-center shrink-0 mt-0.5">
                <User className="w-3 h-3 text-gray-500" />
              </div>
              <div className="flex-1 bg-surface-3 rounded-lg px-3 py-2">
                <div className="flex justify-between text-xs text-gray-500 mb-1">
                  <span>{c.user_id ? c.user_id.slice(0, 8) : 'System'}</span>
                  <span>{new Date(c.created_at).toLocaleString()}</span>
                </div>
                <p className="text-sm text-gray-300">{c.content}</p>
              </div>
            </div>
          ))}
          {!comments?.length && <p className="text-xs text-gray-600 text-center py-4">No activity yet</p>}
        </div>
      )}

      <div className="flex gap-2">
        <input
          className="input flex-1 text-sm py-1.5"
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="Add a comment…"
          onKeyDown={e => { if (e.key === 'Enter' && text.trim()) addComment.mutate(text.trim()) }}
        />
        <button
          onClick={() => text.trim() && addComment.mutate(text.trim())}
          disabled={!text.trim() || addComment.isPending}
          className="btn-primary py-1.5 px-3"
        >
          {addComment.isPending ? <Spinner size="sm" /> : <Send className="w-4 h-4" />}
        </button>
      </div>
    </div>
  )
}

function CaseDetailModal({ c, onClose }: { c: Case; onClose: () => void }) {
  const qc = useQueryClient()
  const [status, setStatus] = useState(c.status)
  const [assigned, setAssigned] = useState(c.assigned_to || '')
  const [remNotes, setRemNotes] = useState(c.remediation_notes || '')
  const [resNotes, setResNotes] = useState(c.resolution_notes || '')

  const update = useMutation({
    mutationFn: (payload: Partial<Case>) => casesApi.update(c.id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cases'] })
    },
  })

  const save = () => update.mutate({ status, assigned_to: assigned || undefined, remediation_notes: remNotes, resolution_notes: resNotes })

  return (
    <Modal open onClose={onClose} title={c.title}>
      <div className="space-y-4">
        <div className="flex gap-3 flex-wrap">
          <span className={SEVERITY_STYLES[c.severity]}>{c.severity}</span>
          {c.fairness_score != null && (
            <span className="badge badge-info">Score: {(c.fairness_score * 100).toFixed(0)}%</span>
          )}
        </div>

        {c.description && <p className="text-sm text-gray-400">{c.description}</p>}

        {c.bias_indicators && c.bias_indicators.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Bias Indicators</p>
            {c.bias_indicators.map((bi, i) => (
              <p key={i} className="text-xs text-danger/80 bg-danger/8 rounded px-2 py-1">{bi}</p>
            ))}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Status</label>
            <select value={status} onChange={e => setStatus(e.target.value as Case['status'])} className="input text-sm">
              <option value="open">Open</option>
              <option value="investigating">Investigating</option>
              <option value="resolved">Resolved</option>
              <option value="closed">Closed</option>
            </select>
          </div>
          <div>
            <label className="label">Assigned To (User ID)</label>
            <input className="input text-sm" value={assigned} onChange={e => setAssigned(e.target.value)} placeholder="user-id" />
          </div>
        </div>

        <div>
          <label className="label">Remediation Notes</label>
          <textarea className="input text-sm resize-none" rows={3} value={remNotes} onChange={e => setRemNotes(e.target.value)} placeholder="Describe remediation steps taken…" />
        </div>

        <div>
          <label className="label">Resolution Notes</label>
          <textarea className="input text-sm resize-none" rows={2} value={resNotes} onChange={e => setResNotes(e.target.value)} placeholder="How was this resolved?" />
        </div>

        <button onClick={save} disabled={update.isPending} className="btn-primary w-full justify-center">
          {update.isPending ? <Spinner size="sm" /> : <CheckCircle2 className="w-4 h-4" />} Save Changes
        </button>

        <div className="border-t border-white/5 pt-4">
          <CommentTimeline caseId={c.id} />
        </div>
      </div>
    </Modal>
  )
}

export default function CasesPage() {
  const { activeDataset } = useDataset()
  const qc = useQueryClient()
  const [selectedCase, setSelectedCase] = useState<Case | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [error, setError] = useState('')
  const [newCase, setNewCase] = useState({ title: '', description: '', severity: 'medium' })

  const { data: cases, isLoading } = useQuery({
    queryKey: ['cases', activeDataset?.file_id, statusFilter],
    queryFn: () => casesApi.list({
      dataset_id: activeDataset?.file_id,
      status_filter: statusFilter || undefined,
    }),
    refetchInterval: 30_000,
  })

  const createMutation = useMutation({
    mutationFn: () => casesApi.create({
      ...newCase,
      dataset_id: activeDataset!.file_id,
      severity: newCase.severity as Case['severity'],
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cases'] })
      setShowCreate(false)
      setNewCase({ title: '', description: '', severity: 'medium' })
    },
    onError: (e: unknown) => setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed'),
  })

  const stats = {
    open: cases?.filter(c => c.status === 'open').length ?? 0,
    investigating: cases?.filter(c => c.status === 'investigating').length ?? 0,
    resolved: cases?.filter(c => c.status === 'resolved').length ?? 0,
    critical: cases?.filter(c => c.severity === 'critical').length ?? 0,
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-white">Case Management</h1>
          <p className="text-gray-500 text-sm mt-1">Track bias findings from detection → remediation → resolution</p>
        </div>
        <button onClick={() => setShowCreate(true)} disabled={!activeDataset} className="btn-primary">
          <Plus className="w-4 h-4" /> New Case
        </button>
      </div>

      {!activeDataset && <Alert type="warning">Select a dataset to view its cases.</Alert>}
      {error && <Alert type="error" onClose={() => setError('')}>{error}</Alert>}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Open', val: stats.open, cls: 'text-danger' },
          { label: 'Investigating', val: stats.investigating, cls: 'text-warning' },
          { label: 'Resolved', val: stats.resolved, cls: 'text-success' },
          { label: 'Critical', val: stats.critical, cls: 'text-orange-400' },
        ].map(s => (
          <div key={s.label} className="stat-card">
            <span className="text-gray-500 text-xs uppercase tracking-wide">{s.label}</span>
            <span className={`text-2xl font-bold ${s.cls}`}>{s.val}</span>
          </div>
        ))}
      </div>

      {/* Filter */}
      <div className="flex gap-2 flex-wrap">
        {['', 'open', 'investigating', 'resolved', 'closed'].map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={clsx('px-3 py-1.5 rounded text-sm transition-colors', statusFilter === s
              ? 'bg-accent text-white' : 'bg-surface-2 border border-white/5 text-gray-400 hover:text-gray-200')}
          >
            {s || 'All'}
          </button>
        ))}
      </div>

      {/* Cases grid */}
      {isLoading ? (
        <div className="flex justify-center py-12"><Spinner /></div>
      ) : cases && cases.length > 0 ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {cases.map(c => (
            <CaseCard key={c.id} c={c} onClick={() => setSelectedCase(c)} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<ShieldAlert className="w-10 h-10" />}
          title="No cases found"
          description="Cases are created automatically when fairness audits detect violations, or manually here"
          action={activeDataset
            ? <button onClick={() => setShowCreate(true)} className="btn-primary mt-2"><Plus className="w-4 h-4" /> Create Case</button>
            : undefined}
        />
      )}

      {/* Create case modal */}
      {showCreate && (
        <Modal open onClose={() => setShowCreate(false)} title="New Case">
          <div className="space-y-4">
            <div>
              <label className="label">Title *</label>
              <input className="input" value={newCase.title} onChange={e => setNewCase(p => ({ ...p, title: e.target.value }))} placeholder="e.g. Disparate impact detected for race attribute" />
            </div>
            <div>
              <label className="label">Description</label>
              <textarea className="input resize-none" rows={3} value={newCase.description} onChange={e => setNewCase(p => ({ ...p, description: e.target.value }))} placeholder="Describe the issue…" />
            </div>
            <div>
              <label className="label">Severity</label>
              <select className="input" value={newCase.severity} onChange={e => setNewCase(p => ({ ...p, severity: e.target.value }))}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <button onClick={() => createMutation.mutate()} disabled={!newCase.title || createMutation.isPending} className="btn-primary w-full justify-center">
              {createMutation.isPending ? <Spinner size="sm" /> : <Plus className="w-4 h-4" />} Create Case
            </button>
          </div>
        </Modal>
      )}

      {/* Case detail modal */}
      {selectedCase && <CaseDetailModal c={selectedCase} onClose={() => setSelectedCase(null)} />}
    </div>
  )
}
