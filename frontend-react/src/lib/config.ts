// Base URL for the backend API
// In production (Vercel): set VITE_API_URL to your Railway backend URL
// In development: falls back to localhost via Vite proxy
export const API_BASE = import.meta.env.VITE_API_URL || ''

export const fetchFromAPI = (path: string, options?: RequestInit) =>
  fetch(`${API_BASE}${path}`, options).then(r => r.json())
