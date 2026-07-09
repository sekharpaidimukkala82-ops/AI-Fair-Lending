import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useDatasetStore, type MLAuditResult } from '../store/datasetStore'
import api from '../lib/api'
import toast from 'react-hot-toast'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { Brain, Loader2, TrendingUp, AlertTriangle, Users, Info, ChevronDown, ChevronUp, Clock, Trash2 } from 'lucide-react'

const COLORS = ['#1a237e','#283593','#303f9f','#3949ab','#3f51b5','#5c6bc0','#7986cb','#9fa8da','#c5cae9','#e8eaf6','#bbdefb','#90caf9']

function MLRunCard({ result, index, total }: { result: MLAuditResult; index: number; total: number }) {
  const [showFeatures, setShowFeatures] = useState(true)
  const featureData = result.feature_importance
    ? Object.entries(result.feature_importance).sort((a,b)=>(b[1] as number)-(a[1] as number)).slice(0,12)
        .map(([name, imp]) => ({ name: name.replace(/_/g,' ').substring(0,20), importance: Math.round((imp as number)*1000)/10 }))
    : []
  const tag = result.n_clusters != null ? 'Clustering' : result.anomaly_count != null ? 'Anomaly' : 'Training'
  return (
    <div className="card border-l-4 border-l-amber-500 space-y-4 p-5">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <span className="bg-amber-500 text-white text-xs px-2.5 py-1 rounded-full font-semibold">Run #{total-index} · {tag}</span>
          <span className="text-xs text-gray-500 flex items-center gap-1"><Clock className="w-3 h-3"/>{new Date(result.timestamp).toLocaleString()}</span>
          <span className="text-xs text-gray-400 truncate max-w-32">{result.dataset_name}</span>
        </div>
        {result.accuracy > 0 && <span className="text-lg font-bold text-green-600">{(result.accuracy*100).toFixed(1)}% accuracy</span>}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        {result.accuracy > 0 && (
          <div className="bg-green-50 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-green-700">{(result.accuracy*100).toFixed(1)}%</div>
            <div className="text-xs text-gray-500 mt-0.5">Model Accuracy</div>
          </div>
        )}
        {result.training_rows > 0 && (
          <div className="bg-blue-50 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-blue-700">{result.training_rows.toLocaleString()}</div>
            <div className="text-xs text-gray-500 mt-0.5">Training Rows</div>
          </div>
        )}
        {result.features_used?.length > 0 && (
          <div className="bg-gray-50 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-gray-700">{result.features_used.length}</div>
            <div className="text-xs text-gray-500 mt-0.5">Features Used</div>
          </div>
        )}
        {result.anomaly_count != null && (
          <div className="bg-red-50 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-red-700">{result.anomaly_count}</div>
            <div className="text-xs text-gray-500 mt-0.5">Anomalies Detected</div>
          </div>
        )}
        {result.anomaly_rate != null && (
          <div className="bg-amber-50 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-amber-700">{(result.anomaly_rate).toFixed(1)}%</div>
            <div className="text-xs text-gray-500 mt-0.5">Anomaly Rate</div>
          </div>
        )}
        {result.n_clusters != null && (
          <div className="bg-purple-50 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-purple-700">{result.n_clusters}</div>
            <div className="text-xs text-gray-500 mt-0.5">Clusters Found</div>
          </div>
        )}
      </div>

      {/* Feature importance */}
      {featureData.length > 0 && (
        <div>
          <button onClick={() => setShowFeatures(!showFeatures)} className="flex items-center gap-2 text-sm font-semibold text-gray-700 w-full">
            <TrendingUp className="w-4 h-4 text-amber-500"/>Feature Importance (Top {featureData.length})
            {showFeatures ? <ChevronUp className="w-3.5 h-3.5 ml-auto"/> : <ChevronDown className="w-3.5 h-3.5 ml-auto"/>}
          </button>
          {showFeatures && (
            <ResponsiveContainer width="100%" height={280} className="mt-2">
              <BarChart data={featureData} layout="vertical" margin={{top:0,right:20,left:100,bottom:0}}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false}/>
                <XAxis type="number" tick={{fontSize:11}} unit="%"/>
                <YAxis dataKey="name" type="category" tick={{fontSize:11}} width={100}/>
                <Tooltip formatter={(v:number) => [`${v}%`,'Importance']}/>
                <Bar dataKey="importance" radius={[0,4,4,0]}>
                  {featureData.map((_,i) => <Cell key={i} fill={COLORS[i%COLORS.length]}/>)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      )}

      {/* Anomaly table */}
      {(result.anomalies?.length ?? 0) > 0 && (
        <div className="max-h-48 overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 sticky top-0">
              <tr>
                <th className="text-left px-3 py-2 font-semibold text-gray-600">Row</th>
                <th className="text-right px-3 py-2 font-semibold text-gray-600">Anomaly Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {result.anomalies!.map((a,i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-3 py-2 text-gray-700">Row {a.index}</td>
                  <td className="px-3 py-2 text-right font-medium text-red-600">{a.score.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Clusters */}
      {result.cluster_sizes && Object.keys(result.cluster_sizes).length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {Object.entries(result.cluster_sizes).map(([cluster, size]) => (
            <div key={cluster} className="bg-purple-50 border border-purple-200 rounded-lg p-3">
              <div className="text-lg font-bold text-purple-700">{(size as number).toLocaleString()}</div>
              <div className="text-xs font-medium text-gray-600">{cluster}</div>
              {result.cluster_profiles?.[cluster] && (
                <div className="mt-1 space-y-0.5">
                  {Object.entries(result.cluster_profiles[cluster]).slice(0,3).map(([k,v]) => (
                    <div key={k} className="text-xs text-gray-500">
                      <span className="font-medium">{k.replace(/_/g,' ')}:</span> {typeof v === 'number' ? (v as number).toFixed(1) : typeof v === 'object' && v !== null ? Object.entries(v as Record<string,number>).map(([sk,sv])=>`${sk}: ${typeof sv==='number'?(sv as number).toFixed(1):sv}`).join(', ') : String(v)}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function MLPage() {
  const { selectedId, getSelected, mlHistory, addMLResult, clearMLHistory } = useDatasetStore()
  const selected = getSelected()
  // Show only the LATEST result per dataset
  const latestResult = selectedId ? (mlHistory[selectedId] ?? [])[0] ?? null : null
  const latestTrain = selectedId ? (mlHistory[selectedId] ?? []).find(r => r.accuracy > 0) ?? null : null

  const trainMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) throw new Error('No dataset selected')
      const res = await api.post('/ml/train', { dataset_id: selectedId })
      return res.data
    },
    onSuccess: (data) => {
      addMLResult({ id:`${selectedId}-train-${Date.now()}`, dataset_id:selectedId!, dataset_name:selected?.filename??selectedId!, timestamp:new Date().toISOString(), accuracy:data.accuracy, training_rows:data.training_rows, features_used:data.features_used??[], feature_importance:data.feature_importance })
      toast.success(`Model trained — ${(data.accuracy*100).toFixed(1)}% accuracy`)
    },
    onError: (err:any) => toast.error(err.response?.data?.detail||'Training failed'),
  })

  const anomalyMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) throw new Error('No dataset selected')
      const res = await api.post('/ml/anomalies', { dataset_id: selectedId })
      return res.data
    },
    onSuccess: (data) => {
      addMLResult({ id:`${selectedId}-anomaly-${Date.now()}`, dataset_id:selectedId!, dataset_name:selected?.filename??selectedId!, timestamp:new Date().toISOString(), accuracy:latestTrain?.accuracy??0, training_rows:latestTrain?.training_rows??0, features_used:latestTrain?.features_used??[], anomaly_count:data.anomaly_count??0, anomaly_rate:data.anomaly_rate??0, anomalies:(data.anomalous_records||[]).slice(0,20).map((rec:any,i:number)=>({index:data.anomaly_indices?.[i]??i, score:rec._anomaly_score??0})) })
      toast.success(`${data.anomaly_count} anomalies detected`)
    },
    onError: (err:any) => toast.error(err.response?.data?.detail||'Anomaly detection failed'),
  })

  const clusterMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) throw new Error('No dataset selected')
      const res = await api.post('/ml/segments', { dataset_id: selectedId })
      return res.data
    },
    onSuccess: (data) => {
      addMLResult({ id:`${selectedId}-cluster-${Date.now()}`, dataset_id:selectedId!, dataset_name:selected?.filename??selectedId!, timestamp:new Date().toISOString(), accuracy:latestTrain?.accuracy??0, training_rows:latestTrain?.training_rows??0, features_used:latestTrain?.features_used??[], n_clusters:data.num_clusters??0, cluster_sizes:data.segment_sizes??{}, cluster_profiles:data.cluster_profiles??{} })
      toast.success(`Clustered into ${data.num_clusters} segments`)
    },
    onError: (err:any) => toast.error(err.response?.data?.detail||'Clustering failed'),
  })

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">ML Engine</h1>
          <p className="text-gray-500 mt-1">Train approval prediction models, detect anomalies, and segment applicants.</p>
        </div>
        {history.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 flex items-center gap-1"><Clock className="w-3.5 h-3.5"/>{history.length} run{history.length>1?'s':''} · persisted</span>
            <button onClick={()=>{if(confirm('Clear ML history for this dataset?'))clearMLHistory(selectedId!)}} className="flex items-center gap-1 text-xs text-red-600 border border-red-200 hover:bg-red-50 px-3 py-1.5 rounded-lg">
              <Trash2 className="w-3.5 h-3.5"/> Clear
            </button>
          </div>
        )}
      </div>

      {!selectedId && (
        <div className="card p-8 text-center"><Info className="w-10 h-10 text-blue-400 mx-auto mb-3"/><p className="text-gray-600">Select a dataset from the top bar to run ML analysis.</p></div>
      )}

      <div className="grid grid-cols-3 gap-4">
        <div className="card p-5">
          <Brain className="w-8 h-8 text-amber-500 mb-3"/>
          <h3 className="font-semibold text-gray-800 mb-1">Approval Model</h3>
          <p className="text-xs text-gray-500 mb-4">Train RandomForest classifier to predict loan approvals and compute feature importance.</p>
          <button onClick={()=>trainMutation.mutate()} disabled={trainMutation.isPending||!selectedId} className="btn-primary w-full flex items-center justify-center gap-2 text-sm">
            {trainMutation.isPending?<Loader2 className="w-4 h-4 animate-spin"/>:<Brain className="w-4 h-4"/>}
            {trainMutation.isPending?'Training…':'Train Model'}
          </button>
        </div>
        <div className="card p-5">
          <AlertTriangle className="w-8 h-8 text-red-500 mb-3"/>
          <h3 className="font-semibold text-gray-800 mb-1">Anomaly Detection</h3>
          <p className="text-xs text-gray-500 mb-4">Isolate outlier applications using Isolation Forest for unusual lending patterns.</p>
          <button onClick={()=>anomalyMutation.mutate()} disabled={anomalyMutation.isPending||!selectedId} className="btn-secondary w-full flex items-center justify-center gap-2 text-sm">
            {anomalyMutation.isPending?<Loader2 className="w-4 h-4 animate-spin"/>:<AlertTriangle className="w-4 h-4"/>}
            {anomalyMutation.isPending?'Detecting…':'Detect Anomalies'}
          </button>
        </div>
        <div className="card p-5">
          <Users className="w-8 h-8 text-purple-500 mb-3"/>
          <h3 className="font-semibold text-gray-800 mb-1">Applicant Clustering</h3>
          <p className="text-xs text-gray-500 mb-4">K-Means segmentation to identify applicant profiles and risk groups.</p>
          <button onClick={()=>clusterMutation.mutate()} disabled={clusterMutation.isPending||!selectedId} className="btn-secondary w-full flex items-center justify-center gap-2 text-sm">
            {clusterMutation.isPending?<Loader2 className="w-4 h-4 animate-spin"/>:<Users className="w-4 h-4"/>}
            {clusterMutation.isPending?'Clustering…':'Cluster Applicants'}
          </button>
        </div>
      </div>

      {latestResult && (
        <div className="space-y-4">
          <p className="text-sm text-gray-500 flex items-center gap-2">
            <Clock className="w-4 h-4"/> Last run: {new Date(latestResult.timestamp).toLocaleString()} · results persist across navigation
          </p>
          <MLRunCard key={latestResult.id} result={latestResult} index={0} total={1}/>
        </div>
      )}
    </div>
  )
}
