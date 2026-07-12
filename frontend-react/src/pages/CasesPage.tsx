import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ShieldAlert, Plus, AlertTriangle, CheckCircle2, Clock,
  X, Send, ChevronRight, User, Edit2, Trash2
} from 'lucide-react'
import { casesApi, type Case, type CaseComment } from '../lib/api'
import { useDataset } from '../hooks/useDataset'
import api from '../lib/api'
import toast from 'react-hot-toast'

const SEV_COLOR: Record<string, string> = {
  low:      'bg-gray-100 text-gray-600 border-gray-200',
  medium:   'bg-amber-100 text-amber-700 border-amber-200',
  high:     'bg-orange-100 text-orange-700 border-orange-200',
  critical: 'bg-red-100 text-red-700 border-red-200',
}
const STATUS_COLOR: Record<string, string> = {
  open:          'bg-red-100 text-red-700',
  investigating: 'bg-amber-100 text-amber-700',
  remediation:   'bg-blue-100 text-blue-700',
  resolved:      'bg-green-100 text-green-700',
  closed:        'bg-gray-100 text-gray-500',
}
const STATUS_ICON: Record<string, React.ReactNode> = {
  open:          <AlertTriangle className="w-3 h-3" />,
  investigating: <Clock className="w-3 h-3" />,
  remediation:   <ChevronRight className="w-3 h-3" />,
  resolved:      <CheckCircle2 className="w-3 h-3" />,
  closed:        <X className="w-3 h-3" />,
}

// ── Case Detail / Edit Panel ──────────────────────────────────────────────────
function CaseDetail({ c, onClose, onUpdated }: { c: Case; onClose: () => void; onUpdated: () => void }) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(c.title)
  const [description, setDescription] = useState(c.description || '')
  const [status, setStatus] = useState(c.status)
  const [severity, setSeverity] = useState(c.severity)
  const [assignedTo, setAssignedTo] = useState(c.assigned_to || '')
  const [remNotes, setRemNotes] = useState(c.remediation_notes || '')
  const [resNotes, setResNotes] = useState(c.resolution_notes || '')
  const [comment, setComment] = useState('')

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      try { const r = await api.get('/auth/users'); return r.data || [] }
      catch { return [] }
    },
  })
  const { data: comments = [], refetch: refetchComments } = useQuery({
    queryKey: ['case-comments', c.id],
    queryFn: () => casesApi.comments(c.id),
  })

  const updateMutation = useMutation({
    mutationFn: () => casesApi.update(c.id, { title, description, status, severity,
      assigned_to: assignedTo || undefined, remediation_notes: remNotes, resolution_notes: resNotes }),
    onSuccess: () => { setEditing(false); onUpdated(); toast.success('Case updated') },
    onError: () => toast.error('Update failed'),
  })

  const commentMutation = useMutation({
    mutationFn: () => casesApi.addComment(c.id, comment),
    onSuccess: () => { setComment(''); refetchComments() },
  })

  const deleteMutation = useMutation({
    mutationFn: () => casesApi.delete(c.id),
    onSuccess: () => { onClose(); onUpdated(); toast.success('Case deleted') },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-gray-200">
          <div className="flex-1 pr-4">
            {editing ? (
              <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-navy-900"
                value={title} onChange={e => setTitle(e.target.value)} />
            ) : (
              <h2 className="font-semibold text-gray-900 text-lg">{c.title}</h2>
            )}
            <div className="flex items-center gap-2 mt-2">
              <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full border font-medium ${SEV_COLOR[c.severity]}`}>
                {c.severity}
              </span>
              <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full font-medium ${STATUS_COLOR[c.status]}`}>
                {STATUS_ICON[c.status]} {c.status}
              </span>
              {c.fairness_score != null && (
                <span className="text-xs text-gray-500">Score: {c.fairness_score.toFixed(1)}/100</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setEditing(!editing)} className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
              <Edit2 className="w-4 h-4" />
            </button>
            <button onClick={() => { if (confirm('Delete this case?')) deleteMutation.mutate() }} className="p-2 text-red-400 hover:text-red-600 rounded-lg hover:bg-red-50">
              <Trash2 className="w-4 h-4" />
            </button>
            <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="p-5 space-y-5">
          {/* Bias indicators */}
          {c.bias_indicators && c.bias_indicators.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="text-xs font-bold text-red-700 uppercase tracking-wide mb-3 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" /> BIAS INDICATORS THAT TRIGGERED THIS CASE
              </p>
              <div className="space-y-2">
                {c.bias_indicators.slice(0, 8).map((bi: any, i: number) => {
                  const text = typeof bi === 'string' ? bi : `${bi.field || ''} group '${bi.group || ''}': DI ratio ${bi.value || ''} (${bi.severity || ''})`
                  const isCritical = text.toLowerCase().includes('critical')
                  const isHigh = text.toLowerCase().includes('high')
                  return (
                    <div key={i} className={`flex items-start gap-2 rounded-lg px-3 py-2 ${isCritical ? 'bg-red-100 border border-red-200' : isHigh ? 'bg-orange-50 border border-orange-200' : 'bg-amber-50 border border-amber-200'}`}>
                      <AlertTriangle className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${isCritical ? 'text-red-600' : isHigh ? 'text-orange-600' : 'text-amber-600'}`} />
                      <span className={`text-sm font-medium ${isCritical ? 'text-red-800' : isHigh ? 'text-orange-800' : 'text-amber-800'}`}>{text}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Editable fields */}
          {editing ? (
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Title</label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-navy-900"
                  value={title} onChange={e => setTitle(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Investigation Notes</label>
                <textarea rows={3} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900 resize-none"
                  value={description} onChange={e => setDescription(e.target.value)} placeholder="Add investigation context, findings, or notes…" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
                  <select className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none"
                    value={status} onChange={e => setStatus(e.target.value as any)}>
                    <option value="open">Open</option>
                    <option value="investigating">Investigating</option>
                    <option value="remediation">Remediation</option>
                    <option value="resolved">Resolved</option>
                    <option value="closed">Closed</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Severity</label>
                  <select className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none"
                    value={severity} onChange={e => setSeverity(e.target.value as any)}>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Assign To</label>
                {users.length > 0 ? (
                  <select className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none"
                    value={assignedTo} onChange={e => setAssignedTo(e.target.value)}>
                    <option value="">— Unassigned —</option>
                    {users.map((u: any) => <option key={u.id} value={u.id}>{u.full_name || u.username} ({u.role})</option>)}
                  </select>
                ) : (
                  <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none"
                    value={assignedTo} onChange={e => setAssignedTo(e.target.value)} placeholder="User ID or name" />
                )}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Remediation Notes</label>
                <textarea rows={3} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none resize-none"
                  value={remNotes} onChange={e => setRemNotes(e.target.value)} placeholder="Steps taken to address the violation…" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Resolution Notes</label>
                <textarea rows={2} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none resize-none"
                  value={resNotes} onChange={e => setResNotes(e.target.value)} placeholder="How was this resolved?" />
              </div>
              <div className="flex gap-2">
                <button onClick={() => updateMutation.mutate()} disabled={updateMutation.isPending}
                  className="btn-primary flex items-center gap-2 text-sm">
                  {updateMutation.isPending ? 'Saving…' : <><CheckCircle2 className="w-4 h-4"/> Save Changes</>}
                </button>
                <button onClick={() => setEditing(false)} className="px-4 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {c.description && (
                <div className="bg-gray-50 border border-gray-200 rounded-xl p-3">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Case Description</p>
                  <p className="text-sm text-gray-700 leading-relaxed">{c.description}</p>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-gray-400 text-xs">Assigned to:</span>
                  <p className="font-medium text-gray-700">{c.assigned_to || 'Unassigned'}</p></div>
                <div><span className="text-gray-400 text-xs">Created:</span>
                  <p className="font-medium text-gray-700">{new Date(c.created_at).toLocaleDateString()}</p></div>
              </div>
              {c.remediation_notes && (
                <div className="bg-blue-50 rounded-lg p-3">
                  <p className="text-xs font-semibold text-blue-700 mb-1">REMEDIATION NOTES</p>
                  <p className="text-sm text-blue-800">{c.remediation_notes}</p>
                </div>
              )}
              {c.resolution_notes && (
                <div className="bg-green-50 rounded-lg p-3">
                  <p className="text-xs font-semibold text-green-700 mb-1">RESOLUTION</p>
                  <p className="text-sm text-green-800">{c.resolution_notes}</p>
                </div>
              )}
            </div>
          )}

          {/* Comments timeline */}
          <div className="border-t border-gray-100 pt-4">
            <p className="text-sm font-semibold text-gray-700 mb-3">Activity Timeline</p>
            <div className="space-y-3 max-h-48 overflow-y-auto mb-3">
              {(comments as CaseComment[]).map((cm) => (
                <div key={cm.id} className="flex gap-3">
                  <div className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <User className="w-3.5 h-3.5 text-gray-400" />
                  </div>
                  <div className="flex-1 bg-gray-50 rounded-lg px-3 py-2">
                    <div className="flex justify-between text-xs text-gray-400 mb-1">
                      <span>{cm.user_id ? cm.user_id.slice(0, 8) + '…' : 'System'}</span>
                      <span>{new Date(cm.created_at).toLocaleString()}</span>
                    </div>
                    <p className="text-sm text-gray-700">{cm.content}</p>
                  </div>
                </div>
              ))}
              {!comments.length && <p className="text-xs text-gray-400 text-center py-3">No activity yet — add a comment below</p>}
            </div>
            <div className="flex gap-2">
              <input className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                value={comment} onChange={e => setComment(e.target.value)}
                placeholder="Add investigation note or update…"
                onKeyDown={e => { if (e.key === 'Enter' && comment.trim()) commentMutation.mutate() }} />
              <button onClick={() => comment.trim() && commentMutation.mutate()}
                disabled={!comment.trim() || commentMutation.isPending}
                className="btn-primary px-3 py-2">
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function CasesPage() {
  const { activeDataset } = useDataset()
  const qc = useQueryClient()
  const [selected, setSelected] = useState<Case | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [newCase, setNewCase] = useState({ title: '', description: '', severity: 'medium' })

  const { data: cases = [], isLoading } = useQuery({
    queryKey: ['cases', activeDataset?.file_id, statusFilter],
    queryFn: () => casesApi.list({
      dataset_id: activeDataset?.file_id,
      status_filter: statusFilter || undefined,
    }),
    refetchInterval: 15000,  // refresh every 15s to catch new auto-created cases
  })

  const createMutation = useMutation({
    mutationFn: () => casesApi.create({ ...newCase, dataset_id: activeDataset!.file_id, severity: newCase.severity as any }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cases'] }); setShowCreate(false); setNewCase({ title: '', description: '', severity: 'medium' }); toast.success('Case created') },
    onError: () => toast.error('Failed to create case'),
  })

  const stats = {
    open: cases.filter(c => c.status === 'open').length,
    investigating: cases.filter(c => c.status === 'investigating').length,
    resolved: cases.filter(c => c.status === 'resolved').length,
    critical: cases.filter(c => c.severity === 'critical').length,
  }

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Case Management</h1>
          <p className="text-gray-500 mt-1 text-sm">Track fair lending violations from detection → investigation → resolution</p>
        </div>
        <button onClick={() => setShowCreate(true)} disabled={!activeDataset}
          className="btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" /> New Case
        </button>
      </div>

      {!activeDataset && (
        <div className="card p-6 text-center text-gray-400">
          <ShieldAlert className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p>Select a dataset from the top bar to view its cases.</p>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Open', val: stats.open, color: 'text-red-600' },
          { label: 'Investigating', val: stats.investigating, color: 'text-amber-600' },
          { label: 'Resolved', val: stats.resolved, color: 'text-green-600' },
          { label: 'Critical', val: stats.critical, color: 'text-red-700' },
        ].map(s => (
          <div key={s.label} className="card p-4 text-center">
            <div className={`text-3xl font-bold ${s.color}`}>{s.val}</div>
            <div className="text-xs text-gray-500 mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Status filters */}
      <div className="flex gap-2 flex-wrap">
        {['', 'open', 'investigating', 'remediation', 'resolved', 'closed'].map(s => (
          <button key={s} onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              statusFilter === s ? 'bg-navy-900 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
            }`}>
            {s || 'All'} {s && cases.filter(c => c.status === s).length > 0 && `(${cases.filter(c => c.status === s).length})`}
          </button>
        ))}
      </div>

      {/* Cases grid */}
      {isLoading ? (
        <div className="card p-8 text-center text-gray-400">Loading cases…</div>
      ) : cases.length > 0 ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {cases.map(c => (
            <div key={c.id} onClick={() => setSelected(c)}
              className="card p-4 cursor-pointer hover:border-navy-900 hover:shadow-md transition-all space-y-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-semibold text-gray-900 leading-snug flex-1">{c.title}</p>
                <span className={`inline-flex items-center text-xs px-2 py-0.5 rounded-full border font-medium flex-shrink-0 ${SEV_COLOR[c.severity]}`}>
                  {c.severity}
                </span>
              </div>
              {c.description && <p className="text-xs text-gray-500 line-clamp-2">{c.description}</p>}
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[c.status]}`}>
                  {STATUS_ICON[c.status]} {c.status}
                </span>
                {c.fairness_score != null && (
                  <span className="text-xs text-gray-400">Score: {c.fairness_score.toFixed(1)}</span>
                )}
                <span className="text-xs text-gray-400 ml-auto">{new Date(c.created_at).toLocaleDateString()}</span>
              </div>
              {c.assigned_to && (
                <div className="flex items-center gap-1 text-xs text-gray-500">
                  <User className="w-3 h-3" /> {c.assigned_to.slice(0, 8)}…
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="card p-12 text-center text-gray-400">
          <ShieldAlert className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="font-medium mb-1">No cases found</p>
          <p className="text-sm">Cases are auto-created when Fairness Audit detects violations, or create one manually.</p>
          {activeDataset && (
            <button onClick={() => setShowCreate(true)} className="btn-primary mt-4 text-sm">
              <Plus className="w-4 h-4" /> Create Case
            </button>
          )}
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">New Case</h2>
              <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5"/></button>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Title *</label>
              <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900"
                value={newCase.title} onChange={e => setNewCase(p => ({...p, title: e.target.value}))}
                placeholder="e.g. Race disparate impact detected — needs investigation" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
              <textarea rows={3} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none resize-none"
                value={newCase.description} onChange={e => setNewCase(p => ({...p, description: e.target.value}))}
                placeholder="Describe the issue found…" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Severity</label>
              <select className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none"
                value={newCase.severity} onChange={e => setNewCase(p => ({...p, severity: e.target.value}))}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <button onClick={() => createMutation.mutate()} disabled={!newCase.title || !activeDataset || createMutation.isPending}
              className="btn-primary w-full flex items-center justify-center gap-2">
              {createMutation.isPending ? 'Creating…' : <><Plus className="w-4 h-4"/> Create Case</>}
            </button>
          </div>
        </div>
      )}

      {/* Case detail */}
      {selected && (
        <CaseDetail c={selected} onClose={() => setSelected(null)}
          onUpdated={() => { qc.invalidateQueries({ queryKey: ['cases'] }); setSelected(null) }} />
      )}
    </div>
  )
}
