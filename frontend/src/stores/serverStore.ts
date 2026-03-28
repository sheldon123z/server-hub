import { create } from 'zustand'
import client from '@/api/client'

export interface Server {
  id: string
  name: string
  hostname: string
  ip_address: string
  agent_port: number
  ssh_user: string
  ssh_port: number
  status: string
  is_local: number | boolean
  tags: string | string[]
  groups: string
  last_heartbeat: string | null
  os_info: string | null
  agent_version: string | null
  created_at: string
  updated_at: string
}

interface ServerStore {
  servers: Server[]
  selectedServerId: string
  setSelectedServer: (id: string) => void
  fetchServers: () => Promise<void>
}

export const useServerStore = create<ServerStore>((set) => ({
  servers: [],
  selectedServerId: 'local',
  setSelectedServer: (id) => set({ selectedServerId: id }),
  fetchServers: async () => {
    try {
      const res = await client.get('/api/servers')
      const data = Array.isArray(res.data) ? res.data : res.data?.servers ?? []
      set({ servers: data })
    } catch {
      /* ignore */
    }
  },
}))
