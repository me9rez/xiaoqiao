<script setup lang="ts">
import { ChevronDown, CircleAlert, CircleCheck, Globe, Plus, Save, Trash2 } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import ProviderCard from '@/components/settings/ProviderCard.vue'
import SettingsField from '@/components/settings/SettingsField.vue'
import {
  BTN_DANGER_CLASS,
  BTN_GHOST_CLASS,
  BTN_PRIMARY_CLASS,
  BTN_SECONDARY_CLASS,
  CARD_CLASS,
  CODE_CLASS,
  INPUT_CLASS,
  SELECT_CLASS,
  badgeClass,
} from '@/components/settings/styles'
import { useSettingsStore } from '@/stores/settings'

const store = useSettingsStore()
const showAddProvider = ref(false)
const showClearConfirm = ref(false)
const showWebSearch = ref(false)
const newProvider = ref({ id: '', type: 'openai', base_url: '', api_key: '', api_key_env: '' })
const addError = ref<string | null>(null)

const TYPES = [
  { value: 'openai', label: 'openai（OpenAI 兼容）' },
  { value: 'openai_responses', label: 'openai_responses' },
  { value: 'anthropic', label: 'anthropic' },
]
const EFFORTS = ['low', 'medium', 'high', 'max']
const SEARCH_PROVIDERS = [
  { value: 'bing', label: 'bing（需要 API key）' },
  { value: 'searxng', label: 'searxng（需要实例地址）' },
]

const webSearch = computed(() => store.settings.services?.web_search)
const webSearchReady = computed(() => {
  const service = webSearch.value
  if (!service) return false
  return service.provider === 'searxng' ? Boolean(service.base_url) : Boolean(service.api_key)
})

const fakeClient = computed(() => store.status?.client === 'fake')

function addProvider() {
  const id = newProvider.value.id.trim()
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(id)) {
    addError.value = 'AI 服务 id 只能用小写字母、数字、下划线和连字符'
    return
  }
  const message = store.addProvider(id, {
    type: newProvider.value.type,
    base_url: newProvider.value.base_url.trim(),
    api_key: newProvider.value.api_key.trim(),
    api_key_env: newProvider.value.api_key_env.trim() || null,
  })
  if (message) {
    addError.value = message
    return
  }
  newProvider.value = { id: '', type: 'openai', base_url: '', api_key: '', api_key_env: '' }
  addError.value = null
  showAddProvider.value = false
}

async function clearAllKeys() {
  store.clearApiKeys()
  showClearConfirm.value = false
  await store.saveSettings()
}

function toggleEffort(effort: string | null) {
  store.settings.thinking.effort = effort
}

onMounted(() => {
  void store.load()
})
</script>

<template>
  <div class="mx-auto max-w-4xl p-8">
    <header class="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h1 class="text-[20px] font-semibold leading-7 text-[var(--color-text-strong)]">
          模型
        </h1>
        <p class="mt-1 text-[13px] text-[var(--color-text-muted)]">
          {{ store.providerIds.length }} 个 AI 服务 · {{ store.modelCount }} 个模型 · 写入
          <code :class="CODE_CLASS">config.toml</code>
        </p>
        <p v-if="store.status?.config_path" class="mt-1 break-all font-mono text-[11px] text-[var(--color-text-faint)]">
          {{ store.status.config_path }}
        </p>
      </div>
      <button type="button" :class="BTN_SECONDARY_CLASS" @click="showAddProvider = !showAddProvider">
        <Plus class="h-4 w-4" />
        添加 AI 服务
      </button>
    </header>

    <div v-if="store.loading" class="py-12 text-center text-[13px] text-[var(--color-text-faint)]">
      正在读取 config.toml…
    </div>

    <template v-else>
      <!-- 假客户端警告：没有可用密钥时，回复不是模型给的 -->
      <div
        v-if="fakeClient"
        class="mb-4 flex items-start gap-2.5 rounded-[var(--radius-md)] border-[0.5px] border-[var(--color-warning-bd)] bg-[var(--color-warning-soft)] px-3.5 py-2.5 text-[13px] text-[var(--color-warning)]"
      >
        <CircleAlert class="mt-0.5 h-4 w-4 flex-shrink-0" />
        <span>
          当前没有可用的 API key，回复来自内置的假客户端。给下面某个 AI 服务填上
          <code class="font-mono">api_key</code>，或把对应环境变量设置好，然后保存。
        </span>
      </div>

      <div
        v-if="store.error"
        class="mb-4 flex items-start gap-2.5 rounded-[var(--radius-md)] border-[0.5px] border-[var(--color-danger-bd)] bg-[var(--color-danger-soft)] px-3.5 py-2.5 text-[13px] text-[var(--color-danger)]"
      >
        <CircleAlert class="mt-0.5 h-4 w-4 flex-shrink-0" />
        <span class="min-w-0 break-words">{{ store.error }}</span>
      </div>

      <div
        v-if="store.notice"
        class="mb-4 flex items-start gap-2.5 rounded-[var(--radius-md)] border-[0.5px] border-[var(--color-success-bd)] bg-[var(--color-success-soft)] px-3.5 py-2.5 text-[13px] text-[var(--color-success)]"
      >
        <CircleCheck class="mt-0.5 h-4 w-4 flex-shrink-0" />
        <span>{{ store.notice }}</span>
      </div>

      <!-- 新增 AI 服务 -->
      <section v-if="showAddProvider" :class="CARD_CLASS" class="mb-4 p-5">
        <h2 class="mb-3 text-[15px] font-medium">
          添加 AI 服务
        </h2>
        <div class="grid gap-3 sm:grid-cols-2">
          <SettingsField label="服务 id" toml-key="[providers.<id>]" hint="小写字母开头，例如 openrouter">
            <input v-model="newProvider.id" :class="INPUT_CLASS" spellcheck="false" placeholder="openrouter">
          </SettingsField>
          <SettingsField label="协议类型" toml-key="type">
            <div class="relative">
              <select v-model="newProvider.type" :class="SELECT_CLASS">
                <option v-for="type in TYPES" :key="type.value" :value="type.value">{{ type.label }}</option>
              </select>
              <ChevronDown class="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-faint)]" />
            </div>
          </SettingsField>
          <SettingsField label="Base URL" toml-key="base_url">
            <input v-model="newProvider.base_url" :class="INPUT_CLASS" spellcheck="false" placeholder="https://openrouter.ai/api/v1">
          </SettingsField>
          <SettingsField label="环境变量名（可选）" toml-key="api_key_env">
            <input v-model="newProvider.api_key_env" :class="INPUT_CLASS" spellcheck="false" placeholder="OPENROUTER_API_KEY">
          </SettingsField>
          <SettingsField label="API Key（可选）" toml-key="api_key" hint="建议留空，改用环境变量名">
            <input v-model="newProvider.api_key" :class="INPUT_CLASS" type="password" spellcheck="false" autocomplete="off" placeholder="sk-…">
          </SettingsField>
        </div>
        <p v-if="addError" class="mt-2 text-[12px] text-[var(--color-danger)]">
          {{ addError }}
        </p>
        <div class="mt-3 flex justify-end gap-2">
          <button type="button" :class="BTN_GHOST_CLASS" @click="showAddProvider = false">
            取消
          </button>
          <button type="button" :class="BTN_PRIMARY_CLASS" @click="addProvider">
            添加
          </button>
        </div>
      </section>

      <!-- AI 服务 -->
      <div class="space-y-4">
        <ProviderCard
          v-for="id in store.providerIds"
          :key="id"
          :provider-id="id"
          :provider="store.settings.providers[id]"
        />
        <p v-if="store.providerIds.length === 0" :class="CARD_CLASS" class="p-5 text-[13px] text-[var(--color-text-faint)]">
          还没有 AI 服务。点右上角「添加 AI 服务」开始。
        </p>
      </div>

      <!-- 默认模型与循环控制 -->
      <section :class="CARD_CLASS" class="mt-4 p-5">
        <div class="grid gap-3 sm:grid-cols-2">
          <SettingsField label="默认模型" toml-key="default_model" hint="新会话用它；别名即 provider/model">
            <div class="relative">
              <select v-model="store.settings.default_model" :class="SELECT_CLASS">
                <option v-for="option in store.modelOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <ChevronDown class="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-faint)]" />
            </div>
          </SettingsField>
          <SettingsField label="每轮最大步数（Max Turns）" toml-key="loop_control.max_steps_per_turn">
            <input v-model.number="store.settings.loop_control.max_steps_per_turn" :class="INPUT_CLASS" type="number" min="1">
          </SettingsField>
          <SettingsField label="每步最大尝试次数" toml-key="loop_control.max_attempts_per_step">
            <input v-model.number="store.settings.loop_control.max_attempts_per_step" :class="INPUT_CLASS" type="number" min="1">
          </SettingsField>
          <SettingsField label="压缩最大尝试次数" toml-key="loop_control.compaction_max_attempts">
            <input v-model.number="store.settings.loop_control.compaction_max_attempts" :class="INPUT_CLASS" type="number" min="1">
          </SettingsField>
        </div>
      </section>

      <!-- 思考 -->
      <section :class="CARD_CLASS" class="mt-4 p-5">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-[15px] font-medium">
            思考
          </h2>
          <code :class="CODE_CLASS">[thinking]</code>
        </div>
        <label class="flex items-center gap-2 text-[13px] text-[var(--color-text)]">
          <input v-model="store.settings.thinking.enabled" type="checkbox" class="h-4 w-4 accent-[var(--color-accent)]">
          启用 thinking
        </label>
        <div class="mt-3">
          <SettingsField
            label="思考档位"
            toml-key="effort"
            hint="留空表示用每个模型自己的 default_effort"
          >
            <div class="flex flex-wrap gap-1.5">
              <button
                type="button"
                :class="store.settings.thinking.effort === null ? badgeClass('ok') : badgeClass('neutral')"
                @click="toggleEffort(null)"
              >
                跟随模型
              </button>
              <button
                v-for="effort in EFFORTS"
                :key="effort"
                type="button"
                :class="store.settings.thinking.effort === effort ? badgeClass('ok') : badgeClass('neutral')"
                @click="toggleEffort(effort)"
              >
                {{ effort }}
              </button>
            </div>
          </SettingsField>
        </div>
      </section>

      <!-- 辅助能力 -->
      <section :class="CARD_CLASS" class="mt-4 overflow-hidden">
        <div class="border-b-[0.5px] border-[var(--color-line)] bg-[var(--color-surface)] px-5 py-2.5 text-[13px] font-medium">
          辅助能力
        </div>
        <div class="flex items-center justify-between gap-3 px-5 py-3.5">
          <div class="flex min-w-0 items-center gap-2.5">
            <Globe class="h-4 w-4 flex-shrink-0 text-[var(--color-text-muted)]" />
            <div class="min-w-0">
              <p class="text-[13px] text-[var(--color-text)]">
                联网搜索
              </p>
              <code :class="CODE_CLASS">[services.web_search]</code>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span :class="webSearchReady ? badgeClass('ok') : badgeClass('warn')">
              <CircleCheck v-if="webSearchReady" class="h-3 w-3" />
              <CircleAlert v-else class="h-3 w-3" />
              {{ webSearchReady ? '已配置' : '需自定义配置' }}
            </span>
            <button type="button" :class="BTN_GHOST_CLASS" @click="showWebSearch = !showWebSearch">
              <ChevronDown class="h-3.5 w-3.5 transition" :class="showWebSearch ? 'rotate-180' : ''" />
            </button>
          </div>
        </div>
        <div v-if="showWebSearch" class="border-t-[0.5px] border-[var(--color-line)] px-5 py-3.5">
          <div class="grid gap-3 sm:grid-cols-2">
            <SettingsField label="搜索服务" toml-key="provider" hint="bing 用 key；searxng 用实例地址">
              <div class="relative">
                <select
                  :value="webSearch?.provider || 'bing'"
                  :class="SELECT_CLASS"
                  @change="store.updateService('web_search', { provider: ($event.target as HTMLSelectElement).value })"
                >
                  <option v-for="item in SEARCH_PROVIDERS" :key="item.value" :value="item.value">{{ item.label }}</option>
                </select>
                <ChevronDown class="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-faint)]" />
              </div>
            </SettingsField>
            <SettingsField label="Base URL" toml-key="base_url">
              <input
                :value="webSearch?.base_url ?? ''"
                :class="INPUT_CLASS"
                spellcheck="false"
                placeholder="http://localhost:8080"
                @input="store.updateService('web_search', { base_url: ($event.target as HTMLInputElement).value })"
              >
            </SettingsField>
          </div>
          <div class="mt-3">
            <SettingsField label="API Key" toml-key="api_key">
              <input
                :value="webSearch?.api_key ?? ''"
                :class="INPUT_CLASS"
                type="password"
                spellcheck="false"
                autocomplete="off"
                @input="store.updateService('web_search', { api_key: ($event.target as HTMLInputElement).value })"
              >
            </SettingsField>
          </div>
        </div>
        <div class="border-t-[0.5px] border-[var(--color-line)] px-5 py-3 text-[12px] text-[var(--color-text-faint)]">
          图片生成：当前运行时没有对应工具，暂不提供配置。
        </div>
      </section>

      <!-- 危险区 -->
      <div class="mt-6 flex justify-end">
        <button type="button" :class="BTN_DANGER_CLASS" @click="showClearConfirm = true">
          <Trash2 class="h-3.5 w-3.5" />
          清除所有已保存密钥
        </button>
      </div>

      <!-- 未保存提示 -->
      <div
        v-if="store.isDirty"
        class="sticky bottom-0 mt-6 flex items-center justify-between gap-3 rounded-[var(--radius-md)] border-[0.5px] border-[var(--color-line-strong)] bg-[var(--color-surface-overlay)] px-3.5 py-2.5 shadow-[var(--shadow-xs)] backdrop-blur"
      >
        <span class="text-[13px] text-[var(--color-text-muted)]">
          有未保存的修改
        </span>
        <div class="flex items-center gap-2">
          <button type="button" :class="BTN_GHOST_CLASS" @click="store.discard()">
            放弃
          </button>
          <button type="button" :class="BTN_PRIMARY_CLASS" :disabled="store.saving || store.problems.length > 0" @click="store.saveSettings()">
            <Save class="h-3.5 w-3.5" />
            {{ store.saving ? '保存中…' : '保存到 config.toml' }}
          </button>
        </div>
      </div>
      <p v-if="store.isDirty && store.problems.length" class="mt-2 text-right text-[12px] text-[var(--color-danger)]">
        {{ store.problems.join('；') }}
      </p>
    </template>

    <Teleport to="body">
      <div
        v-if="showClearConfirm"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6"
        @click.self="showClearConfirm = false"
      >
        <div class="w-full max-w-sm rounded-[var(--radius-xl)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-overlay)] p-6 shadow-[var(--shadow-xs)]">
          <h3 class="text-[16px] font-medium">
            清除所有已保存密钥
          </h3>
          <p class="mt-2 text-[13px] leading-5 text-[var(--color-text-muted)]">
            会清空 config.toml 里所有 AI 服务与
            <code class="font-mono">[services.*]</code>
            的 <code class="font-mono">api_key</code> 并立即保存；环境变量名保留。此操作无法撤销。
          </p>
          <div class="mt-5 flex justify-end gap-2">
            <button type="button" :class="BTN_GHOST_CLASS" @click="showClearConfirm = false">
              取消
            </button>
            <button type="button" :class="BTN_DANGER_CLASS" @click="clearAllKeys">
              确认清除
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
