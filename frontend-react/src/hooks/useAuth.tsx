/**
 * useAuth hook — wraps useAuthStore for compatibility with P3/P4 pages.
 * P3/P4 pages use `useAuth()` returning `{ user, loading }`.
 */
import { useAuthStore } from '../store/authStore'

export function useAuth() {
  const { user, isAuthenticated } = useAuthStore()
  return {
    user,
    loading: false,          // authStore is synchronous; no async loading state
    isAuthenticated,
  }
}
