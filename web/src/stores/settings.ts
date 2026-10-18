import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { gatewayService } from '@/services/gateway'
import type {
  ConfigStatus,
  ModelEntry,
  ProviderConfig,
  ProviderProbe,
  Settings,
  ServiceConfig,
} from '@/types/session'

/**
 * A fresh copy on every call — `settings` is edited in place by the views, so a
 * shared module-level default would leak edits into the next reset.
 */
export function createDefaultSettings(): Settings {
  return {
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
}

/** JSON with sorted keys, so comparison ignores key order (objects get rebuilt on edits). */
function stableStringify(value: unknown): string {
  return JSON.stringify(value, (_key, item: unknown) => {
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const record = item as Record<string, unknown>
      return Object.fromEntries(Object.keys(record).sort().map((key) => [key, record[key]]))
    }
    return item
  })
}

/** Alias the rest of the product stores (`<provider>/<model>`). */
export function aliasFor(providerId: string, modelId: string): string {
  return `${providerId}/${modelId}`
}

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<Settings>(createDefaultSettings())
  const status = ref<ConfigStatus | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)
  const notice = ref<string | null>(null)
  const probes = ref<Record<string, { loading: boolean; result: ProviderProbe | null }>>({})
  const saved = ref<string>(stableStringify(settings.value))
  const loaded = ref(false)

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

  const providerIds = computed(() => Object.keys(settings.value.providers))

  const modelCount = computed(() => Object.keys(settings.value.models).length)

  const isDirty = computed(() => stableStringify(settings.value) !== saved.value)

  /** Problems that make saving pointless; each one is shown verbatim. */
  const problems = computed(() => {
    const list: string[] = []
    const providers = settings.value.providers
    if (Object.keys(providers).length === 0) list.push('至少需要一个 AI 服务')
    for (const [alias, model] of Object.entries(settings.value.models)) {
      if (!providers[model.provider]) list.push(`模型 ${alias} 指向不存在的 AI 服务 ${model.provider}`)
      if (!model.model.trim()) list.push(`模型 ${alias} 缺少 model 字段`)
    }
    if (!settings.value.models[settings.value.default_model]) {
      list.push(`默认模型 ${settings.value.default_model || '（空）'} 不在 [models] 中`)
    }
    return list
  })

  function modelsFor(providerId: string): [string, ModelEntry][] {
    return Object.entries(settings.value.models).filter(([, model]) => model.provider === providerId)
  }

  function providerOf(model: ModelEntry | undefined): ProviderConfig | undefined {
    return model ? settings.value.providers[model.provider] : undefined
  }

  function providerStatus(providerId: string) {
    return status.value?.providers?.[providerId]
  }

  async function loadSettings() {
    loading.value = true
    error.value = null
    try {
      const data = await gatewayService.call<Settings>('getSettings')
      settings.value = { ...createDefaultSettings(), ...data }
      saved.value = stableStringify(settings.value)
      loaded.value = true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  async function loadStatus() {
    try {
      status.value = await gatewayService.call<ConfigStatus>('getConfigStatus')
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    }
  }

  async function load() {
    await Promise.all([loadSettings(), loadStatus()])
  }

  async function saveSettings(): Promise<boolean> {
    if (problems.value.length > 0) {
      error.value = problems.value.join('；')
      return false
    }
    saving.value = true
    error.value = null
    notice.value = null
    try {
      const data = await gatewayService.call<Settings>('updateSettings', settings.value as unknown as Record<string, unknown>)
      settings.value = { ...createDefaultSettings(), ...data }
      saved.value = stableStringify(settings.value)
      notice.value = '已写入 config.toml'
      void loadStatus()
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return false
    } finally {
      saving.value = false
    }
  }

  function discard() {
    settings.value = JSON.parse(saved.value) as Settings
    error.value = null
    notice.value = null
  }

  /**
   * A partial save from the composer must not make the settings page believe its
   * own unsaved edits went through, so only the patched keys leave the dirty set.
   */
  function markSaved(mutate: (snapshot: Settings) => void) {
    const snapshot = JSON.parse(saved.value) as Settings
    mutate(snapshot)
    saved.value = stableStringify(snapshot)
  }

  async function patchRemote(patch: Record<string, unknown>): Promise<boolean> {
    try {
      await gatewayService.call('updateSettings', patch)
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return false
    }
  }

  /** Composer affordance: pick a model without touching anything else. */
  async function setDefaultModel(alias: string): Promise<boolean> {
    if (!alias || settings.value.default_model === alias) return true
    settings.value.default_model = alias
    markSaved((snapshot) => {
      snapshot.default_model = alias
    })
    return patchRemote({ default_model: alias })
  }

  /** Composer affordance: `[thinking] effort` in config.toml (`null` = follow the model). */
  async function setThinkingEffort(effort: string | null): Promise<boolean> {
    if (settings.value.thinking.effort === effort) return true
    const thinking = { ...settings.value.thinking, effort }
    settings.value.thinking = thinking
    markSaved((snapshot) => {
      snapshot.thinking = { ...thinking }
    })
    return patchRemote({ thinking })
  }

  function ensureLoaded() {
    if (!loaded.value && !loading.value) void loadSettings()
  }

  // ── providers ────────────────────────────────────────────────

  function updateProvider(providerId: string, patch: Partial<ProviderConfig>) {
    const existing = settings.value.providers[providerId]
    if (!existing) return
    settings.value.providers = { ...settings.value.providers, [providerId]: { ...existing, ...patch } }
  }

  function addProvider(providerId: string, patch: Partial<ProviderConfig> = {}): string | null {
    const id = providerId.trim()
    if (!id) return '请填写 AI 服务 id'
    if (settings.value.providers[id]) return `AI 服务 ${id} 已存在`
    settings.value.providers = {
      ...settings.value.providers,
      [id]: { type: 'openai', base_url: '', api_key: '', api_key_env: null, ...patch },
    }
    return null
  }

  function removeProvider(providerId: string) {
    const { [providerId]: _removed, ...rest } = settings.value.providers
    settings.value.providers = rest
    const models = { ...settings.value.models }
    for (const [alias, model] of Object.entries(models)) {
      if (model.provider === providerId) delete models[alias]
    }
    settings.value.models = models
    const first = Object.keys(models)[0]
    if (!models[settings.value.default_model]) settings.value.default_model = first ?? ''
  }

  // ── models ───────────────────────────────────────────────────

  function addModel(providerId: string, modelId: string, patch: Partial<ModelEntry> = {}): string | null {
    const id = modelId.trim()
    if (!id) return '请填写模型 id'
    const alias = aliasFor(providerId, id)
    if (settings.value.models[alias]) return `模型 ${alias} 已存在`
    settings.value.models = {
      ...settings.value.models,
      [alias]: {
        provider: providerId,
        model: id,
        max_context_size: 128000,
        max_output_size: 8000,
        capabilities: ['tool_use'],
        support_efforts: [],
        default_effort: null,
        display_name: null,
        ...patch,
      },
    }
    return null
  }

  /** Renaming the id changes the alias, so `default_model` follows it. */
  function updateModel(alias: string, patch: Partial<ModelEntry>) {
    const existing = settings.value.models[alias]
    if (!existing) return
    const next = { ...existing, ...patch }
    const nextAlias = aliasFor(next.provider, next.model)
    const models = { ...settings.value.models }
    delete models[alias]
    models[nextAlias] = next
    settings.value.models = models
    if (settings.value.default_model === alias) settings.value.default_model = nextAlias
  }

  function removeModel(alias: string) {
    const models = { ...settings.value.models }
    delete models[alias]
    settings.value.models = models
    if (settings.value.default_model === alias) settings.value.default_model = Object.keys(models)[0] ?? ''
  }

  // ── services ─────────────────────────────────────────────────

  function updateService(name: string, patch: Partial<ServiceConfig>) {
    const existing = settings.value.services?.[name]
    if (!existing) {
      settings.value.services = { ...settings.value.services, [name]: { base_url: '', api_key: '', ...patch } }
      return
    }
    settings.value.services = { ...settings.value.services, [name]: { ...existing, ...patch } }
  }

  /** Wipes every stored key — provider keys and service keys alike. */
  function clearApiKeys() {
    const providers: Record<string, ProviderConfig> = {}
    for (const [id, provider] of Object.entries(settings.value.providers)) {
      providers[id] = { ...provider, api_key: '' }
    }
    settings.value.providers = providers
    if (settings.value.services) {
      const services: Record<string, ServiceConfig> = {}
      for (const [name, service] of Object.entries(settings.value.services)) {
        services[name] = { ...service, api_key: '' }
      }
      settings.value.services = services
    }
  }

  // ── probe ────────────────────────────────────────────────────

  async function testProvider(providerId: string) {
    probes.value = { ...probes.value, [providerId]: { loading: true, result: null } }
    try {
      const result = await gatewayService.call<ProviderProbe>('testProvider', { provider: providerId })
      probes.value = { ...probes.value, [providerId]: { loading: false, result } }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      probes.value = { ...probes.value, [providerId]: { loading: false, result: { ok: false, error: message } } }
    }
  }

  return {
    settings,
    status,
    loading,
    saving,
    error,
    notice,
    probes,
    loaded,
    modelOptions,
    providerOptions,
    providerIds,
    modelCount,
    isDirty,
    problems,
    modelsFor,
    providerOf,
    providerStatus,
    load,
    loadSettings,
    loadStatus,
    ensureLoaded,
    saveSettings,
    discard,
    setDefaultModel,
    setThinkingEffort,
    updateProvider,
    addProvider,
    removeProvider,
    addModel,
    updateModel,
    removeModel,
    updateService,
    clearApiKeys,
    testProvider,
  }
})
