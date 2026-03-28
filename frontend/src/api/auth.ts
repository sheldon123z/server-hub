import client from './client'
import type { UserInfo } from '@/types/user'

export const authApi = {
  login: (username: string, password: string) =>
    client.post<{ ok: boolean; user: UserInfo }>('/api/auth/login', { username, password }).then((r) => r.data),

  logout: () => client.post('/api/auth/logout').then((r) => r.data),

  me: () => client.get<UserInfo>('/api/auth/me').then((r) => r.data),

  refresh: () => client.post('/api/auth/refresh').then((r) => r.data),

  changePassword: (old_password: string, new_password: string) =>
    client.post('/api/auth/change-password', { old_password, new_password }).then((r) => r.data),
}
