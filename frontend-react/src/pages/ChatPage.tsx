import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useDatasetStore, type ChatMessage } from '../store/datasetStore'
import api from '../lib/api'
import { safeFormatDistance } from '../lib/utils'
import toast from 'react-hot-toast'
import { MessageSquare, Send, Loader2, Brain, RefreshCw, ChevronDown, Info, ExternalLink } from 'lucide-react'

interface Message extends ChatMessage {}

interface AIConfig {
  provider: string
  model: string
  available_providers: string[]
  available_models: Record<string, string[]>
}

export default function ChatPage() {
  const { selectedId, getSelected, chatMessages, addChatMessage, updateLastAssistantMessage, clearChatMessages } = useDatasetStore()
  const selected = getSelected()
  const messages = chatMessages
  const [input, setInput] = useState('')
  const [provider, setProvider] = useState('gemini')
  const [model, setModel] = useState('gemini-2.0-flash')
  const [showSources, setShowSources] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Load AI config
  const { data: aiConfig } = useQuery<AIConfig>({
    queryKey: ['ai-config'],
    queryFn: async () => {
      const res = await api.get('/ai/status')
      // Map ai/status response to AIConfig shape
      return {
        provider: res.data.active_provider,
        model: res.data.active_model,
        has_api_key: res.data.gemini_configured || res.data.openai_configured || res.data.groq_configured,
        available_providers: ['gemini', 'openai', 'groq'],
        available_models: {
          gemini: res.data.available_gemini_models || ['gemini-2.0-flash', 'gemini-1.5-flash'],
          openai: res.data.available_openai_models || ['gpt-4o-mini', 'gpt-4o'],
          groq:   res.data.available_groq_models   || ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768'],
        },
      }
    },
  })

  useEffect(() => {
    if (aiConfig) {
      setProvider(aiConfig.provider)
      setModel(aiConfig.model)
    }
  }, [aiConfig])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMutation = useMutation({
    mutationFn: async (question: string) => {
      const res = await api.post('/chat', {
        messages: [{ role: 'user', content: question }],
        session_id: selectedId || 'default',
        dataset_id: selectedId,
        top_k: 10,
        provider,
        model,
      })
      return res.data
    },
    onSuccess: (data) => {
      addChatMessage({
        id: Date.now() + '-a',
        role: 'assistant',
        content: data.answer || 'No response.',
        sources: data.sources || [],
        provider: data.metadata?.provider,
        model: data.metadata?.model,
        timestamp: new Date().toISOString(),
      })
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || 'Chat request failed')
      // remove the optimistic user message on error
      useDatasetStore.setState(state => ({
        chatMessages: state.chatMessages.slice(0, -1)
      }))
    },
  })

  const handleSend = () => {
    if (!input.trim()) return
    const q = input.trim()
    setInput('')
    addChatMessage({
      id: Date.now() + '-u',
      role: 'user',
      content: q,
      timestamp: new Date().toISOString(),
    })
    sendMutation.mutate(q)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const suggestedQuestions = [
    'What is the overall approval rate?',
    'Are there disparate impact concerns for minority applicants?',
    'What are the top reasons for loan denials?',
    'Compare approval rates by race and gender.',
    'Which income ranges have the highest denial rates?',
  ]

  const modelsForProvider = aiConfig?.available_models?.[provider] || [model]

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto" style={{ height: 'calc(100vh - 130px)' }}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Assistant</h1>
          <p className="text-gray-500 text-sm">RAG-powered analysis grounded in your lending data</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={provider}
            onChange={e => { setProvider(e.target.value); setModel((aiConfig?.available_models?.[e.target.value] || [])[0] || '') }}
            className="input text-xs w-36"
          >
            {(aiConfig?.available_providers || ['gemini', 'openai', 'groq']).map(p => (
              <option key={p} value={p}>
                {p === 'gemini' ? 'Gemini' : p === 'openai' ? 'OpenAI' : p === 'groq' ? '⚡ Groq (Free)' : p}
              </option>
            ))}
          </select>
          <select value={model} onChange={e => setModel(e.target.value)} className="input text-xs w-44">
            {modelsForProvider.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <button onClick={() => clearChatMessages()} className="btn-secondary flex items-center gap-1 text-xs">
            <RefreshCw className="w-3.5 h-3.5" /> Clear
          </button>
        </div>
      </div>

      {!selectedId && (
        <div className="card p-6 text-center mb-4">
          <Info className="w-8 h-8 text-blue-400 mx-auto mb-2" />
          <p className="text-gray-600 text-sm">Select a dataset from the top bar to ask questions about your lending data.</p>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-gray-500 font-medium">Suggested questions:</p>
            {suggestedQuestions.map(q => (
              <button
                key={q}
                onClick={() => { setInput(q); }}
                className="block w-full text-left text-sm text-navy-900 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-lg px-4 py-2.5 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {messages.map(msg => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-2xl ${msg.role === 'user' ? 'order-1' : 'order-2'}`}>
              {msg.role === 'assistant' && (
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-6 h-6 bg-navy-900 rounded-full flex items-center justify-center">
                    <Brain className="w-3.5 h-3.5 text-white" />
                  </div>
                  <span className="text-xs text-gray-500">
                    AI Assistant {msg.provider && `· ${msg.provider}/${msg.model}`}
                  </span>
                </div>
              )}
              <div className={`rounded-2xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-navy-900 text-white rounded-tr-sm'
                  : 'bg-white border border-gray-200 text-gray-800 rounded-tl-sm shadow-sm'
              }`}>
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
              </div>

              {/* Sources */}
              {msg.sources && msg.sources.length > 0 && (
                <div className="mt-2">
                  <button
                    onClick={() => setShowSources(showSources === msg.id ? null : msg.id)}
                    className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800"
                  >
                    <ExternalLink className="w-3 h-3" />
                    {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''}
                    <ChevronDown className={`w-3 h-3 transition-transform ${showSources === msg.id ? 'rotate-180' : ''}`} />
                  </button>
                  {showSources === msg.id && (
                    <div className="mt-1 space-y-1">
                      {msg.sources.map((s, i) => (
                        <div key={i} className="text-xs bg-gray-50 border border-gray-200 rounded-lg p-2">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-medium text-gray-600">Source {i + 1}</span>
                            <span className="text-gray-400">Score: {s.score.toFixed(3)}</span>
                          </div>
                          <p className="text-gray-600 line-clamp-3">{s.text}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              <div className="text-xs text-gray-400 mt-1 px-1">
                {safeFormatDistance(typeof msg.timestamp === 'string' ? msg.timestamp : new Date(msg.timestamp).toISOString())}
              </div>
            </div>
          </div>
        ))}

        {sendMutation.isPending && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
              <div className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-navy-900" />
                <span className="text-sm text-gray-500">Thinking…</span>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-200 pt-4">
        <div className="flex items-end gap-3">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={selectedId ? 'Ask about your lending data… (Enter to send)' : 'Select a dataset first…'}
            disabled={!selectedId || sendMutation.isPending}
            rows={2}
            className="flex-1 border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-navy-900 resize-none disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || !selectedId || sendMutation.isPending}
            className="btn-primary p-3 rounded-xl flex-shrink-0"
          >
            {sendMutation.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
          </button>
        </div>
        {selectedId && (
          <p className="text-xs text-gray-400 mt-1.5">
            Querying dataset: <strong>{selected?.filename}</strong> · {selected?.total_rows?.toLocaleString()} rows
          </p>
        )}
      </div>
    </div>
  )
}
