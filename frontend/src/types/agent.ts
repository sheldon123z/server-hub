export type MessageRole = 'user' | 'assistant' | 'tool_call' | 'tool_result' | 'approval' | 'ui_component' | 'skill_loaded'

export interface ChatMessage {
  _id: string
  role: MessageRole
  content: string
  tool?: string
  args?: Record<string, unknown>
  approval_id?: string
  description?: string
  actions?: Array<{ name: string; args: Record<string, unknown> }>
  _serverId?: string
  /** 技能加载信息 */
  skillInfo?: {
    skillId: string
    name: string
    description: string
    allowedTools?: string[]
    trigger: 'command' | 'auto'
  }
}

export interface AgentRunSummary {
  id: string
  status: string
  created_at: string
  completed_at?: string | null
}

export interface TodoItem {
  content: string
  status: 'pending' | 'in_progress' | 'completed'
  _justCompleted?: boolean
}

export interface Conversation {
  id: string
  title: string
  username: string
  safety_mode: string
  created_at: string
  updated_at: string
  message_count: number
  latest_run_status?: string | null
}

export interface Patrol {
  id: string
  display_name: string
  description: string
  enabled: boolean
  interval_minutes: number
  last_run: string | null
  last_status: string | null
  next_run: string | null
  prompt: string
  check_tools: string
}

export interface SkillRecommendation {
  id: string
  name: string
  summary: string
  score: number
  reasons: string[]
}

export interface InstalledSkill {
  id: string
  version: string
  name: string
  summary: string
  enabled: boolean
  source_type: string
  source_ref?: string | null
  install_path: string
  manifest: Record<string, unknown>
  skill_markdown?: string
}

export interface AgentRun {
  id: string
  conversation_id: string
  username: string
  status: string
  safety_mode: string
  page_context?: string | null
  skill_id?: string | null
  user_message: string
  error?: string | null
  created_at: string
  updated_at: string
  completed_at?: string | null
}

export interface AgentRunEvent {
  id: string
  event_type: string
  payload: Record<string, unknown>
  created_at: string
}

// ── A to UI: Agent UI 组件渲染 ──

export type UIComponentType = 'chart' | 'table' | 'form' | 'card' | 'metric' | 'log-viewer' | 'process-tree' | 'custom'

export interface UIAction {
  id: string
  label: string
  variant?: 'primary' | 'secondary' | 'danger'
  action_type: 'callback' | 'navigate' | 'api' | 'agent' | 'submit' | 'reset'
  payload?: Record<string, unknown>
}

export interface UIComponentData {
  id: string
  type: UIComponentType
  version?: string
  title?: string
  [key: string]: unknown
}

export interface UIComponentMessage extends ChatMessage {
  role: 'ui_component'
  componentType: UIComponentType
  data: UIComponentData
  uiActions?: UIAction[]
}

// ── 消息分组：工具调用与 SubAgent ──

export type ToolCallStatus = 'pending' | 'completed' | 'error' | 'interrupted'

export interface ToolCallItem {
  id: string
  name: string
  args: Record<string, unknown>
  result?: string
  status: ToolCallStatus
}

export interface SubAgentItem {
  id: string
  name: string
  subAgentName: string
  input: Record<string, unknown>
  output?: Record<string, unknown>
  status: ToolCallStatus
}

export interface ProcessedMessage {
  message: ChatMessage
  toolCalls: ToolCallItem[]
  subAgents: SubAgentItem[]
}

export type MessageGroupType = 'content' | 'processing' | 'subagent' | 'mixed'
