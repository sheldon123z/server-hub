import { describe, it, expect, beforeEach } from 'vitest'
import { useArtifactStore } from '@/stores/artifactStore'
import type { ArtifactItem } from '@/stores/artifactStore'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function makeItem(filePath: string, action: ArtifactItem['action'] = 'write_file'): ArtifactItem {
  return { filePath, action, content: filePath, timestamp: Date.now() }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('artifact conversation isolation', () => {
  beforeEach(() => {
    useArtifactStore.getState().clear()
    sessionStorage.clear()
  })

  it('switching conversations replaces artifacts atomically', () => {
    const itemA = makeItem('/conv-a/main.py')
    const itemB = makeItem('/conv-b/server.ts')

    useArtifactStore.getState().setArtifactsForConversation('conv-A', [itemA])
    useArtifactStore.getState().setArtifactsForConversation('conv-B', [itemB])

    const state = useArtifactStore.getState()
    expect(state.conversationId).toBe('conv-B')
    expect(state.artifacts).toHaveLength(1)
    expect(state.artifacts[0].filePath).toBe('/conv-b/server.ts')
  })

  it('artifacts from conversation A do not appear in conversation B', () => {
    const itemA = makeItem('/a/file.py')
    const itemB = makeItem('/b/other.ts')

    useArtifactStore.getState().setArtifactsForConversation('conv-A', [itemA])
    // Verify conv-A artifacts are present
    expect(useArtifactStore.getState().artifacts.some((a) => a.filePath === '/a/file.py')).toBe(true)

    // Switch to conv-B
    useArtifactStore.getState().setArtifactsForConversation('conv-B', [itemB])

    const { artifacts } = useArtifactStore.getState()
    expect(artifacts.some((a) => a.filePath === '/a/file.py')).toBe(false)
    expect(artifacts.some((a) => a.filePath === '/b/other.ts')).toBe(true)
  })

  it('clear on new conversation resets conversationId', () => {
    useArtifactStore.getState().setArtifactsForConversation('conv-A', [makeItem('/a.py')])
    expect(useArtifactStore.getState().conversationId).toBe('conv-A')

    useArtifactStore.getState().clear()

    const state = useArtifactStore.getState()
    expect(state.conversationId).toBeNull()
    expect(state.artifacts).toEqual([])
  })

  it('sessionStorage reflects the most recent conversation after switch', () => {
    useArtifactStore.getState().setArtifactsForConversation('conv-A', [])
    useArtifactStore.getState().setArtifactsForConversation('conv-B', [])
    expect(sessionStorage.getItem('serverhub-artifact-conversation-id')).toBe('conv-B')
  })

  it('selection state is cleared when switching conversations', () => {
    const itemA = makeItem('/a/app.py')
    useArtifactStore.getState().setArtifactsForConversation('conv-A', [itemA])
    useArtifactStore.getState().select('/a/app.py')
    expect(useArtifactStore.getState().isOpen).toBe(true)

    // Switch to different conversation
    useArtifactStore.getState().setArtifactsForConversation('conv-B', [])

    const state = useArtifactStore.getState()
    expect(state.selectedPath).toBeNull()
    expect(state.isOpen).toBe(false)
  })

  it('multiple artifacts from same conversation are all present after set', () => {
    const items = [
      makeItem('/a.py'),
      makeItem('/b.ts'),
      makeItem('/c.sh'),
    ]
    useArtifactStore.getState().setArtifactsForConversation('conv-multi', items)
    expect(useArtifactStore.getState().artifacts).toHaveLength(3)
    expect(useArtifactStore.getState().conversationId).toBe('conv-multi')
  })
})
