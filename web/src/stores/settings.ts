import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { gatewayService } from '@/services/gateway'
import type { ModelEntry, ProviderConfig, Settings } from '@/types/session'

const defaultSettings: Settings = {
  default_model: 'deepseek/deepseek-v4-flash',
  providers: {
    deepseek: {
      type: 'openai',
      base_url: 'https://api.deepseek.com/v1',
      api_key: '',
      api_key_env: 'DEEPSEEK_API_KEY',
    },
  },
  models: {
    'deepseek/deepseek-v4-flash': {
      provider: 'deepseek',
      model: 'deepseek-v4-flash',
      max_context_size: 128000,
      max_output_size: 8000,
      capabilities: ['thinking', 'tool_use'],
      support_efforts: ['high', 'max'],
      default_effort: 'max',
      display_name: 'DeepSeek V4 Flash',
    },
    'deepseek/deepseek-v4': {
      provider: 'deepseek',
      model: 'deepseek-v4',
      max_context_size: 128000,
      max_output_size: 8000,
      capabilities: ['thinking', 'tool_use'],
      support_efforts: ['high', 'max'],
      default_effort: 'max',
      display_name: 'DeepSeek V4',
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
}

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<Settings>({ ...defaultSettings })
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  const modelOptions = computed(() => {
    const options: { value: string; label: string }[] = []
    for (const [alias, model] of Object.entries(settings.value.models)) {
      options.push({
        value: alias,
        label: model.display_name ? `${model.display_name}（${alias}）` : alias,
      })
    }
    return options
  })

  const providerOptions = computed(() => Object.keys(settings.value.providers))

  /** Models belonging to one provider, used by the settings cards. */
  function modelsFor(providerId: string): [string, ModelEntry][] {
    return Object.entries(settings.value.models).filter(([, model]) => model.provider === providerId)
  }

  function providerOf(model: ModelEntry | undefined): ProviderConfig | undefined {
    return model ? settings.value.providers[model.provider] : undefined
  }

  async function loadSettings() {
    loading.value = true
    error.value = null
    try {
      const data = await gatewayService.call<Settings>('getSettings')
      settings.value = { ...defaultSettings, ...data }
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  async function saveSettings(partial?: Partial<Settings>) {
    saving.value = true
    error.value = null
    try {
      const next = { ...settings.value, ...partial }
      const data = await gatewayService.call<Settings>('updateSettings', next)
      settings.value = { ...defaultSettings, ...data }
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return false
    } finally {
      saving.value = false
    }
  }

  function updateSettings(partial: Partial<Settings>) {
    settings.value = { ...settings.value, ...partial }
  }

  function updateProvider(providerId: string, patch: Partial<ProviderConfig>) {
    const next = { ...settings.value }
    next.providers = { ...next.providers }
    const existing = next.providers[providerId] ?? { type: 'openai', base_url: '', api_key: '' }
    next.providers[providerId] = { ...existing, ...patch }
    settings.value = next
  }

  function clearApiKeys() {
    const providers = { ...settings.value.providers }
    for (const id of Object.keys(providers)) {
      providers[id] = { ...providers[id], api_key: '' }
    }
    updateSettings({ providers })
  }

  return {
    settings,
    loading,
    saving,
    error,
    modelOptions,
    providerOptions,
    modelsFor,
    providerOf,
    loadSettings,
    saveSettings,
    updateSettings,
    updateProvider,
    clearApiKeys,
  }
})
