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
  timestamp: string  // ISO string — serializable for persistence
}

interface DatasetStore {
  datasets: Dataset[]
  selectedId: string | null
  setDatasets: (datasets: Dataset[]) => void
  setSelected: (id: string | null) => void
  getSelected: () => Dataset | undefined
  // Chat history — persisted across navigation
  chatMessages: ChatMessage[]
  addChatMessage: (msg: ChatMessage) => void
  updateLastAssistantMessage: (msg: Partial<ChatMessage>) => void
  clearChatMessages: () => void
}

export const useDatasetStore = create<DatasetStore>()(
  persist(
    (set, get) => ({
      datasets: [],
      selectedId: null,
      setDatasets: (datasets) => set({ datasets }),
      setSelected: (id) => set({ selectedId: id }),
      getSelected: () => get().datasets.find(d => d.file_id === get().selectedId),
      chatMessages: [],
      addChatMessage: (msg) => set(state => ({
        chatMessages: [...state.chatMessages, msg],
      })),
      updateLastAssistantMessage: (update) => set(state => {
        const msgs = [...state.chatMessages]
        // find last assistant message and update it
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].role === 'assistant') {
            msgs[i] = { ...msgs[i], ...update }
            break
          }
        }
        return { chatMessages: msgs }
      }),
      clearChatMessages: () => set({ chatMessages: [] }),
    }),
    {
      name: 'fairlend-store',
      // Only persist selectedId and chatMessages — datasets are fetched fresh
      partialize: (state) => ({
        selectedId: state.selectedId,
        chatMessages: state.chatMessages.slice(-100), // keep last 100 messages
      }),
    }
  )
)
