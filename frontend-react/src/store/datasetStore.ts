import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface Dataset {
  file_id: string
  filename: string
  original_filename?: string
  status: string
  file_size: number
  total_rows?: number
  total_columns?: number
  mapped_columns?: number
  quality_score?: number
  dataset_type?: string
  uploaded_at?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Array<{ text: string; score: number; metadata?: Record<string, string> }>
  provider?: string
  model?: string
  timestamp: string
}

// ── Audit result types ────────────────────────────────────────────────────────

export interface FairnessAuditResult {
  id: string                    // unique run id
  dataset_id: string
  dataset_name: string
  timestamp: string             // ISO string
  score: number
  disparate_impact_ratios: Record<string, number>
  approval_rates_by_group: Record<string, Record<string, number>>
  bias_indicators: Array<{field: string; group: string; value: number; severity: string; description: string}>
  findings: string[]
  recommendations: string[]
  ai_explanation?: string
}

export interface MLAuditResult {
  id: string
  dataset_id: string
  dataset_name: string
  timestamp: string
  accuracy: number
  training_rows: number
  features_used: string[]
  feature_importance?: Record<string, number>
  anomaly_count?: number
  anomaly_rate?: number
  anomalies?: Array<{index: number; score: number}>
  n_clusters?: number
  cluster_sizes?: Record<string, number>
  cluster_profiles?: Record<string, any>
}

export interface AdvancedAuditResult {
  id: string
  dataset_id: string
  dataset_name: string
  timestamp: string
  tab: string      // 'full' | 'equalized' | 'intersectional'
  result: Record<string, unknown>
}

// ── Store interface ───────────────────────────────────────────────────────────

interface DatasetStore {
  datasets: Dataset[]
  selectedId: string | null
  setDatasets: (datasets: Dataset[]) => void
  setSelected: (id: string | null) => void
  getSelected: () => Dataset | undefined

  // Chat history
  chatMessages: ChatMessage[]
  addChatMessage: (msg: ChatMessage) => void
  updateLastAssistantMessage: (msg: Partial<ChatMessage>) => void
  clearChatMessages: () => void

  // Fairness audit history — keyed by dataset_id, multiple runs per dataset
  fairnessHistory: Record<string, FairnessAuditResult[]>
  addFairnessResult: (result: FairnessAuditResult) => void
  clearFairnessHistory: (dataset_id: string) => void
  clearAllFairnessHistory: () => void

  // ML audit history
  mlHistory: Record<string, MLAuditResult[]>
  addMLResult: (result: MLAuditResult) => void
  clearMLHistory: (dataset_id: string) => void

  // Advanced fairness history
  advancedHistory: Record<string, AdvancedAuditResult[]>
  addAdvancedResult: (result: AdvancedAuditResult) => void
  clearAdvancedHistory: (dataset_id: string) => void
}

// ── Store implementation ──────────────────────────────────────────────────────

export const useDatasetStore = create<DatasetStore>()(
  persist(
    (set, get) => ({
      datasets: [],
      selectedId: null,
      setDatasets: (datasets) => set({ datasets }),
      setSelected: (id) => set({ selectedId: id }),
      getSelected: () => get().datasets.find(d => d.file_id === get().selectedId),

      // ── Chat ──
      chatMessages: [],
      addChatMessage: (msg) => set(state => ({
        chatMessages: [...state.chatMessages, msg],
      })),
      updateLastAssistantMessage: (update) => set(state => {
        const msgs = [...state.chatMessages]
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].role === 'assistant') {
            msgs[i] = { ...msgs[i], ...update }
            break
          }
        }
        return { chatMessages: msgs }
      }),
      clearChatMessages: () => set({ chatMessages: [] }),

      // ── Fairness History ──
      fairnessHistory: {},
      addFairnessResult: (result) => set(state => {
        const existing = state.fairnessHistory[result.dataset_id] ?? []
        // Keep last 10 runs per dataset
        const updated = [result, ...existing].slice(0, 10)
        return { fairnessHistory: { ...state.fairnessHistory, [result.dataset_id]: updated } }
      }),
      clearFairnessHistory: (dataset_id) => set(state => {
        const updated = { ...state.fairnessHistory }
        delete updated[dataset_id]
        return { fairnessHistory: updated }
      }),
      clearAllFairnessHistory: () => set({ fairnessHistory: {} }),

      // ── ML History ──
      mlHistory: {},
      addMLResult: (result) => set(state => {
        const existing = state.mlHistory[result.dataset_id] ?? []
        const updated = [result, ...existing].slice(0, 10)
        return { mlHistory: { ...state.mlHistory, [result.dataset_id]: updated } }
      }),
      clearMLHistory: (dataset_id) => set(state => {
        const updated = { ...state.mlHistory }
        delete updated[dataset_id]
        return { mlHistory: updated }
      }),

      // ── Advanced History ──
      advancedHistory: {},
      addAdvancedResult: (result) => set(state => {
        const existing = state.advancedHistory[result.dataset_id] ?? []
        const updated = [result, ...existing].slice(0, 10)
        return { advancedHistory: { ...state.advancedHistory, [result.dataset_id]: updated } }
      }),
      clearAdvancedHistory: (dataset_id) => set(state => {
        const updated = { ...state.advancedHistory }
        delete updated[dataset_id]
        return { advancedHistory: updated }
      }),
    }),
    {
      name: 'fairlend-store',
      partialize: (state) => ({
        selectedId: state.selectedId,
        chatMessages: state.chatMessages.slice(-100),
        // Persist audit histories — survive page navigation and refresh
        fairnessHistory: state.fairnessHistory,
        mlHistory: state.mlHistory,
        advancedHistory: state.advancedHistory,
      }),
    }
  )
)
