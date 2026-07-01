/** Safe date formatting utilities */

export function safeFormatDistance(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return '—'
    const now = Date.now()
    const diff = now - d.getTime()
    if (diff < 5000)  return 'just now'
    if (diff < 60000) return `${Math.floor(diff / 1000)}s ago`
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
    if (diff < 2592000000) return `${Math.floor(diff / 86400000)}d ago`
    return `${Math.floor(diff / 2592000000)}mo ago`
  } catch {
    return '—'
  }
}

export function safeDate(dateStr: string | null | undefined): Date | null {
  if (!dateStr) return null
  try {
    const d = new Date(dateStr)
    return isNaN(d.getTime()) ? null : d
  } catch {
    return null
  }
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return '—'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(2) + ' MB'
}
