import { create } from 'zustand'

export interface ArtifactItem {
  filePath: string
  action: 'write_file' | 'edit_file'
  content?: string
  timestamp: number
}

interface ArtifactState {
  artifacts: ArtifactItem[]
  selectedPath: string | null
  isOpen: boolean
  /** 用户手动切走标签后禁用自动切换 */
  _autoOpenUsed: boolean

  addArtifact: (item: ArtifactItem) => void
  setArtifacts: (items: ArtifactItem[]) => void
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
  _autoOpenUsed: false,

  addArtifact: (item) => {
    const state = get()
    // 去重: 同路径只保留最新条目
    const filtered = state.artifacts.filter((a) => a.filePath !== item.filePath)
    set({ artifacts: [...filtered, item] })
  },

  setArtifacts: (items) => set({ artifacts: items }),

  select: (path) => set({ selectedPath: path, isOpen: true }),

  deselect: () => set({ selectedPath: null }),

  setOpen: (open) => set({ isOpen: open }),

  clear: () =>
    set({
      artifacts: [],
      selectedPath: null,
      isOpen: false,
      _autoOpenUsed: false,
    }),

  markAutoOpenUsed: () => set({ _autoOpenUsed: true }),
}))
