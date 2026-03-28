import { create } from 'zustand'
import type { ChatMessage, TodoItem } from '@/types/agent'

interface ChatState {
  conversationId: string | null
  messages: ChatMessage[]
  todos: TodoItem[]
  isStreaming: boolean
  safetyMode: 'supervised' | 'autonomous'

  // Actions
  setConversationId: (id: string | null) => void
  addMessage: (msg: ChatMessage) => void
  setMessages: (msgs: ChatMessage[]) => void
  removeMessage: (id: string) => void
  removeMessagesFrom: (id: string) => void
  setTodos: (todos: TodoItem[]) => void
  setStreaming: (streaming: boolean) => void
  setSafetyMode: (mode: 'supervised' | 'autonomous') => void
  clearChat: () => void

  // Internal
  _msgSeq: number
  _seenIds: Set<string>
  pushMsg: (msg: Partial<ChatMessage>) => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversationId: null,
  messages: [],
  todos: [],
  isStreaming: false,
  safetyMode: 'supervised',

  _msgSeq: 0,
  _seenIds: new Set<string>(),

  setConversationId: (id) => set({ conversationId: id }),

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),

  setMessages: (msgs) => {
    const seen = new Set<string>()
    for (const m of msgs) {
      if (m._serverId) seen.add(m._serverId)
    }
    set({ messages: msgs, _seenIds: seen })
  },

  removeMessage: (id) =>
    set((s) => ({ messages: s.messages.filter((m) => m._id !== id) })),

  removeMessagesFrom: (id) =>
    set((s) => {
      const idx = s.messages.findIndex((m) => m._id === id)
      if (idx === -1) return s
      return { messages: s.messages.slice(0, idx) }
    }),

  setTodos: (todos) => set({ todos }),

  setStreaming: (streaming) => set({ isStreaming: streaming }),

  setSafetyMode: (mode) => set({ safetyMode: mode }),

  clearChat: () => {
    set({
      conversationId: null,
      messages: [],
      todos: [],
      isStreaming: false,
      _msgSeq: 0,
      _seenIds: new Set<string>(),
    })
  },

  pushMsg: (msg) => {
    const state = get()

    // Deduplicate by _serverId
    if (msg._serverId && state._seenIds.has(msg._serverId)) return

    const seq = state._msgSeq + 1
    const _id = msg._id ?? 's_' + seq

    const newMsg: ChatMessage = {
      _id,
      role: msg.role ?? 'assistant',
      content: msg.content ?? '',
      tool: msg.tool,
      args: msg.args,
      approval_id: msg.approval_id,
      description: msg.description,
      actions: msg.actions,
      _serverId: msg._serverId,
    }

    const newSeen = new Set(state._seenIds)
    if (msg._serverId) newSeen.add(msg._serverId)

    set({
      messages: [...state.messages, newMsg],
      _msgSeq: seq,
      _seenIds: newSeen,
    })
  },
}))
