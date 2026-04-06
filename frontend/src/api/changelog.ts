/**
 * 变更日历 API 层
 */

import client from '@/api/client'

export interface ChangeEvent {
  id: number
  timestamp: string
  event_type: 'deploy' | 'config' | 'restart' | 'maintenance' | 'other'
  title: string
  description?: string
  operator: string
  affected_services?: string
  risk_level: 'low' | 'medium' | 'high'
  duration_minutes?: number
}

export interface FreezeWindow {
  id: number
  title: string
  start_time: string
  end_time: string
  reason?: string
  created_by: string
  created_at: string
}

export interface ChangeStats {
  by_type: Record<string, number>
  by_risk: Record<string, number>
  by_day: Record<string, number>
  total: number
}

export const changelogApi = {
  getEvents: (params?: {
    start?: string
    end?: string
    event_type?: string
    operator?: string
    limit?: number
  }) =>
    client.get('/api/changelog/events', { params }).then((r) => r.data as ChangeEvent[]),

  createEvent: (data: Omit<ChangeEvent, 'id'>) =>
    client.post('/api/changelog/events', data).then((r) => r.data),

  deleteEvent: (id: number) =>
    client.delete(`/api/changelog/events/${id}`).then((r) => r.data),

  getFreezeWindows: (activeOnly = false) =>
    client
      .get('/api/changelog/freeze-windows', { params: { active_only: activeOnly } })
      .then((r) => {
        const raw = r.data
        if (Array.isArray(raw)) return raw as FreezeWindow[]
        if (Array.isArray(raw?.items)) return raw.items as FreezeWindow[]
        return [] as FreezeWindow[]
      }),

  createFreezeWindow: (data: { title: string; start_time: string; end_time: string; reason?: string }) =>
    client.post('/api/changelog/freeze-windows', data).then((r) => r.data),

  deleteFreezeWindow: (id: number) =>
    client.delete(`/api/changelog/freeze-windows/${id}`).then((r) => r.data),

  getStats: (params?: { start?: string; end?: string }) =>
    client.get('/api/changelog/stats', { params }).then((r) => r.data as ChangeStats),
}
