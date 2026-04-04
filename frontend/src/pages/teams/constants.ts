/**
 * Teams 模块共享常量
 */

import type { TeamTopology, AgentType } from '@/types/team'

export const TOPOLOGY_LABELS: Record<TeamTopology, { label: string; color: string; desc: string }> = {
  supervisor: { label: '组长调度', color: 'bg-accent-dim text-accent', desc: 'Leader 分配任务给 Workers' },
  swarm: { label: '自主协作', color: 'bg-green/20 text-green', desc: 'Agent 间自主移交任务' },
  pipeline: { label: '流水线', color: 'bg-blue/20 text-blue', desc: '按 position 顺序执行' },
}

export const AGENT_TYPE_COLORS: Record<AgentType, string> = {
  leader: 'bg-accent-dim text-accent',
  worker: 'bg-blue/20 text-blue',
  reviewer: 'bg-purple/20 text-purple',
}

export const STATUS_BADGES: Record<string, string> = {
  pending: 'bg-text3/20 text-text3',
  running: 'bg-blue/20 text-blue',
  success: 'bg-green/20 text-green',
  failed: 'bg-red/20 text-red',
  timeout: 'bg-yellow/20 text-yellow',
  cancelled: 'bg-text3/20 text-text3',
}
