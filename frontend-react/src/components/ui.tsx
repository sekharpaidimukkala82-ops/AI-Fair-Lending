/**
 * Shared UI primitives used by P3/P4 pages.
 * Styled to match the existing navy/white design system.
 */
import React, { useEffect } from 'react'
import { X, AlertTriangle, CheckCircle, Info, XCircle, Loader2 } from 'lucide-react'

// ── Spinner ───────────────────────────────────────────────────────────────────
interface SpinnerProps { size?: 'sm' | 'md' | 'lg' }
export function Spinner({ size = 'md' }: SpinnerProps) {
  const cls = size === 'sm' ? 'w-4 h-4' : size === 'lg' ? 'w-8 h-8' : 'w-6 h-6'
  return <Loader2 className={`${cls} animate-spin text-blue-500`} />
}

// ── Alert ─────────────────────────────────────────────────────────────────────
interface AlertProps {
  type?: 'error' | 'warning' | 'success' | 'info'
  children: React.ReactNode
  onClose?: () => void
}
export function Alert({ type = 'info', children, onClose }: AlertProps) {
  const styles = {
    error:   { bg: 'bg-red-50 border-red-200',    text: 'text-red-800',   icon: <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" /> },
    warning: { bg: 'bg-amber-50 border-amber-200', text: 'text-amber-800', icon: <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" /> },
    success: { bg: 'bg-green-50 border-green-200', text: 'text-green-800', icon: <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" /> },
    info:    { bg: 'bg-blue-50 border-blue-200',   text: 'text-blue-800',  icon: <Info className="w-4 h-4 text-blue-500 flex-shrink-0" /> },
  }
  const s = styles[type]
  return (
    <div className={`flex items-start gap-2 rounded-lg border px-4 py-3 text-sm ${s.bg} ${s.text}`}>
      {s.icon}
      <span className="flex-1">{children}</span>
      {onClose && (
        <button onClick={onClose} className="ml-2 opacity-60 hover:opacity-100 flex-shrink-0">
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  )
}

// ── EmptyState ────────────────────────────────────────────────────────────────
interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description?: string
  action?: React.ReactNode
}
export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="card p-12 text-center text-gray-400">
      {icon && <div className="mx-auto mb-3 opacity-40">{icon}</div>}
      <p className="font-medium text-gray-600">{title}</p>
      {description && <p className="text-sm mt-1">{description}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

// ── Modal ─────────────────────────────────────────────────────────────────────
interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  children: React.ReactNode
}
export function Modal({ open, onClose, title, children }: ModalProps) {
  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      {/* Panel */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {/* Header */}
        {title && (
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="w-5 h-5" />
            </button>
          </div>
        )}
        {/* Body */}
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  )
}

// ── StatusPill ────────────────────────────────────────────────────────────────
export function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed:  'bg-green-100 text-green-700',
    processing: 'bg-amber-100 text-amber-700',
    queued:     'bg-blue-100 text-blue-700',
    failed:     'bg-red-100 text-red-700',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${map[status] || 'bg-gray-100 text-gray-600'}`}>
      {status}
    </span>
  )
}

// ── ScoreBadge ────────────────────────────────────────────────────────────────
export function ScoreBadge({ score }: { score: number }) {
  const pct = score > 1 ? score : score * 100
  const cls = pct >= 80 ? 'text-green-600' : pct >= 60 ? 'text-amber-600' : 'text-red-600'
  return <span className={`text-xs font-semibold ${cls}`}>{pct.toFixed(0)}%</span>
}
