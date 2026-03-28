import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/authStore'

export function useAuth() {
  const { setUser, setLoading } = useAuthStore()

  const query = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: authApi.me,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  useEffect(() => {
    if (query.data) {
      setUser(query.data)
    } else if (query.isError) {
      // Only clear user on auth errors, not transient network failures
      const status = (query.error as any)?.response?.status
      if (status === 401 || status === 403) setUser(null)
    }
    if (!query.isLoading) {
      setLoading(false)
    }
  }, [query.data, query.isError, query.isLoading, query.error, setUser, setLoading])

  // 定时刷新 token — only when authenticated
  useEffect(() => {
    if (!query.data) return
    const interval = setInterval(() => {
      authApi.refresh().catch(() => {})
    }, 20 * 60 * 1000)
    return () => clearInterval(interval)
  }, [query.data])

  return query
}
