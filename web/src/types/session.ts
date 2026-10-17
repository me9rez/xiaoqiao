export interface SessionInfo {
  id: string
  title: string
  model: string
  modelProvider: string
  workspace: string
  botId: string
  createdAt: string
  updatedAt: string
  messageCount: number
  status: string
  sessionStartedAt: string
  lastInteractionAt: string
  startedAt: string
  endedAt: string
  runtimeMs: number
  inputTokens: number
  outputTokens: number
  totalTokens: number
  cacheReadTokens: number
  reasoningTokens: number
  estimatedCostUsd: number
}

export interface SessionData {
  id: string
  title: string
  model: string
  modelProvider: string
  workspace: string
  botId: string
  createdAt: string
  updatedAt: string
  messages: Message[]
  status: string
  sessionStartedAt: string
  lastInteractionAt: string
  startedAt: string
  endedAt: string
  runtimeMs: number
  inputTokens: number
  outputTokens: number
  totalTokens: number
  cacheReadTokens: number
  reasoningTokens: number
  estimatedCostUsd: number
}

export interface ModelConfig {
  id: string
  name: string
  contextWindow?: number
  maxTokens?: number
  reasoning?: boolean
  thinking_level?: string[]
  input?: string[]
}

export interface ProviderConfig {
  api?: string
  baseUrl?: string
  apiKey?: string
  enabled?: boolean
  models: ModelConfig[]
}

export interface Settings {
  primaryModel: string
  providers: Record<string, ProviderConfig>
  max_turns: number
}

export type MessageRole = 'user' | 'assistant' | 'system' | 'tool'

export interface TextContent {
  type: 'text'
  text: string
}

export interface FunctionCallContent {
  type: 'function_call'
  call_id: string
  name: string
  arguments: string
}

export interface FunctionResultContent {
  type: 'function_result'
  call_id: string
  name: string
  result: string
}

export interface UsageContent {
  type: 'usage'
  usage_details: Record<string, unknown>
}

export type MessageContent = TextContent | FunctionCallContent | FunctionResultContent | UsageContent

export interface Message {
  role: MessageRole
  contents: MessageContent[]
  additional_properties?: Record<string, unknown>
  usage?: Record<string, unknown>
}

export interface UiMessage {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  timestamp: number
  loading?: boolean
  thinking?: string
  toolCall?: {
    callId: string
    name: string
    arguments: string
  }
  toolExecution?: {
    callId: string
    name: string
    output: string
    ok: boolean
    exitCode: number
    finished?: boolean
  }
}
