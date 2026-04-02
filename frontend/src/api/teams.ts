/**
 * Teams API 客户端 — 团队多 Agent 协作
 * API 前缀: /api/agents/teams
 */

import client from '@/api/client'
import type {
  Team,
  TeamCreateRequest,
  TeamUpdateRequest,
  TeamMember,
  MemberCreateRequest,
  MemberUpdateRequest,
  TeamExecution,
  TeamTemplate,
  TeamMessage,
} from '@/types/team'

/* ─── Team CRUD ─── */

export const teamsApi = {
  list: (params?: { enabled_only?: boolean }) =>
    client.get<Team[]>('/api/agents/teams', { params }).then((r) => r.data),

  get: (teamId: string) =>
    client.get<Team & { members: TeamMember[] }>(`/api/agents/teams/${teamId}`).then((r) => r.data),

  create: (data: TeamCreateRequest) =>
    client.post<Team>('/api/agents/teams', data).then((r) => r.data),

  update: (teamId: string, data: TeamUpdateRequest) =>
    client.put<Team>(`/api/agents/teams/${teamId}`, data).then((r) => r.data),

  delete: (teamId: string) =>
    client.delete(`/api/agents/teams/${teamId}`).then((r) => r.data),
}

/* ─── Member CRUD ─── */

export const membersApi = {
  add: (teamId: string, data: MemberCreateRequest) =>
    client.post<TeamMember>(`/api/agents/teams/${teamId}/members`, data).then((r) => r.data),

  update: (memberId: string, data: MemberUpdateRequest) =>
    client.put<TeamMember>(`/api/agents/teams/members/${memberId}`, data).then((r) => r.data),

  remove: (memberId: string) =>
    client.delete(`/api/agents/teams/members/${memberId}`).then((r) => r.data),
}

/* ─── Execution ─── */

export const executionsApi = {
  list: (teamId: string, params?: { limit?: number }) =>
    client.get<TeamExecution[]>(`/api/agents/teams/${teamId}/executions`, { params }).then((r) => r.data),

  get: (executionId: string) =>
    client.get<TeamExecution & { messages: TeamMessage[] }>(`/api/agents/teams/executions/${executionId}`).then((r) => r.data),

  cancel: (executionId: string) =>
    client.post(`/api/agents/teams/executions/${executionId}/cancel`).then((r) => r.data),

  /** SSE 执行端点 URL (用于 EventSource) */
  executeUrl: (teamId: string) => `/api/agents/teams/${teamId}/execute`,
}

/* ─── Templates ─── */

export const templatesApi = {
  list: () =>
    client.get<TeamTemplate[]>('/api/agents/teams/templates').then((r) => r.data),

  instantiate: (templateId: string, overrides?: Partial<TeamCreateRequest>) =>
    client.post<Team>(`/api/agents/teams/templates/${templateId}/instantiate`, overrides ?? {}).then((r) => r.data),
}
