export type MessageRole = 'user' | 'assistant' | 'tool_call' | 'tool_result' | 'approval'

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
