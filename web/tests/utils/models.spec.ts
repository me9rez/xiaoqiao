import { beforeEach, describe, expect, it } from 'vitest'
import type { Settings } from '@/types/session'
import {
  activeEffort,
  buildModelChoices,
  capabilityLabel,
  contextLabel,
  effortLabel,
  loadFavorites,
  toggleFavorite,
} from '@/utils/models'

function settings(overrides: Partial<Settings> = {}): Settings {
  return {
    default_model: 'deepseek/deepseek-v4-flash',
    providers: {
      deepseek: { type: 'openai', base_url: 'https://api.deepseek.com/v1', api_key: '' },
      local: { type: 'openai', base_url: 'http://127.0.0.1:8000/v1', api_key: '' },
    },
    models: {
      'deepseek/deepseek-v4-flash': {
        provider: 'deepseek',
        model: 'deepseek-v4-flash',
        max_context_size: 128000,
        capabilities: ['thinking', 'tool_use', 'image_in'],
        support_efforts: ['high', 'max'],
        default_effort: 'max',
        display_name: 'DeepSeek V4 Flash',
      },
      'local/llama': {
        provider: 'local',
        model: 'llama',
        max_context_size: 32000,
        capabilities: ['tool_use'],
        support_efforts: [],
        default_effort: null,
      },
    },
    thinking: { enabled: true, effort: null, keep: null },
    loop_control: {
      max_steps_per_turn: 25,
      max_attempts_per_step: 10,
      reserved_context_size: null,
      compaction_max_attempts: 5,
    },
    limits: { daily_token_budget: 0, daily_budget_usd: 0, max_requests_per_minute: 0 },
    permission: { mode: 'manual', dangerous_command_guard: true, rules: [] },
    services: {},
    ...overrides,
  }
}

describe('model presentation helpers', () => {
  it('formats context sizes the way the dialog subtitle does', () => {
    expect(contextLabel(128000)).toBe('128k')
    expect(contextLabel(977000)).toBe('977k')
    expect(contextLabel(900)).toBe('900')
    expect(contextLabel(null)).toBe('')
    expect(contextLabel(0)).toBe('')
  })

  it('capitalises effort values for the chips', () => {
    expect(effortLabel('high')).toBe('High')
    expect(effortLabel('max')).toBe('Max')
    expect(effortLabel('medium')).toBe('Medium')
  })

  it('translates capabilities and keeps unknown ones', () => {
    expect(capabilityLabel('tool_use')).toBe('工具调用')
    expect(capabilityLabel('always_thinking')).toBe('始终思考')
    expect(capabilityLabel('mystery')).toBe('mystery')
  })

  it('builds a choice per alias with provider, name and subtitle', () => {
    const choices = buildModelChoices(settings())

    expect(choices.map((choice) => choice.alias)).toEqual(['deepseek/deepseek-v4-flash', 'local/llama'])
    const first = choices[0]
    expect(first.name).toBe('DeepSeek V4 Flash')
    expect(first.provider).toBe('deepseek')
    expect(first.subtitle).toBe('deepseek · 128k ctx · 思考 · 工具调用 · 图片输入')
    // No display_name in the config → the model id is the label.
    expect(choices[1].name).toBe('llama')
    expect(choices[1].subtitle).toBe('local · 32k ctx · 工具调用')
  })

  it('returns nothing before settings load', () => {
    expect(buildModelChoices(null)).toEqual([])
  })
})

describe('activeEffort', () => {
  it('prefers the global [thinking] effort', () => {
    const value = settings()
    value.thinking.effort = 'high'
    expect(activeEffort(value, 'deepseek/deepseek-v4-flash')).toBe('high')
  })

  it('falls back to the model default, then to the last supported level', () => {
    expect(activeEffort(settings(), 'deepseek/deepseek-v4-flash')).toBe('max')

    const value = settings()
    value.models['deepseek/deepseek-v4-flash'].default_effort = null
    expect(activeEffort(value, 'deepseek/deepseek-v4-flash')).toBe('max')

    value.models['deepseek/deepseek-v4-flash'].support_efforts = []
    expect(activeEffort(value, 'deepseek/deepseek-v4-flash')).toBeNull()
  })

  it('has no effort for a model without support_efforts', () => {
    expect(activeEffort(settings(), 'local/llama')).toBeNull()
  })
})

describe('favorites', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('toggles and persists aliases, newest first', () => {
    expect(toggleFavorite('a/b')).toEqual(['a/b'])
    expect(toggleFavorite('c/d')).toEqual(['c/d', 'a/b'])
    expect(loadFavorites()).toEqual(['c/d', 'a/b'])
    expect(toggleFavorite('a/b')).toEqual(['c/d'])
  })

  it('survives corrupt storage', () => {
    localStorage.setItem('xiaoqiao:model-favorites', '{not json')
    expect(loadFavorites()).toEqual([])
  })
})
