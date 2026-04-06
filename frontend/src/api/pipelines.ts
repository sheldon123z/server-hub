/**
 * Pipeline 编排引擎 — API 层
 *
 * TypeScript 类型定义 + API 调用封装
 * API 前缀: /api/pipelines
 */

import client from '@/api/client'

/* ─── 类型定义 ─── */

export interface StepDefinition {
  id: string
  type:
    | 'shell'
    | 'ssh'
    | 'playbook'
    | 'agent'
    | 'approval'
    | 'condition'
    | 'parallel'
    | 'notify'
    | 'http'
    | 'delay'
  name: string
  [key: string]: unknown
}

export interface PipelineParam {
  name: string
  type: 'string' | 'number' | 'boolean' | 'array' | 'secret'
  required?: boolean
  default?: unknown
  description?: string
}

export interface Pipeline {
  id: string
  name: string
  display_name: string
  description: string
  yaml_content: string
  steps_json: string
  params_json: string
  trigger_json: string
  version: number
  max_concurrent_runs: number
  timeout: number
  enabled: number
  created_by: string
  created_at: string
  updated_at: string
}

export type RunStatus = 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled'

export interface PipelineRun {
  id: string
  pipeline_id: string
  pipeline_version: number
  status: RunStatus
  params_json: string
  current_step_id: string | null
  steps_state_json: string
  trigger_type: string
  started_at: string
  completed_at: string | null
  started_by: string
  error: string | null
  summary: string | null
}

export type StepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'

export interface StepLog {
  id: number
  run_id: string
  step_id: string
  step_type: string
  status: StepStatus
  started_at: string | null
  completed_at: string | null
  input_json: string | null
  output_json: string | null
  error: string | null
  duration_ms: number | null
}

export interface ValidationResult {
  valid: boolean
  errors?: string[]
}

/* ─── API 调用 ─── */

export const pipelinesApi = {
  // Pipeline 定义 CRUD
  list: (params?: { enabled?: boolean; search?: string }) =>
    client.get<Pipeline[]>('/api/pipelines', { params }),

  create: (yaml_content: string) =>
    client.post<{ ok: true; id: string }>('/api/pipelines', { yaml_content }),

  get: (id: string) => client.get<Pipeline>(`/api/pipelines/${id}`),

  update: (id: string, yaml_content: string) =>
    client.put<{ ok: true; version: number }>(`/api/pipelines/${id}`, { yaml_content }),

  delete: (id: string) => client.delete<{ ok: true }>(`/api/pipelines/${id}`),

  validate: (yaml_content: string) =>
    client.post<ValidationResult>('/api/pipelines/validate', { yaml_content }),

  getMermaid: (id: string) => client.get<{ mermaid: string }>(`/api/pipelines/${id}/mermaid`),

  // 执行管理
  run: (id: string, params: Record<string, unknown>) =>
    client.post<{ ok: true; run_id: string }>(`/api/pipelines/${id}/run`, { params }),

  listRuns: (params?: { pipeline_id?: string; status?: RunStatus; limit?: number }) =>
    client.get<PipelineRun[]>('/api/pipelines/runs', { params }),

  getRun: (runId: string) => client.get<PipelineRun>(`/api/pipelines/runs/${runId}`),

  cancelRun: (runId: string) =>
    client.post<{ ok: true }>(`/api/pipelines/runs/${runId}/cancel`),

  approveRun: (runId: string) =>
    client.post<{ ok: true }>(`/api/pipelines/runs/${runId}/approve`),

  rejectRun: (runId: string) =>
    client.post<{ ok: true }>(`/api/pipelines/runs/${runId}/reject`),

  getRunLogs: (runId: string) => client.get<StepLog[]>(`/api/pipelines/runs/${runId}/logs`),
}
