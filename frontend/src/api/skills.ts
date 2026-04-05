/**
 * skills.ts - API functions for the skill management system.
 * Covers CRUD, files, evals, market, and versions.
 */

import client from '@/api/client'

// ── Types ──────────────────────────────────────────────

export interface SkillMeta {
  id: string
  name: string
  description: string
  version: string
  enabled: boolean
  owner: string // 'system' | 'shared' | username
  source_type: string
  allowed_tools?: string[]
  allowed_roles?: string[]
  page_contexts?: string[]
  capabilities?: string[]
  compose?: string[]
  install_path?: string
  skill_markdown?: string
  files?: SkillFile[]
}

export interface SkillCreate {
  name: string
  description: string
  owner?: string
  allowed_tools?: string[]
  allowed_roles?: string[]
  page_contexts?: string[]
  capabilities?: string[]
  compose?: string[]
  skill_markdown?: string
}

export interface SkillUpdate {
  name?: string
  description?: string
  owner?: string
  allowed_tools?: string[]
  allowed_roles?: string[]
  page_contexts?: string[]
  capabilities?: string[]
  compose?: string[]
  skill_markdown?: string
}

export interface SkillFile {
  path: string
  size?: number
  modified?: string
}

export interface SkillListItem {
  id: string
  name: string
  description: string
}

export interface EvalCase {
  id: number
  prompt: string
  expected_behavior: string
  assertions: EvalAssertion[]
}

export interface EvalAssertion {
  name: string
  check: string
}

export interface EvalSet {
  skill_name: string
  evals: EvalCase[]
}

export interface EvalRunResult {
  run_id: string
  skill_id: string
  started_at: string
  completed_at?: string
  status: string
  results?: EvalCaseResult[]
  summary?: {
    pass_rate: number
    total: number
    passed: number
    avg_tokens: number
    avg_duration_ms: number
  }
}

export interface EvalCaseResult {
  eval_id: number
  with_skill: EvalSideResult
  without_skill: EvalSideResult
  assertions: Array<{ name: string; passed: boolean }>
  passed: boolean
}

export interface EvalSideResult {
  output_summary: string
  tool_calls: string[]
  tokens_used: number
  duration_ms: number
}

export interface MarketSkill {
  name: string
  description: string
  version: string
  category?: string
  author?: string
  tags?: string[]
  download_url?: string
  installed: boolean
  installed_version?: string
  updatable: boolean
}

export interface MarketIndex {
  skills: MarketSkill[]
  last_sync?: string
  source_count?: number
}

export interface SkillVersion {
  version: string
  created_at: string
  snapshot_path?: string
}

// ── Skill CRUD ──────────────────────────────────────────

export const listSkills = () =>
  client.get<{ skills: SkillMeta[] }>('/api/agents/admin/skills').then((r) => r.data)

export const getSkill = (id: string, includeContent?: boolean) =>
  client
    .get<SkillMeta>(`/api/agents/skills/${id}`, {
      params: includeContent ? { include_content: true } : undefined,
    })
    .then((r) => r.data)

export const createSkill = (data: SkillCreate) =>
  client.post<{ ok: true; id: string }>('/api/agents/admin/skills/create', data).then((r) => r.data)

export const updateSkill = (id: string, data: SkillUpdate) =>
  client.put<{ ok: true }>(`/api/agents/admin/skills/${id}`, data).then((r) => r.data)

export const deleteSkill = (id: string) =>
  client.delete<{ ok: true }>(`/api/agents/admin/skills/${id}`).then((r) => r.data)

export const enableSkill = (id: string) =>
  client.post<{ ok: true }>(`/api/agents/admin/skills/${id}/enable`).then((r) => r.data)

export const disableSkill = (id: string) =>
  client.post<{ ok: true }>(`/api/agents/admin/skills/${id}/disable`).then((r) => r.data)

export const exportSkill = (id: string) =>
  client.post(`/api/agents/admin/skills/${id}/export`, {}, { responseType: 'blob' }).then((r) => r.data)

// ── Skill list for /skill: menu (non-admin accessible) ──

export const listEnabledSkills = () =>
  client.get<SkillListItem[]>('/api/agents/skills/list').then((r) => r.data)

// ── Attached files ──────────────────────────────────────

export const listSkillFiles = (id: string) =>
  client.get<SkillFile[]>(`/api/agents/admin/skills/${id}/files`).then((r) => r.data)

export const uploadSkillFile = (id: string, path: string, content: string) =>
  client
    .put<{ ok: true }>(`/api/agents/admin/skills/${id}/files/${encodeURIComponent(path)}`, { content })
    .then((r) => r.data)

export const deleteSkillFile = (id: string, path: string) =>
  client
    .delete<{ ok: true }>(`/api/agents/admin/skills/${id}/files/${encodeURIComponent(path)}`)
    .then((r) => r.data)

// ── Evals ───────────────────────────────────────────────

export const getEvals = (id: string) =>
  client.get<EvalSet>(`/api/agents/admin/skills/${id}/evals`).then((r) => r.data)

export const saveEvals = (id: string, data: EvalSet) =>
  client.put<{ ok: true }>(`/api/agents/admin/skills/${id}/evals`, data).then((r) => r.data)

export const runEval = (id: string, params?: { eval_id?: number; mode?: string }) =>
  client
    .post<{ ok: true; run_id: string }>(`/api/agents/admin/skills/${id}/evals/run`, params ?? {})
    .then((r) => r.data)

export const getEvalResults = (id: string) =>
  client.get<EvalRunResult[]>(`/api/agents/admin/skills/${id}/evals/results`).then((r) => r.data)

// ── Market ──────────────────────────────────────────────

export const getMarketIndex = () =>
  client.get<MarketIndex>('/api/agents/admin/skill-market').then((r) => r.data)

export const syncMarket = () =>
  client.post<{ ok: true }>('/api/agents/admin/skill-market/sync').then((r) => r.data)

export const installFromMarket = (name: string, version?: string) =>
  client
    .post<{ ok: true; id: string }>(`/api/agents/admin/skill-market/install/${encodeURIComponent(name)}`, {
      version,
    })
    .then((r) => r.data)

// ── Versions ────────────────────────────────────────────

export const listVersions = (id: string) =>
  client.get<SkillVersion[]>(`/api/agents/admin/skills/${id}/versions`).then((r) => r.data)

export const rollbackSkill = (id: string, version: string) =>
  client
    .post<{ ok: true }>(`/api/agents/admin/skills/${id}/rollback`, { version })
    .then((r) => r.data)
