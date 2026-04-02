import { useCallback, useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useChatStore } from '@/stores/chatStore'
import type { TodoItem, UIComponentType, UIComponentData, UIAction, UIComponentMessage } from '@/types/agent'
import { ensureArray } from '@/lib/utils'

function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

/** Module-level singleton: ensures only one active SSE request across all hook instances */
let _activeController: AbortController | null = null
let _activeSubscribers = 0

interface SendMessageOptions {
  pageContext?: string
  skillId?: string | null
}

export function useSSEChat() {
  const store = useChatStore()
  const queryClient = useQueryClient()
  const mountedRef = useRef(false)

  useEffect(() => {
    mountedRef.current = true
    _activeSubscribers++
    return () => {
      mountedRef.current = false
      _activeSubscribers--
      // Only abort if this is the last subscriber and no other instance is mounted
      if (_activeSubscribers <= 0) {
        _activeController?.abort()
        _activeController = null
        _activeSubscribers = 0
      }
    }
  }, [])

  const sendMessage = useCallback(
    async (text: string, options?: SendMessageOptions) => {
      const state = useChatStore.getState()
      // Abort any existing request (singleton across all instances)
      _activeController?.abort()
      const controller = new AbortController()
      _activeController = controller

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
        if (_activeController === controller) {
          _activeController = null
        }
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
        .map((block: unknown) => {
          if (typeof block === 'string') return block
          if (block && typeof block === 'object' && 'type' in block && 'text' in block) {
            const b = block as { type: string; text: string }
            if (b.type === 'text' && typeof b.text === 'string') return b.text
          }
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
        const items = ensureArray<TodoItem>(Array.isArray(data) ? data : data.todos ?? [])
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
          actions: ensureArray<{ name: string; args: Record<string, unknown> }>(data.actions),
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

      case 'ui.render':
        store.pushMsg({
          role: 'ui_component' as const,
          componentType: data.component_type as UIComponentType,
          data: data.data as UIComponentData,
          uiActions: (data.actions as UIAction[]) ?? [],
          content: '',
          _serverId: data.id as string | undefined,
        } as Parameters<typeof store.pushMsg>[0])
        break

      case 'ui.update': {
        const componentId = data.component_id as string
        const updateType = data.update_type as string
        const updateData = data.data as Record<string, unknown>
        const msgs = [...useChatStore.getState().messages]
        const idx = msgs.findIndex(
          (m) => m.role === 'ui_component' && (m as UIComponentMessage).data?.id === componentId,
        )
        if (idx !== -1) {
          const existing = msgs[idx] as UIComponentMessage
          msgs[idx] = {
            ...existing,
            data:
              updateType === 'replace'
                ? { ...existing.data, ...updateData }
                : updateType === 'clear'
                  ? { ...existing.data, data: undefined }
                  : existing.data,
          } as UIComponentMessage
          useChatStore.getState().setMessages(msgs)
        }
        break
      }

      case 'ui.remove': {
        const removeId = data.component_id as string
        const currentMsgs = useChatStore.getState().messages.filter(
          (m) => !(m.role === 'ui_component' && (m as UIComponentMessage).data?.id === removeId),
        )
        useChatStore.getState().setMessages(currentMsgs)
        break
      }

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
    _activeController?.abort()
    _activeController = null
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
