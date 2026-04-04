import { describe, it, expect } from 'vitest'
import {
  isUIComponentMessage,
  hasContent,
  hasToolCalls,
  hasSubAgents,
  extractTextContent,
  isToolCallCompleted,
  isSubAgentCompleted,
  getMessageGroupType,
  getToolDisplayInfo,
  getToolResultSummary,
} from '@/lib/message-utils'
import type { ChatMessage, ProcessedMessage, ToolCallItem, SubAgentItem } from '@/types/agent'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMsg(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return { _id: 'test-id', role: 'assistant', content: 'hello', ...overrides }
}

function makeProcessed(overrides: Partial<ProcessedMessage> = {}): ProcessedMessage {
  return {
    message: makeMsg(),
    toolCalls: [],
    subAgents: [],
    ...overrides,
  }
}

function makeToolCall(status: ToolCallItem['status'] = 'pending'): ToolCallItem {
  return { id: 'tc-1', name: 'execute', args: {}, status }
}

function makeSubAgent(status: SubAgentItem['status'] = 'pending'): SubAgentItem {
  return {
    id: 'sa-1',
    name: 'researcher',
    subAgentName: 'researcher',
    input: {},
    status,
  }
}

// ---------------------------------------------------------------------------
// isUIComponentMessage
// ---------------------------------------------------------------------------

describe('isUIComponentMessage', () => {
  it('returns true for ui_component role with componentType', () => {
    const msg = makeMsg({ role: 'ui_component', componentType: 'chart' } as ChatMessage)
    expect(isUIComponentMessage(msg)).toBe(true)
  })

  it('returns false for assistant role', () => {
    const msg = makeMsg({ role: 'assistant' })
    expect(isUIComponentMessage(msg)).toBe(false)
  })

  it('returns false for ui_component without componentType', () => {
    const msg = makeMsg({ role: 'ui_component' })
    expect(isUIComponentMessage(msg)).toBe(false)
  })

  it('returns false for tool_call role', () => {
    const msg = makeMsg({ role: 'tool_call' })
    expect(isUIComponentMessage(msg)).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// hasContent
// ---------------------------------------------------------------------------

describe('hasContent', () => {
  it('returns true when message has non-empty string content', () => {
    const pm = makeProcessed({ message: makeMsg({ content: 'Some text' }) })
    expect(hasContent(pm)).toBe(true)
  })

  it('returns false when content is empty string', () => {
    const pm = makeProcessed({ message: makeMsg({ content: '' }) })
    expect(hasContent(pm)).toBe(false)
  })

  it('returns false when content is whitespace only', () => {
    const pm = makeProcessed({ message: makeMsg({ content: '   \n\t  ' }) })
    expect(hasContent(pm)).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// hasToolCalls
// ---------------------------------------------------------------------------

describe('hasToolCalls', () => {
  it('returns true when toolCalls is non-empty', () => {
    const pm = makeProcessed({ toolCalls: [makeToolCall()] })
    expect(hasToolCalls(pm)).toBe(true)
  })

  it('returns false when toolCalls is empty', () => {
    const pm = makeProcessed({ toolCalls: [] })
    expect(hasToolCalls(pm)).toBe(false)
  })

  it('returns true with multiple tool calls', () => {
    const pm = makeProcessed({ toolCalls: [makeToolCall(), makeToolCall('completed')] })
    expect(hasToolCalls(pm)).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// hasSubAgents
// ---------------------------------------------------------------------------

describe('hasSubAgents', () => {
  it('returns true when subAgents is non-empty', () => {
    const pm = makeProcessed({ subAgents: [makeSubAgent()] })
    expect(hasSubAgents(pm)).toBe(true)
  })

  it('returns false when subAgents is empty', () => {
    const pm = makeProcessed({ subAgents: [] })
    expect(hasSubAgents(pm)).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// extractTextContent
// ---------------------------------------------------------------------------

describe('extractTextContent', () => {
  it('returns string directly when content is a string', () => {
    expect(extractTextContent('hello world')).toBe('hello world')
  })

  it('returns empty string for null/undefined', () => {
    expect(extractTextContent(null)).toBe('')
    expect(extractTextContent(undefined)).toBe('')
  })

  it('extracts text parts from content array', () => {
    const parts = [
      { type: 'text', text: 'Hello ' },
      { type: 'text', text: 'World' },
    ]
    expect(extractTextContent(parts)).toBe('Hello World')
  })

  it('ignores non-text parts in content array', () => {
    const parts = [
      { type: 'text', text: 'visible' },
      { type: 'image', url: 'http://example.com/img.png' },
    ]
    expect(extractTextContent(parts)).toBe('visible')
  })

  it('returns empty string for empty array', () => {
    expect(extractTextContent([])).toBe('')
  })

  it('converts non-string primitives via String()', () => {
    expect(extractTextContent(42)).toBe('42')
  })
})

// ---------------------------------------------------------------------------
// isToolCallCompleted
// ---------------------------------------------------------------------------

describe('isToolCallCompleted', () => {
  it('returns true for completed status', () => {
    expect(isToolCallCompleted(makeToolCall('completed'))).toBe(true)
  })

  it('returns true for error status', () => {
    expect(isToolCallCompleted(makeToolCall('error'))).toBe(true)
  })

  it('returns false for pending status', () => {
    expect(isToolCallCompleted(makeToolCall('pending'))).toBe(false)
  })

  it('returns false for interrupted status', () => {
    expect(isToolCallCompleted(makeToolCall('interrupted'))).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// isSubAgentCompleted
// ---------------------------------------------------------------------------

describe('isSubAgentCompleted', () => {
  it('returns true for completed status', () => {
    expect(isSubAgentCompleted(makeSubAgent('completed'))).toBe(true)
  })

  it('returns true for error status', () => {
    expect(isSubAgentCompleted(makeSubAgent('error'))).toBe(true)
  })

  it('returns false for pending status', () => {
    expect(isSubAgentCompleted(makeSubAgent('pending'))).toBe(false)
  })

  it('returns false for interrupted status', () => {
    expect(isSubAgentCompleted(makeSubAgent('interrupted'))).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// getMessageGroupType
// ---------------------------------------------------------------------------

describe('getMessageGroupType', () => {
  it('returns "content" when no tool calls and no subagents', () => {
    const pm = makeProcessed()
    expect(getMessageGroupType(pm)).toBe('content')
  })

  it('returns "processing" when there are tool calls but no content', () => {
    const pm = makeProcessed({
      message: makeMsg({ content: '' }),
      toolCalls: [makeToolCall()],
    })
    expect(getMessageGroupType(pm)).toBe('processing')
  })

  it('returns "mixed" when there are both tool calls and content', () => {
    const pm = makeProcessed({
      message: makeMsg({ content: 'analysis result' }),
      toolCalls: [makeToolCall()],
    })
    expect(getMessageGroupType(pm)).toBe('mixed')
  })

  it('returns "subagent" when there are subagents (takes priority over tool calls)', () => {
    const pm = makeProcessed({
      message: makeMsg({ content: 'some content' }),
      toolCalls: [makeToolCall()],
      subAgents: [makeSubAgent()],
    })
    expect(getMessageGroupType(pm)).toBe('subagent')
  })

  it('returns "subagent" when only subagents present', () => {
    const pm = makeProcessed({ subAgents: [makeSubAgent()] })
    expect(getMessageGroupType(pm)).toBe('subagent')
  })
})

// ---------------------------------------------------------------------------
// getToolDisplayInfo
// ---------------------------------------------------------------------------

describe('getToolDisplayInfo', () => {
  it('returns correct info for known docker tool', () => {
    const info = getToolDisplayInfo('list_docker_containers')
    expect(info.category).toBe('Docker')
    expect(info.label).toBe('容器列表')
    expect(info.icon).toBe('Box')
  })

  it('returns correct info for built-in execute tool', () => {
    const info = getToolDisplayInfo('execute')
    expect(info.category).toBe('内置')
    expect(info.label).toBe('执行命令')
  })

  it('returns correct info for write_file tool', () => {
    const info = getToolDisplayInfo('write_file')
    expect(info.category).toBe('内置')
    expect(info.label).toBe('写入文件')
    expect(info.icon).toBe('FilePlus')
  })

  it('returns correct info for web_search tool', () => {
    const info = getToolDisplayInfo('web_search')
    expect(info.category).toBe('研究')
    expect(info.label).toBe('网络搜索')
  })

  it('falls back to default for unknown tool', () => {
    const info = getToolDisplayInfo('unknown_custom_tool')
    expect(info.icon).toBe('Wrench')
    // label falls back to the tool name itself
    expect(info.label).toBe('unknown_custom_tool')
    expect(info.category).toBe('其他')
  })

  it('returns color class for system tool', () => {
    const info = getToolDisplayInfo('get_system_overview')
    expect(info.color).toBe('text-green-400')
  })
})

// ---------------------------------------------------------------------------
// getToolResultSummary
// ---------------------------------------------------------------------------

describe('getToolResultSummary', () => {
  it('returns empty string for undefined result', () => {
    expect(getToolResultSummary(undefined)).toBe('')
  })

  it('returns trimmed result when within maxLength', () => {
    expect(getToolResultSummary('OK', 100)).toBe('OK')
  })

  it('trims leading/trailing whitespace', () => {
    expect(getToolResultSummary('  hello  ', 100)).toBe('hello')
  })

  it('truncates to maxLength and appends ellipsis', () => {
    const long = 'a'.repeat(200)
    const result = getToolResultSummary(long, 100)
    expect(result).toHaveLength(103) // 100 + '...'
    expect(result.endsWith('...')).toBe(true)
  })

  it('does not truncate when result is exactly maxLength', () => {
    const exact = 'x'.repeat(100)
    const result = getToolResultSummary(exact, 100)
    expect(result).toBe(exact)
    expect(result.endsWith('...')).toBe(false)
  })

  it('uses default maxLength of 100', () => {
    const long = 'b'.repeat(150)
    const result = getToolResultSummary(long)
    expect(result.length).toBe(103)
  })
})
