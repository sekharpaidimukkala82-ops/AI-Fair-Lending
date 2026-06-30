import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api/v1`
  : '/api/v1'

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Handle 401 — redirect to login
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api

// ── Cases ─────────────────────────────────────────────────────────────────────
export interface Case {
  id: string
  dataset_id: string
  audit_id?: string
  title: string
  description?: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  status: 'open' | 'investigating' | 'resolved' | 'closed'
  assigned_to?: string
  created_by?: string
  fairness_score?: number
  bias_indicators?: string[]
  remediation_notes?: string
  resolution_notes?: string
  resolved_at?: string
  created_at: string
  updated_at?: string
}

export interface CaseComment {
  id: string; case_id: string; user_id?: string; content: string; created_at: string
}

export const casesApi = {
  list: (params?: { dataset_id?: string; status_filter?: string; severity?: string }) =>
    api.get<Case[]>('/cases', { params }).then(r => r.data),
  get: (id: string) => api.get<Case>(`/cases/${id}`).then(r => r.data),
  create: (payload: Partial<Case>) => api.post<Case>('/cases', payload).then(r => r.data),
  update: (id: string, payload: Partial<Case>) => api.patch<Case>(`/cases/${id}`, payload).then(r => r.data),
  delete: (id: string) => api.delete(`/cases/${id}`),
  comments: (id: string) => api.get<CaseComment[]>(`/cases/${id}/comments`).then(r => r.data),
  addComment: (id: string, content: string) =>
    api.post<CaseComment>(`/cases/${id}/comments`, { content }).then(r => r.data),
}

// ── Advanced Fairness ─────────────────────────────────────────────────────────
export const advancedFairnessApi = {
  fullAnalysis: (payload: { dataset_id: string; outcome_col?: string; protected_cols?: string[] }) =>
    api.post('/fairness-advanced/full-analysis', payload).then(r => r.data),
  equalizedOdds: (payload: object) => api.post('/fairness-advanced/equalized-odds', payload).then(r => r.data),
  calibration: (payload: object) => api.post('/fairness-advanced/calibration', payload).then(r => r.data),
  intersectional: (payload: object) => api.post('/fairness-advanced/intersectional', payload).then(r => r.data),
  denialLetter: (payload: object) => api.post('/fairness-advanced/denial-letter', payload).then(r => r.data),
  lineage: (datasetId: string) => api.get(`/fairness-advanced/lineage/${datasetId}`).then(r => r.data),
  scheduleAudit: (payload: object) => api.post('/fairness-advanced/schedule-audit', payload).then(r => r.data),
  scheduledAudits: () => api.get('/fairness-advanced/scheduled-audits').then(r => r.data),
}

// ── Compliance ────────────────────────────────────────────────────────────────
export const complianceApi = {
  validateHMDA: (datasetId: string) =>
    api.post(`/compliance/validate-hmda/${datasetId}`).then(r => r.data),
  craAnalysis: (datasetId: string) =>
    api.post(`/compliance/cra-analysis/${datasetId}`).then(r => r.data),
  examExport: (datasetId: string) =>
    api.post(`/compliance/exam-export/${datasetId}`, {}, { responseType: 'blob' }),
  auditTrail: (limit = 100) =>
    api.get('/compliance/audit-trail', { params: { limit } }).then(r => r.data),
}
