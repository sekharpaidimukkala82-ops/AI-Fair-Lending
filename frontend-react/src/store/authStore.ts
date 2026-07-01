import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface User {
  id: string
  email: string
  username: string
  full_name: string
  role: string
  institution: string
}

interface AuthStore {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  setAuth: (user: User, token: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      setAuth: (user, token) => {
        try { localStorage.setItem('access_token', token) } catch {}
        set({ user, token, isAuthenticated: true })
      },
      logout: () => {
        try { localStorage.removeItem('access_token') } catch {}
        set({ user: null, token: null, isAuthenticated: false })
      },
    }),
    {
      name: 'fairlend-auth',
      partialize: (s) => ({ user: s.user, token: s.token, isAuthenticated: s.isAuthenticated }),
      // Handle localStorage unavailable (private mode, some mobile browsers)
      storage: {
        getItem: (name) => { try { return JSON.parse(localStorage.getItem(name) || 'null') } catch { return null } },
        setItem: (name, value) => { try { localStorage.setItem(name, JSON.stringify(value)) } catch {} },
        removeItem: (name) => { try { localStorage.removeItem(name) } catch {} },
      },
    }
  )
)
