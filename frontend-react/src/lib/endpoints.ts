/**
 * Centralized API endpoint mapping.
 * All React pages use these — update here if the backend routes change.
 */

export const API = {
  // Upload
  uploadDataset:    '/upload/dataset',
  uploadDocument:   '/upload/document',
  uploadList:       '/upload/list',
  uploadStatus:     (id: string) => `/upload/status/${id}`,

  // Fairness  — maps React names to actual backend routes
  fairnessAudit:    '/fairness/audit',          // POST {dataset_id}
  fairnessExplain:  '/fairness/ai-explain',     // POST {dataset_id}
  fairnessDetect:   (id: string) => `/fairness/detect-columns/${id}`,
  fairnessScore:    (id: string) => `/fairness/score/${id}`,
  fairnessRegister: '/fairness/register-dataset',

  // ML
  mlTrain:          '/ml/train',                // POST {dataset_id}
  mlPredict:        '/ml/predict',              // POST {record}
  mlPredictBatch:   '/ml/predict-batch',        // POST {dataset_id}
  mlAnomalies:      '/ml/anomalies',            // POST {dataset_id}
  mlSegments:       '/ml/segments',             // POST {dataset_id}
  mlExplain:        (id: string) => `/ml/explain/${id}`,
  mlModelInfo:      '/ml/model-info',

  // Chat
  chat:             '/chat',                    // POST {messages, session_id}
  chatHistory:      (id: string) => `/chat/history/${id}`,
  chatClear:        (id: string) => `/chat/session/${id}`,

  // Search
  searchSemantic:   '/search/semantic',         // POST {query, top_k}
  searchApplicants: '/search/similar-applicants',
  searchLoans:      '/search/similar-loans',
  searchPolicy:     '/search/policy',

  // Reports
  reportFairness:   '/reports/fairness',
  reportCompliance: '/reports/compliance',
  reportRisk:       '/reports/risk',
  reportExecutive:  '/reports/executive-summary',

  // AI config
  aiConfig:         '/ai/config',               // POST {provider, api_key, model}
  aiStatus:         '/ai/status',               // GET
  aiTest:           '/ai/test',                 // POST {provider}
  aiClear:          (p: string) => `/ai/config/${p}`,

  // Auth
  authLogin:        '/auth/login',
  authRegister:     '/auth/register',
  authMe:           '/auth/me',
  authLogout:       '/auth/logout',

  // Monitoring
  monitorDashboard: '/monitoring/dashboard',    // Note: no /api/v1 prefix!
  monitorAlerts:    '/monitoring/alerts',
  monitorResolve:   (id: string) => `/monitoring/alerts/${id}/resolve`,
}
