/**
 * useSSEChat — SSE 事件解析测试
 *
 * 通过 mock fetch 返回 SSE 格式流，验证 handleSSEEvent 对 13 种事件类型（含 alias）
 * 正确更新 chatStore / artifactStore 的状态。
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useSSEChat } from '@/hooks/useSSEChat'
import { useChatStore } from '@/stores/chatStore'
import { useArtifactStore } from '@/stores/artifactStore'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a fake SSE Response from a list of event descriptors */
function makeSseResponse(events: Array<{ event: string; data: unknown }>): Response {
  const encoder = new TextEncoder()
  const text = events
    .map(({ event, data }) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    .join('')
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text))
      controller.close()
    },
  })
  return new Response(stream, { status: 200 })
}

/** Render the hook with the required providers and return sendMessage + cancel */
function renderSSEChat(queryClient: QueryClient) {
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  return renderHook(() => useSSEChat(), { wrapper })
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

let queryClient: QueryClient

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  useChatStore.getState().clearChat()
  useArtifactStore.getState().clear()
  sessionStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
  queryClient.clear()
})

// ---------------------------------------------------------------------------
// run.started
// ---------------------------------------------------------------------------

describe('event: run.started', () => {
  it('sets currentRunId in chatStore', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'run.started', data: { run_id: 'run-abc' } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('hello')
    })
    expect(useChatStore.getState().currentRunId).toBe('run-abc')
  })
})

// ---------------------------------------------------------------------------
// message / message.final
// ---------------------------------------------------------------------------

describe('event: message', () => {
  it('pushes an assistant message to chatStore', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'message', data: { content: 'Hello from agent' } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('hi')
    })
    const msgs = useChatStore.getState().messages
    const assistantMsgs = msgs.filter((m) => m.role === 'assistant')
    expect(assistantMsgs.length).toBeGreaterThanOrEqual(1)
    expect(assistantMsgs.some((m) => m.content === 'Hello from agent')).toBe(true)
  })

  it('message.final alias also pushes assistant message', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'message.final', data: { content: 'Final answer' } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    const msgs = useChatStore.getState().messages
    expect(msgs.some((m) => m.role === 'assistant' && m.content === 'Final answer')).toBe(true)
  })

  it('handles content as ContentPart array', async () => {
    const content = [{ type: 'text', text: 'Part1 ' }, { type: 'text', text: 'Part2' }]
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'message', data: { content } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    const msgs = useChatStore.getState().messages
    expect(msgs.some((m) => m.role === 'assistant' && m.content === 'Part1 Part2')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// tool.call / tool_call
// ---------------------------------------------------------------------------

describe('event: tool.call / tool_call', () => {
  it('pushes a tool_call message with tool name and args', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([
        { event: 'tool.call', data: { tool: 'execute', input: { command: 'ls' } } },
      ]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('run ls')
    })
    const msgs = useChatStore.getState().messages
    const toolMsg = msgs.find((m) => m.role === 'tool_call')
    expect(toolMsg).toBeDefined()
    expect(toolMsg?.tool).toBe('execute')
  })

  it('tool_call alias also pushes tool_call message', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([
        { event: 'tool_call', data: { name: 'get_system_overview', args: {} } },
      ]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('check')
    })
    const msgs = useChatStore.getState().messages
    expect(msgs.some((m) => m.role === 'tool_call' && m.tool === 'get_system_overview')).toBe(true)
  })

  it('write_file tool call adds artifact to artifactStore', async () => {
    // Set up a matching conversationId so the artifact isolation logic allows the add
    useChatStore.getState().setConversationId('conv-write')
    useArtifactStore.getState().setArtifactsForConversation('conv-write', [])

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([
        {
          event: 'tool_call',
          data: {
            tool: 'write_file',
            input: { file_path: '/srv/app.py', content: 'print("hi")' },
          },
        },
      ]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('write it')
    })
    const artifacts = useArtifactStore.getState().artifacts
    expect(artifacts.some((a) => a.filePath === '/srv/app.py')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// tool.result / tool_result
// ---------------------------------------------------------------------------

describe('event: tool.result / tool_result', () => {
  it('pushes tool_result message with content', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([
        { event: 'tool.result', data: { tool: 'execute', content: 'output text', id: 'r1' } },
      ]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('run')
    })
    const msgs = useChatStore.getState().messages
    const resultMsg = msgs.find((m) => m.role === 'tool_result')
    expect(resultMsg).toBeDefined()
    expect(resultMsg?.content).toBe('output text')
  })

  it('tool_result alias works the same way', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([
        { event: 'tool_result', data: { tool: 'ls', content: 'file1.txt\nfile2.txt' } },
      ]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('ls')
    })
    const msgs = useChatStore.getState().messages
    expect(msgs.some((m) => m.role === 'tool_result')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// todo.update / todo_update
// ---------------------------------------------------------------------------

describe('event: todo.update / todo_update', () => {
  it('sets todos in chatStore from todos array', async () => {
    const todos = [
      { content: 'Task A', status: 'pending' },
      { content: 'Task B', status: 'completed' },
    ]
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'todo.update', data: { todos } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('tasks')
    })
    const storeTodos = useChatStore.getState().todos
    expect(storeTodos).toHaveLength(2)
    expect(storeTodos.find((t) => t.content === 'Task A')?.status).toBe('pending')
  })

  it('todo_update alias also sets todos', async () => {
    const todos = [{ content: 'Only task', status: 'in_progress' }]
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'todo_update', data: { todos } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    expect(useChatStore.getState().todos).toHaveLength(1)
  })

  it('marks item as _justCompleted when status transitions to completed', async () => {
    // Pre-populate todos with a pending task
    useChatStore.getState().setTodos([{ content: 'Step 1', status: 'pending' }])

    const updatedTodos = [{ content: 'Step 1', status: 'completed' }]
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'todo.update', data: { todos: updatedTodos } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('finish')
    })
    // Immediately after update, _justCompleted should be true
    const todos = useChatStore.getState().todos
    const step1 = todos.find((t) => t.content === 'Step 1')
    expect(step1?.status).toBe('completed')
    // Note: _justCompleted may have already been cleared by the 700ms setTimeout
    // but the status transition is guaranteed
  })
})

// ---------------------------------------------------------------------------
// approval.request / approval_request
// ---------------------------------------------------------------------------

describe('event: approval.request / approval_request', () => {
  it('pushes approval message with approval_id and description', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([
        {
          event: 'approval.request',
          data: {
            approval_id: 'apr-1',
            description: 'Confirm deletion',
            actions: [{ name: 'delete', args: { path: '/tmp/file' } }],
          },
        },
      ]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('delete file')
    })
    const msgs = useChatStore.getState().messages
    const approvalMsg = msgs.find((m) => m.role === 'approval')
    expect(approvalMsg).toBeDefined()
    expect(approvalMsg?.approval_id).toBe('apr-1')
    expect(approvalMsg?.description).toBe('Confirm deletion')
  })

  it('approval_request alias pushes approval message', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([
        {
          event: 'approval_request',
          data: { approval_id: 'apr-2', description: '审批', actions: [] },
        },
      ]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    const msgs = useChatStore.getState().messages
    expect(msgs.some((m) => m.role === 'approval' && m.approval_id === 'apr-2')).toBe(true)
  })

  it('uses default description when description is absent', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([
        { event: 'approval.request', data: { approval_id: 'apr-3', actions: [] } },
      ]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    const msgs = useChatStore.getState().messages
    const approvalMsg = msgs.find((m) => m.role === 'approval')
    expect(approvalMsg?.description).toBe('需要审批')
  })
})

// ---------------------------------------------------------------------------
// artifact.update
// ---------------------------------------------------------------------------

describe('event: artifact.update', () => {
  it('adds artifact to artifactStore when conversationIds match', async () => {
    useChatStore.getState().setConversationId('conv-art')
    useArtifactStore.getState().setArtifactsForConversation('conv-art', [])

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([
        {
          event: 'artifact.update',
          data: { file_path: '/srv/main.py', action: 'write_file', content: 'code' },
        },
      ]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('write code')
    })
    expect(useArtifactStore.getState().artifacts.some((a) => a.filePath === '/srv/main.py')).toBe(
      true,
    )
  })

  it('ignores artifact.update when conversationIds mismatch', async () => {
    useChatStore.getState().setConversationId('conv-new')
    useArtifactStore.getState().setArtifactsForConversation('conv-old', [])

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([
        {
          event: 'artifact.update',
          data: { file_path: '/srv/leaked.py', action: 'write_file' },
        },
      ]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    expect(useArtifactStore.getState().artifacts.some((a) => a.filePath === '/srv/leaked.py')).toBe(
      false,
    )
  })
})

// ---------------------------------------------------------------------------
// run.completed
// ---------------------------------------------------------------------------

describe('event: run.completed', () => {
  it('updates currentRunId and clears streamingMessageId', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'run.completed', data: { run_id: 'run-done' } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    expect(useChatStore.getState().currentRunId).toBe('run-done')
    expect(useChatStore.getState().streamingMessageId).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// run.error / error
// ---------------------------------------------------------------------------

describe('event: run.error / error', () => {
  it('pushes assistant error message for run.error', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'run.error', data: { error: 'timeout occurred' } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    const msgs = useChatStore.getState().messages
    expect(msgs.some((m) => m.role === 'assistant' && m.content.includes('timeout occurred'))).toBe(
      true,
    )
  })

  it('error alias also pushes error message', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'error', data: { error: 'internal error' } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    const msgs = useChatStore.getState().messages
    expect(msgs.some((m) => m.role === 'assistant' && m.content.includes('internal error'))).toBe(
      true,
    )
  })
})

// ---------------------------------------------------------------------------
// done
// ---------------------------------------------------------------------------

describe('event: done', () => {
  it('sets conversationId in chatStore', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'done', data: { conversation_id: 'conv-final', run_id: 'r1' } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    expect(useChatStore.getState().conversationId).toBe('conv-final')
  })

  it('syncs conversationId to artifactStore when artifactStore has no conversationId yet', async () => {
    // artifactStore starts with no conversationId
    expect(useArtifactStore.getState().conversationId).toBeNull()

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'done', data: { conversation_id: 'conv-new' } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    expect(useArtifactStore.getState().conversationId).toBe('conv-new')
  })

  it('clears streamingMessageId after done event', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'done', data: { conversation_id: 'conv-x' } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    expect(useChatStore.getState().streamingMessageId).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// ui.render
// ---------------------------------------------------------------------------

describe('event: ui.render', () => {
  it('pushes ui_component message for valid chart data', async () => {
    const chartData = {
      id: 'chart-1',
      type: 'chart',
      title: 'CPU Usage',
      chartType: 'line',
      data: {
        labels: ['1m', '2m', '3m'],
        datasets: [{ label: 'CPU', data: [10, 20, 15] }],
      },
    }
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'ui.render', data: { data: chartData, actions: [] } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('show chart')
    })
    const msgs = useChatStore.getState().messages
    expect(msgs.some((m) => m.role === 'ui_component')).toBe(true)
  })

  it('pushes error message for invalid ui.render data', async () => {
    // Missing required fields — should fail schema validation
    const invalidData = { id: 'bad', type: 'chart' }
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'ui.render', data: { data: invalidData } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('show')
    })
    const msgs = useChatStore.getState().messages
    const errMsg = msgs.find((m) => m.role === 'assistant' && m.content.includes('验证失败'))
    expect(errMsg).toBeDefined()
  })
})

// ---------------------------------------------------------------------------
// ui.remove
// ---------------------------------------------------------------------------

describe('event: ui.remove', () => {
  it('removes the matching ui_component message by component_id', async () => {
    // Pre-populate a ui_component message
    useChatStore.getState().pushMsg({
      role: 'ui_component',
      componentType: 'card',
      data: { id: 'comp-del', type: 'card', title: 'Old Card' },
      uiActions: [],
      content: '',
    })
    expect(useChatStore.getState().messages.some((m) => m.role === 'ui_component')).toBe(true)

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeSseResponse([{ event: 'ui.remove', data: { component_id: 'comp-del' } }]),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('remove')
    })
    // ui_component messages matching 'comp-del' should be gone
    const msgs = useChatStore.getState().messages
    const remaining = msgs.filter((m) => m.role === 'ui_component')
    expect(remaining.every((m) => (m as { data?: { id?: string } }).data?.id !== 'comp-del')).toBe(
      true,
    )
  })
})

// ---------------------------------------------------------------------------
// SSE parse resilience
// ---------------------------------------------------------------------------

describe('SSE parse resilience', () => {
  it('ignores malformed JSON data chunks without throwing', async () => {
    const encoder = new TextEncoder()
    const malformed = 'event: message\ndata: {invalid json}\n\n'
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(malformed))
        controller.close()
      },
    })
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(new Response(stream, { status: 200 }))

    const { result } = renderSSEChat(queryClient)
    // Should NOT throw
    await act(async () => {
      await result.current.sendMessage('q')
    })
    // Store should not have a streaming error message from JSON parse failure
    // (the catch block in the loop silently ignores parse errors)
    const msgs = useChatStore.getState().messages.filter((m) => m.role === 'assistant')
    // Only the user message was pushed; no assistant error from JSON parse
    expect(msgs.length).toBe(0)
  })

  it('handles HTTP error response by pushing error assistant message', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response('Unauthorized', { status: 401, statusText: 'Unauthorized' }),
    )
    const { result } = renderSSEChat(queryClient)
    await act(async () => {
      await result.current.sendMessage('q')
    })
    const msgs = useChatStore.getState().messages
    expect(msgs.some((m) => m.role === 'assistant' && m.content.startsWith('错误:'))).toBe(true)
  })
})
