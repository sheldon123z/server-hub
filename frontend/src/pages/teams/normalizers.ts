/**
 * Teams 模块数据规范化函数
 */

import { ensureArray } from '@/lib/utils'
import type {
  Team,
  TeamTopology,
  SafetyMode,
  AgentType,
  TeamMember,
  TeamExecution,
  ExecutionStatus,
  TeamTemplate,
} from '@/types/team'

export function normalizeTeams(value: unknown): Team[] {
  const arr = Array.isArray(value) ? value : (value as Record<string, unknown>)?.teams ?? []
  return ensureArray<Record<string, unknown>>(arr).map((item) => ({
    id: String(item.id ?? ''),
    name: String(item.name ?? ''),
    description: String(item.description ?? ''),
    topology: (['supervisor','swarm','pipeline'].includes(item.topology as string) ? item.topology : 'supervisor') as TeamTopology,
    config_json: String(item.config_json ?? '{}'),
    default_model: item.default_model ? String(item.default_model) : null,
    safety_mode: (['supervised','autonomous'].includes(item.safety_mode as string) ? item.safety_mode : 'supervised') as SafetyMode,
    max_steps: Number(item.max_steps ?? 50),
    timeout_seconds: Number(item.timeout_seconds ?? 300),
    enabled: Number(item.enabled ?? 1),
    is_builtin: Number(item.is_builtin ?? 0),
    created_by: String(item.created_by ?? ''),
    created_at: String(item.created_at ?? ''),
    updated_at: String(item.updated_at ?? ''),
    member_count: item.member_count != null ? Number(item.member_count) : undefined,
  }))
}

export function normalizeMembers(value: unknown): TeamMember[] {
  const arr = Array.isArray(value) ? value : (value as Record<string, unknown>)?.members ?? []
  return ensureArray<Record<string, unknown>>(arr).map((item) => ({
    id: String(item.id ?? ''),
    team_id: String(item.team_id ?? ''),
    name: String(item.name ?? ''),
    agent_type: (item.agent_type as AgentType) ?? 'worker',
    description: String(item.description ?? ''),
    system_prompt: String(item.system_prompt ?? ''),
    tools_json: String(item.tools_json ?? '[]'),
    model_id: item.model_id ? String(item.model_id) : null,
    max_calls: Number(item.max_calls ?? 15),
    handoff_targets: String(item.handoff_targets ?? '[]'),
    position: Number(item.position ?? 0),
    config_json: String(item.config_json ?? '{}'),
  }))
}

export function normalizeExecutions(value: unknown): TeamExecution[] {
  const arr = Array.isArray(value) ? value : (value as Record<string, unknown>)?.executions ?? []
  return ensureArray<Record<string, unknown>>(arr).map((item) => ({
    id: String(item.id ?? ''),
    team_id: String(item.team_id ?? ''),
    instruction: String(item.instruction ?? ''),
    status: (['pending','running','success','failed','timeout','cancelled'].includes(String(item.status)) ? String(item.status) : 'pending') as ExecutionStatus,
    topology: String(item.topology ?? 'supervisor') as TeamTopology,
    result: item.result ? String(item.result) : null,
    agent_outputs: String(item.agent_outputs ?? '{}'),
    started_by: String(item.started_by ?? ''),
    started_at: String(item.started_at ?? ''),
    completed_at: item.completed_at ? String(item.completed_at) : null,
    duration_seconds: item.duration_seconds != null ? Number(item.duration_seconds) : null,
    total_steps: item.total_steps != null ? Number(item.total_steps) : null,
    total_tokens: item.total_tokens != null ? Number(item.total_tokens) : null,
    usage_json: item.usage_json ? String(item.usage_json) : null,
    error: item.error ? String(item.error) : null,
  }))
}

export function normalizeTemplates(value: unknown): TeamTemplate[] {
  const arr = Array.isArray(value) ? value : (value as Record<string, unknown>)?.templates ?? []
  return ensureArray<Record<string, unknown>>(arr).map((item) => ({
    id: String(item.id ?? ''),
    name: String(item.name ?? ''),
    description: String(item.description ?? ''),
    topology: String(item.topology ?? 'supervisor') as TeamTopology,
    member_defs: Array.isArray(item.member_defs) ? item.member_defs : Array.isArray(item.members) ? item.members : [],
    member_count: item.member_count != null ? Number(item.member_count) : Array.isArray(item.members) ? item.members.length : Array.isArray(item.member_defs) ? item.member_defs.length : 0,
    safety_mode: String(item.safety_mode ?? 'supervised') as SafetyMode,
    max_steps: Number(item.max_steps ?? 50),
    timeout_seconds: Number(item.timeout_seconds ?? 300),
  }))
}
