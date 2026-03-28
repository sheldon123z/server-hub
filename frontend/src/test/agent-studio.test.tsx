import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import client from '@/api/client'
import AgentStudioPage from '@/pages/agents/AgentStudioPage'

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

const mockedClient = vi.mocked(client, true)

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
}

function renderWithProviders(ui: ReactNode) {
  const queryClient = createQueryClient()
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('AgentStudioPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    mockedClient.get.mockImplementation((url: string) => {
      switch (url) {
        case '/api/agents/admin/skills':
          return Promise.resolve({
            data: {
              skills: [
                {
                  id: 'incident-local',
                  name: 'Incident Local',
                  summary: 'Handle incidents',
                  version: '1.0.0',
                  enabled: true,
                  source_type: 'repo',
                },
              ],
            },
          })
        case '/api/agents/runs':
          return Promise.resolve({
            data: [
              {
                id: 'run-1',
                user_message: 'inspect dashboard',
                status: 'error',
                page_context: 'dashboard',
                skill_id: 'incident-local',
              },
            ],
          })
        case '/api/agents/approvals':
          return Promise.resolve({ data: [{ id: 'approval-1', description: 'restart nginx', created_at: 'now' }] })
        case '/api/agents/admin/skill-sources':
          return Promise.resolve({ data: { roots: ['/repo/skills'] } })
        case '/api/agents/admin/subagents':
          return Promise.resolve({
            data: { subagents: [{ name: 'Incident Commander', description: 'Triage incidents', tools: ['think'] }] },
          })
        case '/api/agents/admin/prompt':
          return Promise.resolve({ data: { content: 'system prompt' } })
        case '/api/agents/admin/memory':
          return Promise.resolve({ data: { content: 'memory state' } })
        default:
          return Promise.resolve({ data: {} })
      }
    })

    mockedClient.post.mockImplementation((url: string) => {
      switch (url) {
        case '/api/agents/admin/skills/discover':
          return Promise.resolve({
            data: {
              items: [
                {
                  path: '/repo/skills/fleet-local',
                  installed: false,
                  manifest: {
                    id: 'fleet-local',
                    name: 'Fleet Local',
                    summary: 'Investigate fleet issues',
                  },
                },
              ],
            },
          })
        case '/api/agents/admin/skills/install-from-repo':
          return Promise.resolve({ data: { ok: true } })
        default:
          return Promise.resolve({ data: { ok: true } })
      }
    })

    mockedClient.put.mockResolvedValue({ data: { roots: ['/repo/skills', '/extra/skills'] } })
    mockedClient.delete.mockResolvedValue({ data: { ok: true } })
  })

  it('renders overview metrics from admin data', async () => {
    renderWithProviders(<AgentStudioPage />)

    expect(await screen.findByText('Agent Studio')).toBeInTheDocument()
    expect(await screen.findByText('启用技能')).toBeInTheDocument()
    expect(screen.getByText('1 个已安装')).toBeInTheDocument()
    expect(screen.getByText('失败运行')).toBeInTheDocument()
    expect(screen.getByText('待处理审批')).toBeInTheDocument()
  })

  it('supports install tab interactions for saving roots and repo install', async () => {
    renderWithProviders(<AgentStudioPage />)

    fireEvent.click(await screen.findByText('Install'))
    expect(await screen.findByText('Repo 路径安装')).toBeInTheDocument()
    expect(await screen.findByText('发现结果')).toBeInTheDocument()
    expect(await screen.findByText('Fleet Local')).toBeInTheDocument()

    const repoInput = screen.getByPlaceholderText('/path/to/skill')
    fireEvent.change(repoInput, { target: { value: '/repo/skills/fleet-local' } })
    fireEvent.click(screen.getByText('安装'))

    await waitFor(() => {
      expect(mockedClient.post).toHaveBeenCalledWith('/api/agents/admin/skills/install-from-repo', {
        repo_path: '/repo/skills/fleet-local',
      })
    })

    const rootsTextarea = screen.getByDisplayValue('/repo/skills')
    fireEvent.change(rootsTextarea, { target: { value: '/repo/skills\n/extra/skills' } })
    fireEvent.click(screen.getByText('保存扫描源'))

    await waitFor(() => {
      expect(mockedClient.put).toHaveBeenCalledWith('/api/agents/admin/skill-sources', {
        roots: ['/repo/skills', '/extra/skills'],
      })
    })
  })
})
