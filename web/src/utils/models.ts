import type { ModelEntry, Settings } from '@/types/session'

/**
 * Presentation helpers shared by the composer's model popover and the full
 * "切换模型" dialog, so both render the same names and subtitles.
 */

const CAPABILITY_LABELS: Record<string, string> = {
  thinking: '思考',
  always_thinking: '始终思考',
  tool_use: '工具调用',
  image_in: '图片输入',
  video_in: '视频输入',
  audio_in: '音频输入',
}

export function capabilityLabel(capability: string): string {
  return CAPABILITY_LABELS[capability] ?? capability
}

/** `128000` → `128k`; the dialog subtitle reads "deepseek · 128k ctx · 工具调用". */
export function contextLabel(size: number | null | undefined): string {
  if (!size || size <= 0) return ''
  return size >= 1000 ? `${Math.round(size / 1000)}k` : String(size)
}

/** `high` → `High`, matching the effort chips in the reference picker. */
export function effortLabel(effort: string): string {
  return effort.charAt(0).toUpperCase() + effort.slice(1)
}

export interface ModelChoice {
  alias: string
  provider: string
  modelId: string
  /** Display name when the config has one, otherwise the model id. */
  name: string
  contextLabel: string
  capabilities: string[]
  efforts: string[]
  /** "deepseek · 128k ctx · 思考 · 工具调用" */
  subtitle: string
}

function subtitleOf(provider: string, entry: ModelEntry): string {
  const parts = [provider]
  const context = contextLabel(entry.max_context_size)
  if (context) parts.push(`${context} ctx`)
  for (const capability of entry.capabilities) parts.push(capabilityLabel(capability))
  return parts.join(' · ')
}

export function buildModelChoices(settings: Settings | null): ModelChoice[] {
  if (!settings) return []
  return Object.entries(settings.models).map(([alias, entry]) => ({
    alias,
    provider: entry.provider,
    modelId: entry.model,
    name: entry.display_name || entry.model,
    contextLabel: contextLabel(entry.max_context_size),
    capabilities: entry.capabilities.map(capabilityLabel),
    efforts: entry.support_efforts,
    subtitle: subtitleOf(entry.provider, entry),
  }))
}

/** The effort the next request will actually use, mirroring the backend's rule. */
export function activeEffort(settings: Settings | null, alias: string): string | null {
  if (!settings) return null
  const entry = settings.models[alias]
  if (!entry || entry.support_efforts.length === 0) return null
  return settings.thinking.effort || entry.default_effort || entry.support_efforts.at(-1) || null
}

const FAVORITES_KEY = 'xiaoqiao:model-favorites'

export function loadFavorites(): string[] {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

export function toggleFavorite(alias: string): string[] {
  const current = loadFavorites()
  const next = current.includes(alias) ? current.filter((item) => item !== alias) : [alias, ...current]
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(next))
  return next
}
