/**
 * useProcessedMessages - ChatMessage[] -> ProcessedMessage[]
 *
 * Groups tool_call / subagent entries under the preceding assistant message
 * so that ChatPanel can render them as a single visual block.
 */

import { useMemo } from 'react'
import { useChatStore } from '@/stores/chatStore'
import type { ProcessedMessage, ToolCallItem, SubAgentItem } from '@/types/agent'

export function useProcessedMessages(): ProcessedMessage[] {
  const messages = useChatStore((s) => s.messages)

  return useMemo(() => {
    const result: ProcessedMessage[] = []

    for (const msg of messages) {
      if (msg.role === 'tool_call') {
        // Attach to the last assistant ProcessedMessage;
        // if none exists yet (agent calls tools before sending text),
        // create a synthetic empty assistant entry as container.
        let last = result.length > 0 ? result[result.length - 1] : null
        if (!last || last.message.role !== 'assistant') {
          const syntheticAssistant: ProcessedMessage = {
            message: { _id: `synth-${msg._id}`, role: 'assistant', content: '' },
            toolCalls: [],
            subAgents: [],
          }
          result.push(syntheticAssistant)
          last = syntheticAssistant
        }
        if (last) {
          // Detect subagent-style tool calls
          if (msg.args?.subagent_type) {
            const sa: SubAgentItem = {
              id: msg._id,
              name: (msg.args.subagent_name as string) ?? msg.tool ?? 'subagent',
              subAgentName: (msg.args.subagent_name as string) ?? msg.tool ?? 'SubAgent',
              input: (msg.args as Record<string, unknown>) ?? {},
              output: undefined,
              status: msg.content ? 'completed' : 'pending',
            }
            last.subAgents.push(sa)
          } else {
            const tc: ToolCallItem = {
              id: msg._id,
              name: msg.tool ?? 'unknown',
              args: msg.args ?? {},
              result: msg.content || undefined,
              status: msg.content ? 'completed' : 'pending',
            }
            last.toolCalls.push(tc)
          }
        }
        continue
      }

      if (msg.role === 'tool_result') {
        // Find the last assistant ProcessedMessage and update its matching pending tool call
        const last = result.length > 0 ? result[result.length - 1] : null
        if (last && last.message.role === 'assistant') {
          const tc = last.toolCalls.find(
            (t) => t.name === msg.tool && t.status === 'pending',
          )
          if (tc) {
            tc.result = msg.content
            tc.status = msg.content?.startsWith('Error') ? 'error' : 'completed'
          }
          // Also check subagents
          const sa = last.subAgents.find(
            (s) => s.name === msg.tool && s.status === 'pending',
          )
          if (sa) {
            try {
              sa.output = JSON.parse(msg.content) as Record<string, unknown>
            } catch {
              sa.output = { result: msg.content }
            }
            sa.status = msg.content?.startsWith('Error') ? 'error' : 'completed'
          }
        }
        continue
      }

      // All other roles become their own ProcessedMessage entry
      result.push({
        message: msg,
        toolCalls: [],
        subAgents: [],
      })
    }

    return result
  }, [messages])
}
