import { create } from 'zustand'

export interface ArtifactItem {
  filePath: string
  action: 'write_file' | 'edit_file'
  content?: string
  timestamp: number
}

const STORAGE_KEY_CONV_ID = 'serverhub-artifact-conversation-id'

/** 读取持久化的 conversationId（供外部调用） */
export function getPersistedConversationId(): string | null {
  return sessionStorage.getItem(STORAGE_KEY_CONV_ID)
}

interface ArtifactState {
  artifacts: ArtifactItem[]
  selectedPath: string | null
  isOpen: boolean
  conversationId: string | null
  /** 用户手动切走标签后禁用自动切换 */
  _autoOpenUsed: boolean

  addArtifact: (item: ArtifactItem) => void
  setArtifacts: (items: ArtifactItem[]) => void
  setArtifactsForConversation: (conversationId: string, items: ArtifactItem[]) => void
  select: (path: string) => void
  deselect: () => void
  setOpen: (open: boolean) => void
  clear: () => void
  markAutoOpenUsed: () => void
}

export const useArtifactStore = create<ArtifactState>((set, get) => ({
  artifacts: [],
  selectedPath: null,
  isOpen: false,
  conversationId: null,
  _autoOpenUsed: false,

  addArtifact: (item) => {
    const state = get()
    // 去重: 同路径只保留最新条目
    const filtered = state.artifacts.filter((a) => a.filePath !== item.filePath)
    set({ artifacts: [...filtered, item] })
  },

  setArtifacts: (items) => set({ artifacts: items }),

  setArtifactsForConversation: (conversationId, items) => {
    sessionStorage.setItem(STORAGE_KEY_CONV_ID, conversationId)
    set({
      conversationId,
      artifacts: items,
      selectedPath: null,
      isOpen: false,
      _autoOpenUsed: false,
    })
  },

  select: (path) => set({ selectedPath: path, isOpen: true }),

  deselect: () => set({ selectedPath: null, isOpen: false }),

  setOpen: (open) => set({ isOpen: open }),

  clear: () => {
    sessionStorage.removeItem(STORAGE_KEY_CONV_ID)
    set({
      artifacts: [],
      selectedPath: null,
      isOpen: false,
      conversationId: null,
      _autoOpenUsed: false,
    })
  },

  markAutoOpenUsed: () => set({ _autoOpenUsed: true }),
}))
