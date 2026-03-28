import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import client from '@/api/client'
import { useSSEChat } from '@/hooks/useSSEChat'
import { ChatPanel } from '@/pages/agents/ChatPanel'
import { useChatStore } from '@/stores/chatStore'

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

function renderWithProviders(ui: ReactNode, route = '/dashboard') {
  const queryClient = createQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="*" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function buildSSEPayload() {
  return [
    'event: run.started',
    'data: {"run_id":"run-1","conversation_id":"conv-1"}',
    '',
    'event: todo.update',
    'data: {"todos":[{"content":"collect metrics","status":"completed"}]}',
    '',
    'event: message.final',
    'data: {"content":"诊断完成","id":"msg-1"}',
    '',
    'event: run.completed',
    'data: {"run_id":"run-1"}',
    '',
    'event: done',
    'data: {"conversation_id":"conv-1","run_id":"run-1"}',
    '',
  ].join('\n')
}

function buildStreamResponse(payload: string) {
  const encoder = new TextEncoder()
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload))
        controller.close()
      },
    }),
    {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    },
  )
}

function HookHarness() {
  const { sendMessage, cancel } = useSSEChat()
  const { messages, todos, currentRunId, isStreaming } = useChatStore()

  return (
    <div>
      <button onClick={() => sendMessage('please inspect', { pageContext: 'dashboard', skillId: 'incident-local' })}>
        send
      </button>
      <button onClick={() => void cancel()}>cancel</button>
      <div data-testid="run-id">{currentRunId ?? ''}</div>
      <div data-testid="streaming">{String(isStreaming)}</div>
      {messages.map((message) => (
        <div key={message._id}>{message.content || message.tool}</div>
      ))}
      {todos.map((todo) => (
        <div key={todo.content}>{todo.content + ':' + todo.status}</div>
      ))}
    </div>
  )
}

describe('agent runtime frontend', () => {
  beforeEach(() => {
    useChatStore.getState().clearChat()
    vi.clearAllMocks()
  })

  it('parses SSE events, updates store and posts selected skill context', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(buildStreamResponse(buildSSEPayload()))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(<HookHarness />)

    await act(async () => {
      fireEvent.click(screen.getByText('send'))
    })

    await screen.findByText('诊断完成')
    await screen.findByText('collect metrics:completed')
    expect(screen.getByTestId('run-id').textContent).toBe('run-1')

    const request = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/agents/chat')
    expect(request.skill_id).toBe('incident-local')
    expect(request.page_context).toBe('dashboard')
    expect(request.message).toBe('please inspect')

    useChatStore.getState().setCurrentRunId('run-1')
    await act(async () => {
      fireEvent.click(screen.getByText('cancel'))
    })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/agents/runs/run-1/cancel',
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('shows recommendation chips and sends selected skill with page context', async () => {
    mockedClient.get.mockResolvedValue({
      data: {
        items: [
          {
            id: 'incident-local',
            name: 'Incident Local',
            summary: 'Handle dashboard incidents',
            score: 5,
            reasons: ['适配页面 dashboard'],
          },
        ],
      },
    })

    const sendMessage = vi.fn()
    const hookSpy = vi.spyOn(await import('@/hooks/useSSEChat'), 'useSSEChat').mockReturnValue({
      sendMessage,
      cancel: vi.fn(),
    })

    renderWithProviders(<ChatPanel />)

    const textarea = screen.getByPlaceholderText('输入消息... (Shift+Enter 换行)')
    fireEvent.change(textarea, { target: { value: 'incident on dashboard' } })

    await screen.findByText('Incident Local')
    fireEvent.click(screen.getByText('Incident Local'))
    expect(screen.getByText('Handle dashboard incidents')).toBeInTheDocument()

    fireEvent.click(screen.getByTitle('发送'))

    expect(sendMessage).toHaveBeenCalledWith('incident on dashboard', {
      pageContext: 'dashboard',
      skillId: 'incident-local',
    })

    hookSpy.mockRestore()
  })
})
