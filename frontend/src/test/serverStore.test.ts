import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useServerStore } from '@/stores/serverStore'

// ---------------------------------------------------------------------------
// Mock the API client at module level (outside describe) using vi.hoisted
// ---------------------------------------------------------------------------
const { mockGet } = vi.hoisted(() => ({
  mockGet: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  default: { get: (...args: any[]) => mockGet(...args) },
}))

// ---------------------------------------------------------------------------
// Helper: reset store state
// ---------------------------------------------------------------------------
function resetStore() {
  useServerStore.setState({ servers: [], selectedServerId: 'local' })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('useServerStore', () => {
  beforeEach(() => {
    resetStore()
    mockGet.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ---------------------------------------------------------------------------
  // Initial state
  // ---------------------------------------------------------------------------
  describe('initial state', () => {
    it('has selectedServerId "local"', () => {
      const { selectedServerId } = useServerStore.getState()
      expect(selectedServerId).toBe('local')
    })

    it('has empty servers array', () => {
      const { servers } = useServerStore.getState()
      expect(servers).toEqual([])
    })
  })

  // ---------------------------------------------------------------------------
  // setSelectedServer
  // ---------------------------------------------------------------------------
  describe('setSelectedServer', () => {
    it('updates selectedServerId', () => {
      useServerStore.getState().setSelectedServer('server-42')
      expect(useServerStore.getState().selectedServerId).toBe('server-42')
    })

    it('can switch back to "local"', () => {
      useServerStore.getState().setSelectedServer('remote-1')
      useServerStore.getState().setSelectedServer('local')
      expect(useServerStore.getState().selectedServerId).toBe('local')
    })

    it('does not affect servers array', () => {
      const mockServers = [{ id: 's1', name: 'Server 1' }] as any
      useServerStore.setState({ servers: mockServers })
      useServerStore.getState().setSelectedServer('other')
      expect(useServerStore.getState().servers).toEqual(mockServers)
    })
  })

  // ---------------------------------------------------------------------------
  // fetchServers — actually calls the real fetchServers()
  // ---------------------------------------------------------------------------
  describe('fetchServers', () => {
    it('sets servers from array response', async () => {
      const mockData = [
        { id: 'local', name: 'Local', hostname: 'h1', status: 'online' },
        { id: 'remote', name: 'Remote', hostname: 'h2', status: 'offline' },
      ]
      mockGet.mockResolvedValue({ data: mockData })
      await useServerStore.getState().fetchServers()
      expect(mockGet).toHaveBeenCalledWith('/api/servers')
      expect(useServerStore.getState().servers).toEqual(mockData)
      expect(useServerStore.getState().servers).toHaveLength(2)
    })

    it('unwraps { servers: [...] } response shape', async () => {
      const apiResponse = {
        servers: [
          { id: 'local', name: 'Local', hostname: 'h1', status: 'online' },
        ],
      }
      mockGet.mockResolvedValue({ data: apiResponse })
      await useServerStore.getState().fetchServers()
      expect(useServerStore.getState().servers).toHaveLength(1)
      expect(useServerStore.getState().servers[0].id).toBe('local')
    })

    it('handles empty response gracefully', async () => {
      // Set non-empty state first to verify it gets cleared correctly
      const existingServers = [{ id: 's1', name: 'Server 1' }] as any
      useServerStore.setState({ servers: existingServers })

      mockGet.mockResolvedValue({ data: null })
      await useServerStore.getState().fetchServers()
      expect(useServerStore.getState().servers).toEqual([])
    })

    it('keeps state stable on API error', async () => {
      // Set non-empty state first to verify preservation on error
      const existingServers = [{ id: 's1', name: 'Server 1' }] as any
      useServerStore.setState({ servers: existingServers })

      mockGet.mockRejectedValue(new Error('Network error'))
      // fetchServers catches internally — state should remain unchanged
      await useServerStore.getState().fetchServers()
      expect(useServerStore.getState().servers).toEqual(existingServers)
    })
  })

  // ---------------------------------------------------------------------------
  // getState / setState interop
  // ---------------------------------------------------------------------------
  describe('Zustand interop', () => {
    it('getState returns current state snapshot', () => {
      useServerStore.setState({ selectedServerId: 'abc' })
      const state = useServerStore.getState()
      expect(state.selectedServerId).toBe('abc')
    })

    it('setState merges partial state', () => {
      useServerStore.setState({ selectedServerId: 'x' })
      useServerStore.setState({ servers: [{ id: 'y' }] as any })
      expect(useServerStore.getState().selectedServerId).toBe('x')
      expect(useServerStore.getState().servers).toHaveLength(1)
    })

    it('subscribe notifies on state change', () => {
      const listener = vi.fn()
      const unsub = useServerStore.subscribe(listener)
      useServerStore.setState({ selectedServerId: 'new-id' })
      expect(listener).toHaveBeenCalledTimes(1)
      unsub()
    })
  })
})
