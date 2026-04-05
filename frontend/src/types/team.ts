/**
 * Teams 模块前端类型定义
 *
 * 团队多 Agent 协作引擎 — Supervisor / Swarm / Pipeline 三种拓扑
 * API 前缀: /api/agents/teams
 */

/* ─── 团队 ─── */

export type TeamTopology = 'supervisor' | 'swarm' | 'pipeline'
export type SafetyMode = 'supervised' | 'autonomous'

export interface Team {
  id: string
  name: string
  description: string
  topology: TeamTopology
  config_json: string
  default_model: string | null
  safety_mode: SafetyMode
  max_steps: number
  timeout_seconds: number
  enabled: number
  is_builtin: number
  created_by: string
  created_at: string
  updated_at: string
  member_count?: number
}

export interface TeamCreateRequest {
  name: string
  description?: string
  topology?: TeamTopology
  config?: Record<string, unknown>
  default_model?: string | null
  safety_mode?: SafetyMode
  max_steps?: number
  timeout_seconds?: number
}

export type TeamUpdateRequest = Partial<TeamCreateRequest> & { enabled?: number }

/* ─── 成员 ─── */

export type AgentType = 'leader' | 'worker' | 'reviewer'

export interface TeamMember {
  id: string
  team_id: string
  name: string
  agent_type: AgentType
  description: string
  system_prompt: string
  tools_json: string
  model_id: string | null
  max_calls: number
  handoff_targets: string
  position: number
  config_json: string
}

export interface MemberCreateRequest {
  name: string
  agent_type?: AgentType
  description?: string
  system_prompt: string
  tools?: string[]
  model_id?: string | null
  max_calls?: number
  handoff_targets?: string[]
  position?: number
  config?: Record<string, unknown>
}

export type MemberUpdateRequest = Partial<MemberCreateRequest>

/* ─── 执行 ─── */

export type ExecutionStatus = 'pending' | 'running' | 'success' | 'failed' | 'timeout' | 'cancelled'

export interface TeamExecution {
  id: string
  team_id: string
  instruction: string
  status: ExecutionStatus
  topology: TeamTopology
  result: string | null
  agent_outputs: string
  started_by: string
  started_at: string
  completed_at: string | null
  duration_seconds: number | null
  total_steps: number | null
  total_tokens: number | null
  usage_json: string | null
  error: string | null
}

/* ─── 消息 ─── */

export interface TeamMessage {
  id: number
  execution_id: string
  timestamp: string
  from_agent: string
  to_agent: string | null
  message_type: 'text' | 'tool_call' | 'tool_result'
  content: string
  metadata: string
}

/* ─── 模板 ─── */

export interface TeamTemplate {
  id: string
  name: string
  description: string
  topology: TeamTopology
  member_defs: Array<{
    name: string
    agent_type: AgentType
    description: string
    system_prompt: string
    tools: string[]
    model_id?: string
    max_calls: number
    handoff_targets: string[]
  }>
  member_count?: number
  safety_mode: SafetyMode
  max_steps: number
  timeout_seconds: number
}

/* ─── SSE 执行事件 ─── */

export interface TeamSSEEvent {
  event: 'team_start' | 'agent_start' | 'agent_message' | 'agent_tool_call' | 'agent_tool_result' | 'agent_complete' | 'team_error' | 'team_complete' | 'done'
  data: Record<string, unknown>
}
