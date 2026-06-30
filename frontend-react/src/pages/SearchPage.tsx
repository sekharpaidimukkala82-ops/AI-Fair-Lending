import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useDatasetStore } from '../store/datasetStore'
import api from '../lib/api'
import toast from 'react-hot-toast'
import { Search, Loader2, Info, FileText, TrendingUp } from 'lucide-react'

interface SearchResult {
  text: string
  score: number
  metadata: Record<string, string>
  rank: number
}

const EXAMPLE_QUERIES = [
  'High-income applicants denied in urban areas',
  'Female applicants with debt-to-income above 40%',
  'Minority applicants near credit score 620',
  'Manufactured housing loans with high denial rates',
  'Refinance applications from low-income census tracts',
]

export default function SearchPage() {
  const { selectedId, getSelected } = useDatasetStore()
  const selected = getSelected()
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(10)
  const [results, setResults] = useState<SearchResult[]>([])

  const searchMutation = useMutation({
    mutationFn: async (q: string) => {
      const res = await api.post('/search/semantic', {
        query: q,
        top_k: topK,
      })
      return res.data
    },
    onSuccess: (data) => {
      setResults(Array.isArray(data) ? data : (data.results || []))
      if ((Array.isArray(data) ? data : (data.results || [])).length === 0) toast('No results found for this query.')
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Search failed'),
  })

  const handleSearch = () => {
    if (!query.trim()) return
    searchMutation.mutate(query.trim())
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Semantic Search</h1>
        <p className="text-gray-500 mt-1">Natural language vector search across applicant records and lending data.</p>
      </div>

      {!selectedId && (
        <div className="card p-8 text-center">
          <Info className="w-10 h-10 text-blue-400 mx-auto mb-3" />
          <p className="text-gray-600">Select a dataset from the top bar to search.</p>
        </div>
      )}

      {/* Search input */}
      <div className="card p-5">
        <div className="flex gap-3">
          <div className="flex-1">
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="Describe the applicant profile or loan scenario you're looking for…"
              disabled={false}
              className="input text-base py-3"
            />
          </div>
          <select
            value={topK}
            onChange={e => setTopK(Number(e.target.value))}
            className="input w-24"
          >
            {[5, 10, 20, 50].map(k => <option key={k} value={k}>Top {k}</option>)}
          </select>
          <button
            onClick={handleSearch}
            disabled={!query.trim() || searchMutation.isPending}
            className="btn-primary flex items-center gap-2 px-6"
          >
            {searchMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            Search
          </button>
        </div>
        {selectedId && (
          <p className="text-xs text-gray-400 mt-2">
            Searching in: <strong>{selected?.filename}</strong> · {selected?.total_rows?.toLocaleString()} records
          </p>
        )}
      </div>

      {/* Example queries */}
      {results.length === 0 && !searchMutation.isPending && (
        <div>
          <p className="text-sm text-gray-500 font-medium mb-2">Example queries:</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_QUERIES.map(q => (
              <button
                key={q}
                onClick={() => setQuery(q)}
                className="text-xs bg-blue-50 text-blue-700 border border-blue-200 px-3 py-1.5 rounded-lg hover:bg-blue-100 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Loading */}
      {searchMutation.isPending && (
        <div className="card p-8 text-center">
          <Loader2 className="w-8 h-8 animate-spin text-navy-900 mx-auto mb-3" />
          <p className="text-gray-600">Running vector similarity search…</p>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-gray-800">
              {results.length} Results for: <em className="text-navy-900">"{query}"</em>
            </h2>
          </div>
          <div className="space-y-3">
            {results.map((r, i) => (
              <div key={i} className="card p-4 hover:shadow-md transition-shadow">
                <div className="flex items-start gap-3">
                  <div className="w-7 h-7 bg-navy-900 text-white rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0">
                    {r.rank || i + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-gray-400" />
                        <span className="text-xs font-medium text-gray-500">Record</span>
                      </div>
                      <div className="flex items-center gap-1 text-xs text-gray-500">
                        <TrendingUp className="w-3 h-3" />
                        Similarity: <span className="font-semibold text-navy-900">{(r.score * 100).toFixed(1)}%</span>
                      </div>
                    </div>
                    <p className="text-sm text-gray-700 leading-relaxed">{r.text}</p>
                    {r.metadata && Object.keys(r.metadata).length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {Object.entries(r.metadata).slice(0, 6).map(([k, v]) => (
                          <span key={k} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                            <span className="font-medium">{k.replace(/_/g, ' ')}:</span> {String(v).substring(0, 30)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
