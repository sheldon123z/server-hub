/**
 * message-utils — 消息类型守卫、工具分类图标映射
 */

import type { ChatMessage, ProcessedMessage, ToolCallItem, SubAgentItem } from '@/types/agent'

// ===== 类型守卫 =====

/** 判断 ChatMessage 是否为 UIComponentMessage */
export function isUIComponentMessage(msg: ChatMessage): msg is ChatMessage & {
  role: 'ui_component'
  componentType: string
  data: Record<string, unknown>
} {
  return msg.role === 'ui_component' && 'componentType' in msg
}

/** 判断 ProcessedMessage 是否有可见文本内容 */
export function hasContent(pm: ProcessedMessage): boolean {
  const content = pm.message.content
  return typeof content === 'string' && content.trim().length > 0
}

/** 判断 ProcessedMessage 是否有工具调用 */
export function hasToolCalls(pm: ProcessedMessage): boolean {
  return pm.toolCalls.length > 0
}

/** 判断 ProcessedMessage 是否有 SubAgent */
export function hasSubAgents(pm: ProcessedMessage): boolean {
  return pm.subAgents.length > 0
}

/** 提取消息的文本内容（统一处理 string | ContentPart[]） */
export function extractTextContent(content: unknown): string {
  if (!content) return ''
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content
      .filter((part: Record<string, unknown>) => part?.type === 'text')
      .map((part: Record<string, unknown>) => (part?.text as string) ?? '')
      .join('')
  }
  return String(content)
}

/** 判断工具调用是否已完成 */
export function isToolCallCompleted(tc: ToolCallItem): boolean {
  return tc.status === 'completed' || tc.status === 'error'
}

/** 判断 SubAgent 是否已完成 */
export function isSubAgentCompleted(sa: SubAgentItem): boolean {
  return sa.status === 'completed' || sa.status === 'error'
}

/** 获取消息分组类型 */
import type { MessageGroupType } from '@/types/agent'

export function getMessageGroupType(pm: ProcessedMessage): MessageGroupType {
  const hasTc = hasToolCalls(pm)
  const hasSa = hasSubAgents(pm)
  const hasCt = hasContent(pm)

  if (hasSa) return 'subagent'
  if (hasTc && hasCt) return 'mixed'
  if (hasTc) return 'processing'
  return 'content'
}

// ===== 工具分类图标映射 =====

export interface ToolDisplayInfo {
  icon: string       // Lucide icon name
  color: string      // Tailwind color class
  label: string      // 中文显示名
  category: string   // 工具类别
}

const TOOL_DISPLAY_MAP: Record<string, ToolDisplayInfo> = {
  // Docker 类
  list_docker_containers: { icon: 'Box', color: 'text-blue-400', label: '容器列表', category: 'Docker' },
  get_container_logs: { icon: 'FileText', color: 'text-blue-400', label: '容器日志', category: 'Docker' },
  docker_container_action: { icon: 'Play', color: 'text-blue-400', label: '容器操作', category: 'Docker' },
  docker_compose_action: { icon: 'Layers', color: 'text-blue-400', label: 'Compose 操作', category: 'Docker' },
  docker_container_exec: { icon: 'Terminal', color: 'text-blue-400', label: '容器命令', category: 'Docker' },
  docker_prune: { icon: 'Trash2', color: 'text-blue-400', label: '资源清理', category: 'Docker' },
  list_docker_networks: { icon: 'Network', color: 'text-blue-400', label: '网络列表', category: 'Docker' },
  // 系统监控
  get_system_overview: { icon: 'Activity', color: 'text-green-400', label: '系统概览', category: '系统' },
  get_disk_info: { icon: 'HardDrive', color: 'text-green-400', label: '磁盘信息', category: '系统' },
  analyze_resource_trend: { icon: 'TrendingUp', color: 'text-green-400', label: '资源趋势', category: '系统' },
  // 用户管理
  get_user_resources: { icon: 'Users', color: 'text-purple-400', label: '用户资源', category: '用户' },
  manage_linux_user: { icon: 'UserCog', color: 'text-purple-400', label: '用户管理', category: '用户' },
  kill_user_processes: { icon: 'XCircle', color: 'text-red-400', label: '终止进程', category: '用户' },
  kill_single_process_tool: { icon: 'XCircle', color: 'text-red-400', label: '终止进程', category: '用户' },
  get_user_login_history_tool: { icon: 'Clock', color: 'text-purple-400', label: '登录历史', category: '用户' },
  get_active_sessions_tool: { icon: 'Monitor', color: 'text-purple-400', label: '活跃会话', category: '用户' },
  check_quota_violations: { icon: 'AlertTriangle', color: 'text-orange-400', label: '配额违规', category: '用户' },
  // 服务管理
  list_systemd_services: { icon: 'Server', color: 'text-yellow-400', label: '服务列表', category: '服务' },
  get_service_logs: { icon: 'FileText', color: 'text-yellow-400', label: '服务日志', category: '服务' },
  service_control: { icon: 'Settings', color: 'text-yellow-400', label: '服务控制', category: '服务' },
  service_enable_disable_tool: { icon: 'ToggleLeft', color: 'text-yellow-400', label: '自启管理', category: '服务' },
  get_service_dependencies_tool: { icon: 'GitBranch', color: 'text-yellow-400', label: '服务依赖', category: '服务' },
  // 安全
  check_compliance: { icon: 'Shield', color: 'text-red-400', label: '合规检查', category: '安全' },
  auto_fix_compliance: { icon: 'ShieldCheck', color: 'text-red-400', label: '自动修复', category: '安全' },
  // Cron
  list_cron_jobs: { icon: 'Clock', color: 'text-cyan-400', label: '定时任务', category: 'Cron' },
  create_cron_job: { icon: 'PlusCircle', color: 'text-cyan-400', label: '创建任务', category: 'Cron' },
  delete_cron_job_tool: { icon: 'Trash2', color: 'text-cyan-400', label: '删除任务', category: 'Cron' },
  validate_cron_expr: { icon: 'CheckCircle', color: 'text-cyan-400', label: '验证表达式', category: 'Cron' },
  // 知识库
  retrieve_knowledge: { icon: 'BookOpen', color: 'text-indigo-400', label: '知识检索', category: '知识' },
  search_fault_cases: { icon: 'Search', color: 'text-indigo-400', label: '故障搜索', category: '知识' },
  // 通知
  send_notification: { icon: 'Bell', color: 'text-pink-400', label: '发送通知', category: '通知' },
  // 内置工具
  execute: { icon: 'Terminal', color: 'text-text2', label: '执行命令', category: '内置' },
  read_file: { icon: 'FileText', color: 'text-cyan-400', label: '读取文件', category: '内置' },
  write_file: { icon: 'FilePlus', color: 'text-cyan-400', label: '写入文件', category: '内置' },
  edit_file: { icon: 'FileEdit', color: 'text-cyan-400', label: '编辑文件', category: '内置' },
  ls: { icon: 'FolderOpen', color: 'text-cyan-400', label: '列出文件', category: '内置' },
  glob: { icon: 'Search', color: 'text-cyan-400', label: '文件搜索', category: '内置' },
  grep: { icon: 'Search', color: 'text-cyan-400', label: '内容搜索', category: '内置' },
  write_todos: { icon: 'ListTodo', color: 'text-cyan-400', label: '任务管理', category: '内置' },
  // 研究
  web_search: { icon: 'Globe', color: 'text-emerald-400', label: '网络搜索', category: '研究' },
  fetch_webpage_content: { icon: 'ExternalLink', color: 'text-emerald-400', label: '获取网页', category: '研究' },
  think: { icon: 'Brain', color: 'text-violet-400', label: '思考', category: '推理' },
  // UI 渲染
  render_chart: { icon: 'BarChart3', color: 'text-teal-400', label: '渲染图表', category: 'UI' },
  render_table: { icon: 'Table', color: 'text-teal-400', label: '渲染表格', category: 'UI' },
  render_form: { icon: 'FormInput', color: 'text-teal-400', label: '渲染表单', category: 'UI' },
  render_card: { icon: 'CreditCard', color: 'text-teal-400', label: '渲染卡片', category: 'UI' },
  // 剧本
  playbook_list: { icon: 'BookOpen', color: 'text-amber-400', label: '剧本列表', category: '剧本' },
  playbook_execute: { icon: 'PlayCircle', color: 'text-amber-400', label: '执行剧本', category: '剧本' },
  playbook_create: { icon: 'FilePlus', color: 'text-amber-400', label: '创建剧本', category: '剧本' },
  ssh_execute_command: { icon: 'Terminal', color: 'text-amber-400', label: 'SSH 执行', category: '剧本' },
  // 服务器
  server_list: { icon: 'Server', color: 'text-slate-400', label: '服务器列表', category: '服务器' },
  server_test_connectivity: { icon: 'Wifi', color: 'text-slate-400', label: '连通测试', category: '服务器' },
}

const DEFAULT_TOOL_INFO: ToolDisplayInfo = {
  icon: 'Wrench',
  color: 'text-text3',
  label: '工具',
  category: '其他',
}

export function getToolDisplayInfo(toolName: string): ToolDisplayInfo {
  return TOOL_DISPLAY_MAP[toolName] ?? { ...DEFAULT_TOOL_INFO, label: toolName }
}

/** 获取工具调用结果的摘要（截断显示） */
export function getToolResultSummary(result: string | undefined, maxLength = 100): string {
  if (!result) return ''
  const trimmed = result.trim()
  if (trimmed.length <= maxLength) return trimmed
  return trimmed.slice(0, maxLength) + '...'
}
