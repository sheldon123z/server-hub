import { describe, it, expect, beforeEach } from 'vitest'
import { useArtifactStore, getPersistedConversationId } from '@/stores/artifactStore'
import type { ArtifactItem } from '@/stores/artifactStore'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function makeItem(filePath: string, action: ArtifactItem['action'] = 'write_file'): ArtifactItem {
  return { filePath, action, content: 'hello', timestamp: Date.now() }
}

function resetStore() {
  useArtifactStore.getState().clear()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('artifactStore', () => {
  beforeEach(() => {
    resetStore()
    sessionStorage.clear()
  })

  it('initial state has null conversationId and empty artifacts', () => {
    const state = useArtifactStore.getState()
    expect(state.conversationId).toBeNull()
    expect(state.artifacts).toEqual([])
    expect(state.selectedPath).toBeNull()
    expect(state.isOpen).toBe(false)
    expect(state._autoOpenUsed).toBe(false)
  })

  it('addArtifact adds item to artifacts list', () => {
    const item = makeItem('/srv/app.py')
    useArtifactStore.getState().addArtifact(item)
    expect(useArtifactStore.getState().artifacts).toHaveLength(1)
    expect(useArtifactStore.getState().artifacts[0].filePath).toBe('/srv/app.py')
  })

  it('addArtifact deduplicates by filePath, keeping latest entry', () => {
    const first = { ...makeItem('/srv/app.py'), content: 'first', timestamp: 1000 }
    const second = { ...makeItem('/srv/app.py'), content: 'second', timestamp: 2000 }
    useArtifactStore.getState().addArtifact(first)
    useArtifactStore.getState().addArtifact(second)
    const { artifacts } = useArtifactStore.getState()
    expect(artifacts).toHaveLength(1)
    expect(artifacts[0].content).toBe('second')
  })

  it('addArtifact keeps different file paths as separate items', () => {
    useArtifactStore.getState().addArtifact(makeItem('/a.py'))
    useArtifactStore.getState().addArtifact(makeItem('/b.py'))
    expect(useArtifactStore.getState().artifacts).toHaveLength(2)
  })

  it('select sets selectedPath and isOpen to true', () => {
    useArtifactStore.getState().select('/srv/app.py')
    const state = useArtifactStore.getState()
    expect(state.selectedPath).toBe('/srv/app.py')
    expect(state.isOpen).toBe(true)
  })

  it('deselect resets selectedPath to null and isOpen to false', () => {
    useArtifactStore.getState().select('/srv/app.py')
    useArtifactStore.getState().deselect()
    const state = useArtifactStore.getState()
    expect(state.selectedPath).toBeNull()
    expect(state.isOpen).toBe(false)
  })

  it('setArtifactsForConversation atomically sets conversationId, artifacts, and resets selection', () => {
    // Arrange: pre-populate some selection state
    useArtifactStore.getState().select('/old.py')
    const items = [makeItem('/new.ts', 'edit_file')]

    useArtifactStore.getState().setArtifactsForConversation('conv-123', items)

    const state = useArtifactStore.getState()
    expect(state.conversationId).toBe('conv-123')
    expect(state.artifacts).toEqual(items)
    expect(state.selectedPath).toBeNull()
    expect(state.isOpen).toBe(false)
    expect(state._autoOpenUsed).toBe(false)
  })

  it('setArtifactsForConversation writes conversationId to sessionStorage', () => {
    useArtifactStore.getState().setArtifactsForConversation('conv-abc', [])
    expect(sessionStorage.getItem('serverhub-artifact-conversation-id')).toBe('conv-abc')
  })

  it('clear resets everything including conversationId', () => {
    useArtifactStore.getState().setArtifactsForConversation('conv-xyz', [makeItem('/x.py')])
    useArtifactStore.getState().select('/x.py')
    useArtifactStore.getState().markAutoOpenUsed()

    useArtifactStore.getState().clear()

    const state = useArtifactStore.getState()
    expect(state.conversationId).toBeNull()
    expect(state.artifacts).toEqual([])
    expect(state.selectedPath).toBeNull()
    expect(state.isOpen).toBe(false)
    expect(state._autoOpenUsed).toBe(false)
  })

  it('clear removes conversationId from sessionStorage', () => {
    sessionStorage.setItem('serverhub-artifact-conversation-id', 'conv-xyz')
    useArtifactStore.getState().clear()
    expect(sessionStorage.getItem('serverhub-artifact-conversation-id')).toBeNull()
  })

  it('getPersistedConversationId reads from sessionStorage correctly', () => {
    sessionStorage.setItem('serverhub-artifact-conversation-id', 'persisted-id')
    expect(getPersistedConversationId()).toBe('persisted-id')
  })

  it('getPersistedConversationId returns null when sessionStorage has no entry', () => {
    sessionStorage.clear()
    expect(getPersistedConversationId()).toBeNull()
  })

  it('markAutoOpenUsed sets _autoOpenUsed to true', () => {
    expect(useArtifactStore.getState()._autoOpenUsed).toBe(false)
    useArtifactStore.getState().markAutoOpenUsed()
    expect(useArtifactStore.getState()._autoOpenUsed).toBe(true)
  })

  it('setOpen sets isOpen without changing selectedPath', () => {
    useArtifactStore.getState().select('/some.py')
    useArtifactStore.getState().setOpen(false)
    const state = useArtifactStore.getState()
    expect(state.isOpen).toBe(false)
    expect(state.selectedPath).toBe('/some.py')
  })
})
