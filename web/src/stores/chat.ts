import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { gatewayService } from '@/services/gateway'
import { useBotsStore } from '@/stores/bots'
import type { Message, MessageContent, QuotedMessage, UiMessage } from '@/types/session'
import {
  isDoneEvent,
  isErrorEvent,
  isTextDeltaEvent,
  isThinkingDeltaEvent,
  isToolApprovalRequestEvent,
  isToolCallStartEvent,
  isToolExecutionDeltaEvent,
  isToolExecutionEndEvent,
  isToolExecutionStartEvent,
  isTurnEndEvent,
} from '@/types/gateway'
import { generateId } from '@/utils/uid'

export type RunState = 'idle' | 'running' | 'waiting_approval'

export interface PendingApproval {
  callId: string
  name: string
  arguments: string
}

interface SessionData {
  messages: UiMessage[]
  runState: RunState
  error: string | null
  pendingApprovals: PendingApproval[]
  loaded: boolean
}

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<Map<string, SessionData>>(new Map())
  const activeSessionId = ref<string | null>(null)

/** The message the user chose to reply to; cleared once the prompt is sent. */
const pendingQuote = ref<QuotedMessage | null>(null)

function setQuote(quote: QuotedMessage | null) {
  pendingQuote.value = quote
}

function clearQuote() {
  pendingQuote.value = null
}

  const messages = computed(() => {
    if (!activeSessionId.value) return []
    return sessions.value.get(activeSessionId.value)?.messages || []
  })

  const runState = computed((): RunState => {
    if (!activeSessionId.value) return 'idle'
    return sessions.value.get(activeSessionId.value)?.runState || 'idle'
  })

  const error = computed(() => {
    if (!activeSessionId.value) return null
    return sessions.value.get(activeSessionId.value)?.error || null
  })

  const pendingApprovals = computed(() => {
    if (!activeSessionId.value) return []
    return sessions.value.get(activeSessionId.value)?.pendingApprovals || []
  })

  const isRunning = computed(() => runState.value === 'running' || runState.value === 'waiting_approval')

  function getOrCreateSession(sessionId: string): SessionData {
    if (!sessions.value.has(sessionId)) {
      sessions.value.set(sessionId, {
        messages: [],
        runState: 'idle',
        error: null,
        pendingApprovals: [],
        loaded: false,
      })
    }
    return sessions.value.get(sessionId)!
  }

  function reset() {
    sessions.value.clear()
    activeSessionId.value = null
  }

  function setActiveSession(sessionId: string) {
    getOrCreateSession(sessionId)
    activeSessionId.value = sessionId
  }

  function addPendingApproval(sessionId: string, approval: PendingApproval) {
    const session = getOrCreateSession(sessionId)
    const last = session.messages[session.messages.length - 1]
    if (
      last &&
      last.role === 'assistant' &&
      last.loading &&
      !last.content.trim() &&
      !last.thinking?.trim()
    ) {
      session.messages.pop()
    }
    session.pendingApprovals.push(approval)
    session.runState = 'waiting_approval'
  }

  function removePendingApproval(sessionId: string, callId: string) {
    const session = getOrCreateSession(sessionId)
    session.pendingApprovals = session.pendingApprovals.filter((a) => a.callId !== callId)
    if (session.pendingApprovals.length === 0 && session.runState === 'waiting_approval') {
      session.runState = 'running'
    }
  }

  function sendApprovalResponse(callId: string, approved: boolean, remember = false) {
    gatewayService.sendApprovalResponse(callId, approved, remember)
    if (activeSessionId.value) {
      removePendingApproval(activeSessionId.value, callId)
    }
  }

  function loadSession(session: { id: string; messages: Message[] }) {
    const sessionData = getOrCreateSession(session.id)
    if (!sessionData.loaded) {
      sessionData.messages = convertBackendMessages(session.messages)
      sessionData.loaded = true
    }
    activeSessionId.value = session.id
  }

  function addUserMessage(sessionId: string, text: string, quoted?: QuotedMessage) {
    const session = getOrCreateSession(sessionId)
    session.messages.push({
      id: generateId('msg'),
      role: 'user',
      content: text,
      timestamp: Date.now(),
      ...(quoted ? { quoted } : {}),
    })
  }

  function ensureAssistantMessage(sessionId: string): UiMessage {
    const session = getOrCreateSession(sessionId)
    const last = session.messages[session.messages.length - 1]
    if (last && last.role === 'assistant' && !last.toolCall && !last.toolExecution) {
      return last
    }
    const msg: UiMessage = {
      id: generateId('msg'),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
    }
    session.messages.push(msg)
    return msg
  }

  function appendTextDelta(sessionId: string, delta: string) {
    const session = getOrCreateSession(sessionId)
    const last = session.messages[session.messages.length - 1]
    let msg: UiMessage
    if (last && last.role === 'assistant' && !last.toolCall && !last.toolExecution) {
      msg = last
    } else {
      msg = {
        id: generateId('msg'),
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
      }
      session.messages.push(msg)
    }
    msg.loading = false
    msg.content += delta
  }

  function appendThinkingDelta(sessionId: string, delta: string) {
    const session = getOrCreateSession(sessionId)
    const last = session.messages[session.messages.length - 1]
    let msg: UiMessage
    if (last && last.role === 'assistant' && !last.toolCall && !last.toolExecution) {
      msg = last
    } else {
      msg = {
        id: generateId('msg'),
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
      }
      session.messages.push(msg)
    }
    msg.loading = false
    msg.thinking = (msg.thinking ?? '') + delta
  }

  function startToolCall(sessionId: string, callId: string, name: string, args: string) {
    const session = getOrCreateSession(sessionId)
    const last = session.messages[session.messages.length - 1]
    if (
      last &&
      last.role === 'assistant' &&
      last.loading &&
      !last.content.trim() &&
      !last.thinking?.trim()
    ) {
      session.messages.pop()
    }
    session.messages.push({
      id: generateId('tool'),
      role: 'tool',
      content: '',
      timestamp: Date.now(),
      toolCall: { callId, name, arguments: args },
    })
  }

  function startToolExecution(sessionId: string, callId: string, name: string) {
    const session = getOrCreateSession(sessionId)
    const tool = session.messages.find(
      (m) => m.role === 'tool' && (m.toolCall?.callId === callId || m.toolExecution?.callId === callId),
    )
    if (tool) {
      tool.toolExecution = { callId, name, output: '', ok: false, exitCode: 0, finished: false }
    } else {
      session.messages.push({
        id: generateId('tool'),
        role: 'tool',
        content: '',
        timestamp: Date.now(),
        toolExecution: { callId, name, output: '', ok: false, exitCode: 0, finished: false },
      })
    }
  }

  function appendToolExecutionDelta(sessionId: string, callId: string, line: string) {
    const session = getOrCreateSession(sessionId)
    const tool = session.messages.find(
      (m) => m.role === 'tool' && (m.toolCall?.callId === callId || m.toolExecution?.callId === callId),
    )
    if (tool?.toolExecution) {
      tool.toolExecution.output += line
    }
  }

  function endToolExecution(sessionId: string, callId: string, name: string, ok: boolean, exitCode: number, result?: string) {
    const session = getOrCreateSession(sessionId)
    const tool = session.messages.find(
      (m) => m.role === 'tool' && (m.toolCall?.callId === callId || m.toolExecution?.callId === callId),
    )
    if (tool) {
      if (!tool.toolExecution) {
        tool.toolExecution = { callId, name, output: result || '', ok, exitCode, finished: true }
      } else {
        tool.toolExecution.ok = ok
        tool.toolExecution.exitCode = exitCode
        tool.toolExecution.finished = true
        if (result !== undefined) {
          tool.toolExecution.output = result
        }
      }
    }
  }

  function sendMessage(text: string, sessionId?: string) {
    if (!text.trim()) return
    const targetSessionId = sessionId || activeSessionId.value
    if (!targetSessionId) return

    getOrCreateSession(targetSessionId)
    activeSessionId.value = targetSessionId

    const session = sessions.value.get(targetSessionId)!
    session.runState = 'running'
    session.error = null

    const quote = pendingQuote.value
    addUserMessage(targetSessionId, text, quote ?? undefined)
    pendingQuote.value = null

    session.messages.push({
      id: generateId('msg'),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      loading: true,
    })

    // The engine has no per-message quote field, so the quote is composed into the
    // prompt text the model reads; the UI still renders it as a quote bar.
    const body = quote ? `> 引用 ${quote.authorName}：${quote.text}\n\n${text}` : text
    gatewayService.sendPrompt(body, targetSessionId, useBotsStore().activeBotId ?? undefined, quote ?? undefined)
  }

  function stop() {
    if (activeSessionId.value) {
      gatewayService.cancel(activeSessionId.value)
    }
  }

  function setupEventListeners() {
    gatewayService.on('text_delta', (event) => {
      if (isTextDeltaEvent(event) && event.sessionId) {
        const session = sessions.value.get(event.sessionId)
        if (session && session.runState !== 'idle') {
          appendTextDelta(event.sessionId, event.delta)
        }
      }
    })
    gatewayService.on('thinking_delta', (event) => {
      if (isThinkingDeltaEvent(event) && event.sessionId) {
        const session = sessions.value.get(event.sessionId)
        if (session && session.runState !== 'idle') {
          appendThinkingDelta(event.sessionId, event.delta)
        }
      }
    })
    gatewayService.on('tool_call_start', (event) => {
      if (isToolCallStartEvent(event) && event.sessionId) {
        const session = sessions.value.get(event.sessionId)
        if (session && session.runState !== 'idle') {
          startToolCall(event.sessionId, event.callId, event.name, event.arguments)
        }
      }
    })
    gatewayService.on('tool_execution_start', (event) => {
      if (isToolExecutionStartEvent(event) && event.sessionId) {
        const session = sessions.value.get(event.sessionId)
        if (session && session.runState !== 'idle') {
          startToolExecution(event.sessionId, event.callId, event.name)
        }
      }
    })
    gatewayService.on('tool_execution_delta', (event) => {
      if (isToolExecutionDeltaEvent(event) && event.sessionId) {
        const session = sessions.value.get(event.sessionId)
        if (session && session.runState !== 'idle') {
          appendToolExecutionDelta(event.sessionId, event.callId, event.line)
        }
      }
    })
    gatewayService.on('tool_execution_end', (event) => {
      if (isToolExecutionEndEvent(event) && event.sessionId) {
        const session = sessions.value.get(event.sessionId)
        if (session && session.runState !== 'idle') {
          endToolExecution(event.sessionId, event.callId, event.name, event.ok, event.exitCode, event.result)
        }
      }
    })
    gatewayService.on('turn_end', (event) => {
      if (isTurnEndEvent(event) && event.reason === 'complete' && event.sessionId) {
        // assistant message naturally complete
      }
    })
    gatewayService.on('done', (event) => {
      const sessionId = (event as { sessionId?: string }).sessionId
      if (sessionId) {
        const session = sessions.value.get(sessionId)
        if (session) {
          const last = session.messages[session.messages.length - 1]
          if (last && last.role === 'assistant') {
            last.loading = false
          }
          session.runState = 'idle'
        }
      }
    })
    gatewayService.on('error', (event) => {
      if (isErrorEvent(event)) {
        const sessionId = (event as { sessionId?: string }).sessionId
        if (sessionId) {
          const session = sessions.value.get(sessionId)
          if (session) {
            if (!event.recoverable) {
              const last = session.messages[session.messages.length - 1]
              if (last && last.role === 'assistant') {
                last.loading = false
              }
              session.runState = 'idle'
            }
            session.error = event.message
          }
        }
      }
    })
    gatewayService.on('tool_approval_request', (event) => {
      if (isToolApprovalRequestEvent(event) && event.sessionId) {
        const session = sessions.value.get(event.sessionId)
        if (session && session.runState !== 'idle') {
          addPendingApproval(event.sessionId, {
            callId: event.callId,
            name: event.name,
            arguments: event.arguments,
          })
        }
      }
    })
  }

  return {
    sessions,
    messages,
    runState,
    isRunning,
    error,
    pendingApprovals,
    pendingQuote,
    setQuote,
    clearQuote,
    activeSessionId,
    reset,
    setActiveSession,
    loadSession,
    sendMessage,
    stop,
    setupEventListeners,
    sendApprovalResponse,
  }
})

function isTextContent(content: MessageContent): content is Extract<MessageContent, { type: 'text' }> {
  return content.type === 'text'
}

function isFunctionCallContent(content: MessageContent): content is Extract<MessageContent, { type: 'function_call' }> {
  return content.type === 'function_call'
}

function isFunctionResultContent(content: MessageContent): content is Extract<MessageContent, { type: 'function_result' }> {
  return content.type === 'function_result'
}

function isUsageContent(content: MessageContent): content is Extract<MessageContent, { type: 'usage' }> {
  return content.type === 'usage'
}

interface BackendMessage {
  role: string
  contents: MessageContent[]
  thinking?: string
  additional_properties?: Record<string, unknown>
}

function readQuoted(raw: unknown): QuotedMessage | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const value = raw as Record<string, unknown>
  const authorName = typeof value.authorName === 'string' ? value.authorName : ''
  const text = typeof value.text === 'string' ? value.text : ''
  if (!authorName && !text) return undefined
  return { authorName: authorName || '未署名', text }
}

export function convertBackendMessages(msgs: BackendMessage[]): UiMessage[] {
  const result: UiMessage[] = []
  const toolMessages = new Map<string, UiMessage>()
  let textSegment: { role: string; content: string; thinking?: string; quoted?: QuotedMessage } | null = null

  function flushText() {
    if (!textSegment) return
    const hasContent = textSegment.content.trim().length > 0
    const hasThinking = !!textSegment.thinking && textSegment.thinking.trim().length > 0
    if (!hasContent && !hasThinking) {
      textSegment = null
      return
    }
    result.push({
      id: generateId('msg'),
      role: textSegment.role as 'user' | 'assistant' | 'tool',
      content: textSegment.content,
      timestamp: Date.now(),
      thinking: textSegment.thinking,
      ...(textSegment.quoted ? { quoted: textSegment.quoted } : {}),
    })
    textSegment = null
  }

  for (const msg of msgs) {
    const thinking = typeof msg.thinking === 'string'
      ? msg.thinking
      : typeof msg.additional_properties?.thinking === 'string'
        ? msg.additional_properties.thinking
        : undefined
    // The gateway stores a quoted reply on the user message's additional_properties.
    const quoted = readQuoted(msg.additional_properties?.quoted)

    const quotedForTurn = msg.role === 'user' ? quoted : undefined
    let emittedThinking = false
    const hasTextContent = msg.contents.some(isTextContent)
    if (thinking && !textSegment && msg.role === 'assistant' && !hasTextContent) {
      textSegment = { role: msg.role, content: '', thinking, quoted: quotedForTurn }
      emittedThinking = true
    }

    for (const content of msg.contents) {
      if (isTextContent(content)) {
        if (!textSegment) {
          textSegment = { role: msg.role, content: '', thinking, quoted: quotedForTurn }
        } else if (textSegment.role !== msg.role) {
          flushText()
          textSegment = { role: msg.role, content: '', thinking, quoted: quotedForTurn }
        }
        textSegment.content += content.text ?? ''
        continue
      }

      if (isUsageContent(content)) {
        continue
      }

      flushText()

      if (isFunctionCallContent(content)) {
        const callId = content.call_id ?? ''
        const existing = toolMessages.get(callId)
        if (existing) {
          existing.toolCall = {
            callId,
            name: content.name ?? '',
            arguments: content.arguments ?? '',
          }
        } else {
          const toolMsg: UiMessage = {
            id: generateId('tool'),
            role: 'tool',
            content: '',
            timestamp: Date.now(),
            toolCall: {
              callId,
              name: content.name ?? '',
              arguments: content.arguments ?? '',
            },
          }
          toolMessages.set(callId, toolMsg)
          result.push(toolMsg)
        }
      } else if (isFunctionResultContent(content)) {
        const callId = content.call_id ?? ''
        const existing = toolMessages.get(callId)
        if (existing) {
          existing.toolExecution = {
            callId,
            name: content.name ?? '',
            output: content.result ?? '',
            ok: true,
            exitCode: 0,
            finished: true,
          }
        } else {
          const toolMsg: UiMessage = {
            id: generateId('tool'),
            role: 'tool',
            content: '',
            timestamp: Date.now(),
            toolExecution: {
              callId,
              name: content.name ?? '',
              output: content.result ?? '',
              ok: true,
              exitCode: 0,
              finished: true,
            },
          }
          toolMessages.set(callId, toolMsg)
          result.push(toolMsg)
        }
      }
    }

    if (!emittedThinking && thinking && !textSegment && msg.role === 'assistant') {
      textSegment = { role: msg.role, content: '', thinking, quoted: quotedForTurn }
    }
    flushText()
  }

  flushText()
  return result
}
