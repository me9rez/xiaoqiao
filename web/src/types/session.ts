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

/**
 * Configuration types.
 *
 * The wire shape mirrors `~/.xiaoqiao/config.toml` exactly (snake_case, models
 * keyed by alias), so there is only one vocabulary for a setting end to end.
 */
export interface ModelEntry {
  provider: string
  model: string
  max_context_size: number
  max_input_size?: number | null
  max_output_size?: number | null
  capabilities: string[]
  support_efforts: string[]
  default_effort?: string | null
  display_name?: string | null
  reasoning_key?: string | null
}

export interface ProviderConfig {
  type: string
  base_url: string
  api_key: string
  api_key_env?: string | null
  env?: Record<string, string>
  custom_headers?: Record<string, string>
}

export interface ThinkingConfig {
  enabled: boolean
  effort?: string | null
  keep?: string | null
}

export interface LoopControlConfig {
  max_steps_per_turn: number
  max_attempts_per_step: number
  reserved_context_size?: number | null
  compaction_max_attempts: number
}

export interface LimitsConfig {
  daily_token_budget: number
  daily_budget_usd: number
  max_requests_per_minute: number
}

export type PermissionDecision = 'allow' | 'deny' | 'ask'

export interface PermissionRule {
  decision: PermissionDecision
  pattern: string
  reason?: string | null
  scope?: string | null
}

export interface PermissionConfig {
  mode: 'manual' | 'yolo' | 'auto'
  dangerous_command_guard: boolean
  rules: PermissionRule[]
}

export interface ServiceConfig {
  base_url: string
  api_key: string
  provider?: string
  custom_headers?: Record<string, string>
}

/** Where a provider's key comes from right now (`getConfigStatus`). */
export type ApiKeySource = 'file' | 'env' | 'none' | 'missing'

export interface ProviderStatus {
  api_key_source: ApiKeySource
  api_key_env: string | null
  api_key_env_set: boolean
  has_key: boolean
  model_count: number
}

/**
 * Runtime facts the TOML file cannot express. Kept out of `Settings` on purpose:
 * that payload mirrors `config.toml` byte for byte, this one describes it.
 */
export interface ConfigStatus {
  config_path: string
  default_model: string
  default_model_defined: boolean
  provider: string
  /** `fake` means the canned `_FakeClient` answers — no usable key anywhere. */
  client: 'real' | 'fake'
  providers: Record<string, ProviderStatus>
}

/** Result of the `testProvider` probe. */
export interface ProviderProbe {
  ok: boolean
  url?: string
  status?: number
  count?: number
  models?: string[]
  error?: string
}

export interface Settings {
  default_model: string
  providers: Record<string, ProviderConfig>
  models: Record<string, ModelEntry>
  thinking: ThinkingConfig
  loop_control: LoopControlConfig
  limits: LimitsConfig
  permission: PermissionConfig
  services: Record<string, ServiceConfig>
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
