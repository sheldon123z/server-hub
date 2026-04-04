/**
 * useFollowUpSuggestions — 根据最后一条 assistant 消息的关键词生成追问建议
 *
 * 纯前端方案：关键词匹配 → 3 条建议
 */

import { useMemo, useState, useRef, useCallback } from 'react'
import { useChatStore } from '@/stores/chatStore'

interface SuggestionRule {
  keywords: string[]
  suggestions: string[]
}

const RULES: SuggestionRule[] = [
  {
    keywords: ['docker', '容器', 'container', 'compose', '镜像', 'image'],
    suggestions: ['查看所有容器状态', '检查容器日志有无异常', '清理未使用的 Docker 资源'],
  },
  {
    keywords: ['cpu', '内存', 'memory', '负载', 'load', '资源', 'gpu', 'disk', '磁盘'],
    suggestions: ['查看 GPU 使用情况', '分析资源使用趋势', '哪些用户占用资源最多？'],
  },
  {
    keywords: ['用户', 'user', '登录', 'login', '会话', 'session', '进程'],
    suggestions: ['查看当前活跃会话', '检查用户配额使用', '最近的登录历史'],
  },
  {
    keywords: ['服务', 'service', 'systemd', 'nginx', 'mysql', 'ollama'],
    suggestions: ['查看所有服务状态', '检查服务依赖关系', '查看服务日志'],
  },
  {
    keywords: ['安全', 'security', '审计', 'audit', '合规', 'compliance', '漏洞'],
    suggestions: ['执行全面安全审计', '检查 SSH 配置安全性', '查看防火墙规则'],
  },
  {
    keywords: ['cron', '定时', '任务', 'schedule'],
    suggestions: ['查看所有定时任务', '检查最近执行历史', '有失败的定时任务吗？'],
  },
  {
    keywords: ['日志', 'log', '错误', 'error', '异常', 'exception', 'fail'],
    suggestions: ['查看系统日志有无异常', '分析错误出现的时间规律', '关联分析多个数据源'],
  },
  {
    keywords: ['网络', 'network', '端口', 'port', '连接', 'connection'],
    suggestions: ['检查网络连接状态', '查看端口占用情况', '测试服务器连通性'],
  },
]

const DEFAULT_SUGGESTIONS = ['系统整体状态如何？', '有什么需要关注的异常吗？', '执行日常巡检']

function matchSuggestions(content: string): string[] {
  if (!content) return DEFAULT_SUGGESTIONS

  const lower = content.toLowerCase()
  const matchedRules = RULES.filter((rule) =>
    rule.keywords.some((kw) => lower.includes(kw)),
  )

  if (matchedRules.length === 0) return DEFAULT_SUGGESTIONS

  // 合并匹配规则的建议，取前 3 条
  const allSuggestions = matchedRules.flatMap((r) => r.suggestions)
  // 去重
  const unique = [...new Set(allSuggestions)]
  return unique.slice(0, 3)
}

export function useFollowUpSuggestions() {
  const messages = useChatStore((s) => s.messages)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const [dismissed, setDismissed] = useState(false)
  const lastAssistantIdRef = useRef<string | null>(null)

  // 检测最后一条 assistant 消息是否变化，变化时重置 dismissed
  const lastAssistantMsg = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant' && messages[i].content) {
        return messages[i]
      }
    }
    return null
  }, [messages])

  // 新的 assistant 消息出现时，重置 dismissed 状态
  if (lastAssistantMsg && lastAssistantMsg._id !== lastAssistantIdRef.current) {
    lastAssistantIdRef.current = lastAssistantMsg._id
    if (dismissed) setDismissed(false)
  }

  const autoSuggestions = useMemo(() => {
    if (isStreaming || dismissed) return []
    if (!lastAssistantMsg) return DEFAULT_SUGGESTIONS
    return matchSuggestions(lastAssistantMsg.content)
  }, [lastAssistantMsg, isStreaming, dismissed])

  const clearSuggestions = useCallback(() => setDismissed(true), [])

  return {
    suggestions: autoSuggestions,
    clearSuggestions,
    hasSuggestions: autoSuggestions.length > 0 && !isStreaming,
  }
}
