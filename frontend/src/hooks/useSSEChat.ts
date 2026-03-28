import { useCallback, useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useChatStore } from '@/stores/chatStore'
import type { TodoItem } from '@/types/agent'

function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

interface SendMessageOptions {
  pageContext?: string
  skillId?: string | null
}

export function useSSEChat() {
  const store = useChatStore()
  const queryClient = useQueryClient()
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => abortRef.current?.abort()
  }, [])

  const sendMessage = useCallback(
    async (text: string, options?: SendMessageOptions) => {
      const state = useChatStore.getState()
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      const conversationId = state.conversationId ?? generateUUID()
      if (!state.conversationId) {
        store.setConversationId(conversationId)
      }

      const seq = state._msgSeq + 1
      store.pushMsg({
        _id: 'u_' + seq,
        role: 'user',
        content: text,
      })
      store.setStreaming(true)

      try {
        const response = await fetch('/api/agents/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          signal: controller.signal,
          body: JSON.stringify({
            message: text,
            conversation_id: conversationId,
            safety_mode: state.safetyMode,
            page_context: options?.pageContext,
            skill_id: options?.skillId ?? state.selectedSkillId,
          }),
        })

        if (!response.ok) {
          const errText = await response.text()
          store.pushMsg({ role: 'assistant', content: '错误: ' + (errText || response.statusText) })
          return
        }

        const reader = response.body?.getReader()
        if (!reader) return

        const decoder = new TextDecoder()
        let buffer = ''
        let currentEvent = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed) {
              currentEvent = ''
              continue
            }
            if (trimmed.startsWith('event:')) {
              currentEvent = trimmed.slice(6).trim()
              continue
            }
            if (!trimmed.startsWith('data:')) continue

            const dataStr = trimmed.slice(5).trim()
            if (!dataStr) continue
            try {
              const data = JSON.parse(dataStr)
              handleSSEEvent(currentEvent, data)
            } catch {
              // ignore invalid chunks
            }
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        store.pushMsg({
          role: 'assistant',
          content: '错误: ' + (err instanceof Error ? err.message : '连接失败'),
        })
      } finally {
        store.setStreaming(false)
        queryClient.invalidateQueries({ queryKey: ['conversations'] })
        queryClient.invalidateQueries({ queryKey: ['agent-runs'] })
      }
    },
    [queryClient, store],
  )

  function extractContent(raw: unknown): string {
    if (typeof raw === 'string') return raw
    if (Array.isArray(raw)) {
      return raw
        .map((block: any) => {
          if (typeof block === 'string') return block
          if (block?.type === 'text' && typeof block.text === 'string') return block.text
          return ''
        })
        .join('')
    }
    if (raw && typeof raw === 'object') return JSON.stringify(raw)
    return String(raw ?? '')
  }

  function handleSSEEvent(event: string, data: Record<string, unknown>) {
    switch (event) {
      case 'run.started':
        if (data.run_id) {
          store.setCurrentRunId(data.run_id as string)
        }
        break

      case 'message.final':
      case 'message':
        store.pushMsg({
          role: 'assistant',
          content: extractContent(data.content),
          _serverId: (data.id as string | undefined) ?? (data.run_id as string | undefined),
        })
        break

      case 'tool.call':
      case 'tool_call':
        store.pushMsg({
          role: 'tool_call',
          tool: (data.tool as string) ?? (data.name as string),
          args: (data.input as Record<string, unknown>) ?? (data.args as Record<string, unknown>),
          content: '',
          _serverId: data.id as string | undefined,
        })
        break

      case 'tool.result':
      case 'tool_result':
        store.pushMsg({
          role: 'tool_result',
          tool: data.tool as string,
          content: extractContent(data.content),
          _serverId: data.id as string | undefined,
        })
        break

      case 'todo.update':
      case 'todo_update': {
        const items = ((Array.isArray(data) ? data : data.todos ?? []) as TodoItem[]) ?? []
        const prevTodos = useChatStore.getState().todos
        const updated = items.map((item) => {
          const prev = prevTodos.find((t) => t.content === item.content)
          if (prev && prev.status !== 'completed' && item.status === 'completed') {
            return { ...item, _justCompleted: true }
          }
          return item
        })
        store.setTodos(updated)
        setTimeout(() => {
          const current = useChatStore.getState().todos
          store.setTodos(current.map((t) => (t._justCompleted ? { ...t, _justCompleted: false } : t)))
        }, 700)
        break
      }

      case 'approval.request':
      case 'approval_request':
        store.pushMsg({
          role: 'approval',
          approval_id: data.approval_id as string,
          description: (data.description as string) ?? '需要审批',
          actions: (data.actions as Array<{ name: string; args: Record<string, unknown> }>) ?? [],
          content: '',
          _serverId: 'approval_' + String(data.approval_id ?? ''),
        })
        break

      case 'run.completed':
        if (data.run_id) {
          store.setCurrentRunId(data.run_id as string)
        }
        break

      case 'run.error':
      case 'error':
        store.pushMsg({
          role: 'assistant',
          content: '错误: ' + (data.error as string),
        })
        break

      case 'done':
        if (data.conversation_id) {
          store.setConversationId(data.conversation_id as string)
        }
        if (data.run_id) {
          store.setCurrentRunId(data.run_id as string)
        }
        break
    }
  }

  const cancel = useCallback(async () => {
    const state = useChatStore.getState()
    abortRef.current?.abort()
    if (state.currentRunId) {
      await fetch(`/api/agents/runs/${state.currentRunId}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ reason: '用户取消当前运行' }),
      }).catch(() => undefined)
    }
    store.setStreaming(false)
  }, [store])

  return { sendMessage, cancel }
}
