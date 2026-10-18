import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { gatewayService } from '@/services/gateway'
import { createDefaultSettings, useSettingsStore } from '@/stores/settings'
import type { Settings } from '@/types/session'

vi.mock('@/services/gateway', () => ({
  gatewayService: {
    call: vi.fn(),
  },
}))

function serverSettings(): Settings {
  return createDefaultSettings()
}

describe('useSettingsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(gatewayService.call).mockReset()
  })

  it('loads settings and status together', async () => {
    vi.mocked(gatewayService.call)
      .mockResolvedValueOnce(serverSettings())
      .mockResolvedValueOnce({
        config_path: '/home/u/.xiaoqiao/config.toml',
        default_model: 'deepseek/deepseek-v4-flash',
        default_model_defined: true,
        provider: 'deepseek',
        client: 'fake',
        providers: {
          deepseek: {
            api_key_source: 'none',
            api_key_env: 'DEEPSEEK_API_KEY',
            api_key_env_set: false,
            has_key: false,
            model_count: 2,
          },
        },
      })

    const store = useSettingsStore()
    await store.load()

    expect(gatewayService.call).toHaveBeenCalledWith('getSettings')
    expect(gatewayService.call).toHaveBeenCalledWith('getConfigStatus')
    expect(store.modelCount).toBe(2)
    expect(store.status?.client).toBe('fake')
    expect(store.providerStatus('deepseek')?.has_key).toBe(false)
    expect(store.isDirty).toBe(false)
  })

  it('marks edits dirty and keeps the whole config on save', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(serverSettings())
    const store = useSettingsStore()
    await store.loadSettings()

    store.updateProvider('deepseek', { api_key: 'sk-test' })
    expect(store.isDirty).toBe(true)

    const saved = serverSettings()
    saved.providers.deepseek.api_key = 'sk-test'
    vi.mocked(gatewayService.call)
      .mockResolvedValueOnce(saved) // updateSettings
      .mockResolvedValueOnce({ providers: {} }) // getConfigStatus (fire and forget)

    await expect(store.saveSettings()).resolves.toBe(true)
    const [method, payload] = vi.mocked(gatewayService.call).mock.calls.at(-2)!
    expect(method).toBe('updateSettings')
    expect((payload as Settings).providers.deepseek.api_key).toBe('sk-test')
    expect(store.isDirty).toBe(false)
  })

  it('adds a provider and derives model aliases from provider/id', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(serverSettings())
    const store = useSettingsStore()
    await store.loadSettings()

    expect(store.addProvider('openrouter', { base_url: 'https://openrouter.ai/api/v1' })).toBeNull()
    expect(store.addProvider('openrouter')).toContain('已存在')

    expect(store.addModel('openrouter', 'qwen-max')).toBeNull()
    expect(store.settings.models['openrouter/qwen-max'].provider).toBe('openrouter')
    expect(store.addModel('openrouter', 'qwen-max')).toContain('已存在')
  })

  it('removing a provider drops its models and moves the default', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(serverSettings())
    const store = useSettingsStore()
    await store.loadSettings()

    store.addProvider('local', { base_url: 'http://127.0.0.1:8000/v1' })
    store.addModel('local', 'llama')
    store.settings.default_model = 'local/llama'

    store.removeProvider('local')

    expect(store.providerIds).not.toContain('local')
    expect(store.settings.models['local/llama']).toBeUndefined()
    expect(store.settings.default_model).toBe('deepseek/deepseek-v4-flash')
  })

  it('renaming a model id follows into default_model', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(serverSettings())
    const store = useSettingsStore()
    await store.loadSettings()

    store.updateModel('deepseek/deepseek-v4', { model: 'deepseek-v5' })

    expect(store.settings.models['deepseek/deepseek-v5']).toBeDefined()
    expect(store.settings.models['deepseek/deepseek-v4']).toBeUndefined()
  })

  it('clears provider and service keys but keeps env var names', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(serverSettings())
    const store = useSettingsStore()
    await store.loadSettings()

    store.updateProvider('deepseek', { api_key: 'sk-1' })
    store.updateService('web_search', { api_key: 'search-key', base_url: 'http://x' })

    store.clearApiKeys()

    expect(store.settings.providers.deepseek.api_key).toBe('')
    expect(store.settings.providers.deepseek.api_key_env).toBe('DEEPSEEK_API_KEY')
    expect(store.settings.services.web_search.api_key).toBe('')
    expect(store.settings.services.web_search.base_url).toBe('http://x')
  })

  it('refuses to save when the default model is gone', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(serverSettings())
    const store = useSettingsStore()
    await store.loadSettings()

    store.settings.default_model = 'ghost/model'

    expect(store.problems.length).toBeGreaterThan(0)
    await expect(store.saveSettings()).resolves.toBe(false)
    expect(gatewayService.call).toHaveBeenCalledTimes(1)
  })

  it('discard restores the last saved snapshot', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(serverSettings())
    const store = useSettingsStore()
    await store.loadSettings()

    store.updateProvider('deepseek', { base_url: 'http://wrong' })
    store.discard()

    expect(store.settings.providers.deepseek.base_url).toBe('https://api.deepseek.com/v1')
    expect(store.isDirty).toBe(false)
  })
})
