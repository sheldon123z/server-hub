import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Check, MessageSquare } from 'lucide-react'
import { cn, ensureArray } from '@/lib/utils'
import { useChatStore } from '@/stores/chatStore'
import { useArtifactStore } from '@/stores/artifactStore'
import client from '@/api/client'
import type { Conversation, ChatMessage, TodoItem } from '@/types/agent'

async function fetchConversations(): Promise<Conversation[]> {
  const { data } = await client.get('/api/agents/conversations')
  return ensureArray<Conversation>(data)
}

interface ServerMessage {
  id: string
  role: string
  content: string | Array<{ type: string; text: string }>
  tool?: string
  args?: Record<string, unknown>
  approval_id?: string
  description?: string
  actions?: unknown[]
}

async function fetchConversation(
  id: string,
): Promise<{ conversation_id: string; messages: ServerMessage[]; todos: never[] }> {
  const { data } = await client.get(`/api/agents/conversations/${id}`)
  return data
}

async function deleteConversationApi(id: string): Promise<void> {
  await client.delete(`/api/agents/conversations/${id}`)
}

function StatusDot({ status }: { status?: string | null }) {
  if (!status) return null
  const color =
    status === 'running'
      ? 'bg-green-500 animate-pulse'
      : status === 'completed'
        ? 'bg-green-500'
        : status === 'error'
          ? 'bg-red-500'
          : status === 'interrupted'
            ? 'bg-orange-400'
            : ''
  if (!color) return null
  return <span className={cn('inline-block w-1.5 h-1.5 rounded-full shrink-0', color)} />
}

export function ConversationSidebar() {
  const queryClient = useQueryClient()
  const { conversationId, setConversationId, setMessages, setTodos, clearChat } =
    useChatStore()
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  // 3 秒后自动取消确认状态
  useEffect(() => {
    if (!confirmDeleteId) return
    const timer = setTimeout(() => setConfirmDeleteId(null), 3000)
    return () => clearTimeout(timer)
  }, [confirmDeleteId])

  // 页面刷新恢复：检查 sessionStorage 中是否有持久化的 conversationId
  useEffect(() => {
    const persistedId = sessionStorage.getItem('serverhub-conversation-id')
    if (persistedId && !conversationId) {
      handleLoad(persistedId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // 仅 mount 时执行一次

  const { data: conversations = [] } = useQuery({
    queryKey: ['conversations'],
    queryFn: fetchConversations,
    refetchInterval: 30_000,
  })

  const grouped = useMemo(() => {
    const now = new Date()
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterdayStart = new Date(todayStart.getTime() - 86_400_000)
    const weekStart = new Date(todayStart.getTime() - 6 * 86_400_000)

    const groups: { today: Conversation[]; yesterday: Conversation[]; thisWeek: Conversation[]; older: Conversation[] } = {
      today: [],
      yesterday: [],
      thisWeek: [],
      older: [],
    }
    for (const conv of conversations) {
      const d = new Date(conv.updated_at)
      if (d >= todayStart) groups.today.push(conv)
      else if (d >= yesterdayStart) groups.yesterday.push(conv)
      else if (d >= weekStart) groups.thisWeek.push(conv)
      else groups.older.push(conv)
    }
    return groups
  }, [conversations])

  const deleteMutation = useMutation({
    mutationFn: deleteConversationApi,
    onSuccess: (_data, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      if (conversationId === deletedId) {
        clearChat()
      }
    },
  })

  function handleNew() {
    clearChat()
  }

  async function handleLoad(id: string) {
    if (id === conversationId) return

    try {
      const detail = await fetchConversation(id)

      // Map server messages to ChatMessage with stable _ids
      const msgs: ChatMessage[] = ensureArray<ServerMessage>(detail.messages).map(
        (m: ServerMessage, i: number) => ({
          _id: 'h_' + i,
          role: (m.role as ChatMessage['role']) ?? 'assistant',
          content: typeof m.content === 'string' ? m.content : Array.isArray(m.content) ? m.content.map((b) => b?.text ?? '').join('') : String(m.content ?? ''),
          tool: m.tool as string | undefined,
          args: m.args as Record<string, unknown> | undefined,
          approval_id: m.approval_id as string | undefined,
          description: m.description as string | undefined,
          actions: Array.isArray(m.actions) ? (m.actions as ChatMessage['actions']) : undefined,
          _serverId: m.id as string | undefined,
        }),
      )

      setConversationId(detail.conversation_id)
      setMessages(msgs)
      setTodos(ensureArray<TodoItem>(detail.todos))

      // 恢复 artifacts 列表
      try {
        const { data: artData } = await client.get('/api/agents/artifacts/list', {
          params: { conversation_id: detail.conversation_id },
        })
        const items = ensureArray<{ file_path: string; action: string; created_at: string }>(artData?.items)
        useArtifactStore.getState().setArtifactsForConversation(
          detail.conversation_id,
          items.map((a) => ({
            filePath: a.file_path,
            action: (a.action as 'write_file' | 'edit_file') ?? 'write_file',
            timestamp: new Date(a.created_at).getTime(),
          })),
        )
      } catch {
        // Artifact 恢复失败不影响对话加载
      }
    } catch {
      // Silently fail; user can retry
    }
  }

  function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    if (confirmDeleteId === id) {
      setConfirmDeleteId(null)
      deleteMutation.mutate(id)
    } else {
      setConfirmDeleteId(id)
    }
  }

  function formatTime(iso: string) {
    if (!iso) return ''
    const d = new Date(iso)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffDays = Math.floor(diffMs / 86_400_000)

    if (diffDays === 0) {
      return d.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
    }
    if (diffDays === 1) return '昨天'
    if (diffDays < 7) return diffDays + '天前'
    return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
  }

  return (
    <div className="flex flex-col h-full w-full bg-bg">
      {/* New conversation button */}
      <button
        onClick={handleNew}
        className={cn(
          'flex items-center gap-2 mx-2 mt-2 mb-1 px-3 py-2 rounded-lg',
          'text-sm font-medium text-accent',
          'border border-dashed border-accent/40 hover:bg-accent-dim',
          'transition-colors cursor-pointer',
        )}
      >
        <Plus size={16} />
        <span>新对话</span>
      </button>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-1 py-1">
        {conversations.length === 0 ? (
          <div className="text-center text-text3 text-xs mt-8 px-3">
            暂无对话记录
          </div>
        ) : (
          <>
            {(
              [
                { key: 'today', label: '今天' },
                { key: 'yesterday', label: '昨天' },
                { key: 'thisWeek', label: '本周' },
                { key: 'older', label: '更早' },
              ] as const
            ).map(({ key, label }) => {
              const group = grouped[key]
              if (group.length === 0) return null
              return (
                <div key={key}>
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-text3 px-3 pt-3 pb-1">
                    {label}
                  </div>
                  {group.map((conv) => {
                    const isActive = conv.id === conversationId
                    return (
                      <div
                        key={conv.id}
                        onClick={() => handleLoad(conv.id)}
                        className={cn(
                          'group flex items-center gap-2 px-2.5 py-2 mx-1 my-0.5 rounded-lg cursor-pointer',
                          'transition-colors text-sm',
                          isActive
                            ? 'bg-accent-dim text-accent'
                            : 'text-text2 hover:bg-card hover:text-text',
                        )}
                      >
                        <MessageSquare size={14} className="shrink-0 opacity-50" />
                        <StatusDot status={conv.latest_run_status} />
                        <div className="flex-1 min-w-0">
                          <div className="truncate text-[13px] leading-tight">
                            {conv.title || '新对话'}
                          </div>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className="text-[11px] text-text3">
                              {formatTime(conv.updated_at)}
                            </span>
                            {conv.message_count > 0 && (
                              <span className="text-[10px] text-text3 tabular-nums">
                                {conv.message_count}
                              </span>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={(e) => handleDelete(e, conv.id)}
                          className={cn(
                            'shrink-0 p-0.5 rounded transition-all cursor-pointer',
                            confirmDeleteId === conv.id
                              ? 'opacity-100 bg-red/20 text-red'
                              : 'opacity-0 group-hover:opacity-100 hover:bg-red/20 hover:text-red',
                          )}
                          title={confirmDeleteId === conv.id ? '确认删除' : '删除对话'}
                        >
                          {confirmDeleteId === conv.id ? <Check size={14} /> : <X size={14} />}
                        </button>
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </>
        )}
      </div>
    </div>
  )
}
