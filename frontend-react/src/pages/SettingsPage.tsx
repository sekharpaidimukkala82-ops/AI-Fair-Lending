import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import toast from 'react-hot-toast'
import { Settings, Save, Loader2, Key, Brain, CheckCircle, RefreshCw, Eye, EyeOff } from 'lucide-react'

interface AIConfig {
  provider: string
  model: string
  has_api_key: boolean
  available_providers: string[]
  available_models: Record<string, string[]>
  temperature?: number
  max_tokens?: number
}

const PROVIDER_LABELS: Record<string, string> = {
  gemini: 'Google Gemini',
  openai: 'OpenAI (GPT)',
  groq:   '⚡ Groq — FREE',
}

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [showKey, setShowKey] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [provider, setProvider] = useState('gemini')
  const [model, setModel] = useState('gemini-2.0-flash')
  const [temperature, setTemperature] = useState(0.3)
  const [maxTokens, setMaxTokens] = useState(2048)

  const { data: config, isLoading } = useQuery<AIConfig>({
    queryKey: ['ai-config'],
    queryFn: async () => {
      const res = await api.get('/ai/status')
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
    if (config) {
      setProvider(config.provider)
      setModel(config.model)
      setTemperature(config.temperature ?? 0.3)
      setMaxTokens(config.max_tokens ?? 2048)
    }
  }, [config])

  const saveMutation = useMutation({
    mutationFn: async (data: { provider: string; model: string; api_key?: string; temperature?: number; max_tokens?: number }) => {
      const res = await api.post('/ai/config', {
        provider: data.provider,
        api_key: data.api_key,
        model: data.model,
        set_active: true,
      })
      return res.data
    },
    onSuccess: () => {
      toast.success('AI configuration saved')
      queryClient.invalidateQueries({ queryKey: ['ai-config'] })
      setApiKey('')
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Save failed'),
  })

  const testMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post('/ai/test', { provider, model })
      return res.data
    },
    onSuccess: (data) => toast.success(data.response || 'AI connection test passed!'),
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Connection test failed'),
  })

  const handleSave = () => {
    const payload: any = { provider, model, temperature, max_tokens: maxTokens }
    if (apiKey.trim()) payload.api_key = apiKey.trim()
    saveMutation.mutate(payload)
  }

  const modelsForProvider = config?.available_models?.[provider] || [model]

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">AI Settings</h1>
        <p className="text-gray-500 mt-1">Configure AI provider, model, and API credentials.</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
        </div>
      ) : (
        <div className="space-y-5">
          {/* Current status */}
          <div className={`card p-4 flex items-center gap-3 ${config?.has_api_key ? 'border-green-200 bg-green-50/30' : 'border-amber-200 bg-amber-50/30'}`}>
            {config?.has_api_key
              ? <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
              : <Key className="w-5 h-5 text-amber-600 flex-shrink-0" />
            }
            <div>
              <p className="text-sm font-medium text-gray-800">
                {config?.has_api_key ? 'API key configured' : 'No API key set'}
              </p>
              <p className="text-xs text-gray-500">
                Current: {PROVIDER_LABELS[config?.provider || ''] || config?.provider} · {config?.model}
              </p>
            </div>
          </div>

          {/* Provider */}
          <div className="card p-5">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Brain className="w-4 h-4 text-purple-600" /> AI Provider
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
                <select
                  value={provider}
                  onChange={e => {
                    setProvider(e.target.value)
                    const models = config?.available_models?.[e.target.value] || []
                    if (models.length > 0) setModel(models[0])
                  }}
                  className="input"
                >
                  {(config?.available_providers || ['gemini', 'openai', 'groq']).map(p => (
                    <option key={p} value={p}>
                      {p === 'gemini' ? 'Google Gemini' : p === 'openai' ? 'OpenAI (GPT)' : p === 'groq' ? '⚡ Groq — FREE (LLaMA / Mixtral)' : p}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                <select value={model} onChange={e => setModel(e.target.value)} className="input">
                  {modelsForProvider.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
            </div>
          </div>

          {/* API Key */}
          <div className="card p-5">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Key className="w-4 h-4 text-amber-600" /> API Key
            </h3>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {PROVIDER_LABELS[provider] || provider} API Key
              </label>
              <div className="relative">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder={config?.has_api_key ? '••••••• (leave blank to keep current)' : 'Enter your API key…'}
                  className="input pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
                >
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-xs text-gray-400 mt-1">
                {provider === 'gemini'  && 'Get your key at aistudio.google.com/app/apikey (enable billing for quota)'}
                {provider === 'openai'  && 'Get your key at platform.openai.com/api-keys (requires $5 minimum credit)'}
                {provider === 'groq'    && '⚡ FREE — Get your key at console.groq.com/keys — no billing required!'}
              </p>
            </div>
          </div>

          {/* Generation parameters */}
          <div className="card p-5">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Settings className="w-4 h-4 text-gray-600" /> Generation Parameters
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Temperature <span className="text-gray-400 font-normal">({temperature})</span>
                </label>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={temperature}
                  onChange={e => setTemperature(Number(e.target.value))}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                  <span>Precise (0)</span>
                  <span>Creative (1)</span>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Max Tokens</label>
                <select
                  value={maxTokens}
                  onChange={e => setMaxTokens(Number(e.target.value))}
                  className="input"
                >
                  {[512, 1024, 2048, 4096, 8192].map(t => (
                    <option key={t} value={t}>{t.toLocaleString()} tokens</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <button
              onClick={handleSave}
              disabled={saveMutation.isPending}
              className="btn-primary flex items-center gap-2"
            >
              {saveMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save Configuration
            </button>
            <button
              onClick={() => testMutation.mutate()}
              disabled={testMutation.isPending}
              className="btn-secondary flex items-center gap-2"
            >
              {testMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              Test Connection
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
