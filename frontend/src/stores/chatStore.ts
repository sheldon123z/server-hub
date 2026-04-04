import { create } from 'zustand'
import type { ChatMessage, TodoItem } from '@/types/agent'
import { ensureArray } from '@/lib/utils'
import { useArtifactStore } from '@/stores/artifactStore'

interface ChatState {
  conversationId: string | null
  currentRunId: string | null
  messages: ChatMessage[]
  todos: TodoItem[]
  isStreaming: boolean
  safetyMode: 'supervised' | 'autonomous'
  selectedSkillId: string | null

  // Actions
  setConversationId: (id: string | null) => void
  setCurrentRunId: (id: string | null) => void
  addMessage: (msg: ChatMessage) => void
  setMessages: (msgs: ChatMessage[]) => void
  removeMessage: (id: string) => void
  removeMessagesFrom: (id: string) => void
  setTodos: (todos: TodoItem[]) => void
  setStreaming: (streaming: boolean) => void
  setSafetyMode: (mode: 'supervised' | 'autonomous') => void
  setSelectedSkillId: (id: string | null) => void
  clearChat: () => void

  // Internal
  _msgSeq: number
  _seenIds: Set<string>
  pushMsg: (msg: Partial<ChatMessage> & Record<string, unknown>) => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversationId: null,
  currentRunId: null,
  messages: [],
  todos: [],
  isStreaming: false,
  safetyMode: 'supervised',
  selectedSkillId: null,

  _msgSeq: 0,
  _seenIds: new Set<string>(),

  setConversationId: (id) => set({ conversationId: id }),
  setCurrentRunId: (id) => set({ currentRunId: id }),

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),

  setMessages: (msgs) => {
    const seen = new Set<string>()
    const safeMessages = ensureArray<ChatMessage>(msgs)
    for (const m of safeMessages) {
      if (m._serverId) seen.add(m._serverId)
    }
    set({ messages: safeMessages, _seenIds: seen })
  },

  removeMessage: (id) =>
    set((s) => ({ messages: s.messages.filter((m) => m._id !== id) })),

  removeMessagesFrom: (id) =>
    set((s) => {
      const idx = s.messages.findIndex((m) => m._id === id)
      if (idx === -1) return s
      return { messages: s.messages.slice(0, idx) }
    }),

  setTodos: (todos) => set({ todos: ensureArray<TodoItem>(todos) }),

  setStreaming: (streaming) => set({ isStreaming: streaming }),

  setSafetyMode: (mode) => set({ safetyMode: mode }),

  setSelectedSkillId: (id) => set({ selectedSkillId: id }),

  clearChat: () => {
    set({
      conversationId: null,
      currentRunId: null,
      messages: [],
      todos: [],
      isStreaming: false,
      selectedSkillId: null,
      _msgSeq: 0,
      _seenIds: new Set<string>(),
    })
    // 联动清理 artifacts
    useArtifactStore.getState().clear()
  },

  pushMsg: (msg) => {
    const state = get()

    // Deduplicate by _serverId
    if (msg._serverId && state._seenIds.has(msg._serverId as string)) return

    const seq = state._msgSeq + 1
    const _id = (msg._id as string) ?? 's_' + seq

    const newMsg: ChatMessage & Record<string, unknown> = {
      _id,
      role: (msg.role as ChatMessage['role']) ?? 'assistant',
      content: (msg.content as string) ?? '',
      tool: msg.tool as string | undefined,
      args: msg.args as Record<string, unknown> | undefined,
      approval_id: msg.approval_id as string | undefined,
      description: msg.description as string | undefined,
      actions: Array.isArray(msg.actions) ? msg.actions : undefined,
      _serverId: msg._serverId as string | undefined,
    }

    // A to UI: 透传 UI 组件字段
    if (msg.role === 'ui_component') {
      newMsg.componentType = msg.componentType
      newMsg.data = msg.data
      newMsg.uiActions = msg.uiActions
    }

    const newSeen = new Set(state._seenIds)
    if (msg._serverId) newSeen.add(msg._serverId as string)

    set({
      messages: [...state.messages, newMsg as unknown as ChatMessage],
      _msgSeq: seq,
      _seenIds: newSeen,
    })
  },
}))
