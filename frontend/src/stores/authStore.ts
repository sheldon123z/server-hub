import { create } from 'zustand'
import type { UserInfo } from '@/types/user'

interface AuthState {
  user: UserInfo | null
  isLoading: boolean
  setUser: (user: UserInfo | null) => void
  setLoading: (loading: boolean) => void
  isAdmin: () => boolean
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isLoading: true,
  setUser: (user) => set({ user, isLoading: false }),
  setLoading: (isLoading) => set({ isLoading }),
  isAdmin: () => get().user?.role === 'admin',
}))
