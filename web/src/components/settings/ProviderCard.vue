<script setup lang="ts">
import { ChevronDown, CircleAlert, CircleCheck, Eye, EyeOff, PlugZap, Plus, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import type { ProviderConfig } from '@/types/session'
import ModelRow from './ModelRow.vue'
import SettingsField from './SettingsField.vue'
import {
  BTN_DANGER_CLASS,
  BTN_GHOST_CLASS,
  BTN_SECONDARY_CLASS,
  CARD_CLASS,
  CODE_CLASS,
  INPUT_CLASS,
  SELECT_CLASS,
  badgeClass,
} from './styles'

const props = defineProps<{ providerId: string; provider: ProviderConfig }>()

const store = useSettingsStore()
const showKey = ref(false)
const confirmRemove = ref(false)
const newModelId = ref('')
const addError = ref<string | null>(null)

const PROVIDER_LABELS: Record<string, string> = {
  deepseek: '深度求索（DeepSeek）',
  openrouter: 'OpenRouter',
  apifree: 'apifree',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
}

const TYPES = [
  { value: 'openai', label: 'openai（OpenAI 兼容）' },
  { value: 'openai_responses', label: 'openai_responses' },
  { value: 'anthropic', label: 'anthropic' },
]

const models = computed(() => store.modelsFor(props.providerId))
const status = computed(() => store.providerStatus(props.providerId))
const probe = computed(() => store.probes[props.providerId])
const hasKey = computed(() => (store.settings.providers[props.providerId]?.api_key ?? '').length > 0)

const sourceText = computed(() => {
  const current = status.value
  if (!current) return '密钥来源：读取中…'
  if (current.api_key_source === 'file') return '密钥来源：config.toml 中的 api_key'
  if (current.api_key_source === 'env') {
    return current.api_key_env ? `密钥来源：环境变量 ${current.api_key_env}` : '密钥来源：env 子表'
  }
  if (current.api_key_env) return `密钥来源：未找到（${current.api_key_env} 未设置）`
  return '密钥来源：未设置'
})

const sourceTone = computed<'ok' | 'warn'>(() => (status.value?.has_key || hasKey.value ? 'ok' : 'warn'))

function update(patch: Partial<ProviderConfig>) {
  store.updateProvider(props.providerId, patch)
}

function addModel() {
  const message = store.addModel(props.providerId, newModelId.value)
  if (message) {
    addError.value = message
    return
  }
  addError.value = null
  newModelId.value = ''
}
</script>

<template>
  <section :class="CARD_CLASS" class="p-5">    <header class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h2 class="text-[15px] font-medium text-[var(--color-text)]">
          {{ PROVIDER_LABELS[providerId] || providerId }}
        </h2>
        <code :class="CODE_CLASS">[providers.{{ providerId }}]</code>
      </div>
      <div class="flex items-center gap-2">
        <span :class="badgeClass(sourceTone)">
          <CircleCheck v-if="sourceTone === 'ok'" class="h-3 w-3" />
          <CircleAlert v-else class="h-3 w-3" />
          {{ status?.has_key || hasKey ? '有密钥' : '缺密钥' }}
        </span>
        <button type="button" :class="BTN_SECONDARY_CLASS" :disabled="probe?.loading" @click="store.testProvider(providerId)">
          <PlugZap class="h-3.5 w-3.5" />
          {{ probe?.loading ? '测试中…' : '测试连接' }}
        </button>
        <button v-if="!confirmRemove" type="button" :class="BTN_GHOST_CLASS" @click="confirmRemove = true">
          <Trash2 class="h-3.5 w-3.5" />
        </button>
        <div v-else class="flex items-center gap-1">
          <button type="button" :class="BTN_DANGER_CLASS" @click="store.removeProvider(providerId)">
            删除
          </button>
          <button type="button" :class="BTN_GHOST_CLASS" @click="confirmRemove = false">
            取消
          </button>
        </div>
      </div>
    </header>

    <div class="mt-4 grid gap-3 sm:grid-cols-2">
      <SettingsField label="协议类型" toml-key="type">
        <div class="relative">
          <select
            :value="provider.type"
            :class="SELECT_CLASS"
            @change="update({ type: ($event.target as HTMLSelectElement).value })"
          >
            <option v-for="type in TYPES" :key="type.value" :value="type.value">{{ type.label }}</option>
          </select>
          <ChevronDown class="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-faint)]" />
        </div>
      </SettingsField>
      <SettingsField label="Base URL" toml-key="base_url">
        <input
          :value="provider.base_url"
          :class="INPUT_CLASS"
          spellcheck="false"
          placeholder="https://api.deepseek.com/v1"
          @input="update({ base_url: ($event.target as HTMLInputElement).value })"
        >
      </SettingsField>
      <SettingsField label="API Key" toml-key="api_key" hint="只保存在本机 config.toml；留空则回退到下面的环境变量">
        <div class="relative">
          <input
            :value="provider.api_key"
            :type="showKey ? 'text' : 'password'"
            :class="`${INPUT_CLASS} pr-9`"
            spellcheck="false"
            autocomplete="off"
            placeholder="sk-…"
            @input="update({ api_key: ($event.target as HTMLInputElement).value })"
          >
          <button
            type="button"
            class="absolute right-1 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-text-faint)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
            :aria-label="showKey ? '隐藏密钥' : '显示密钥'"
            @click="showKey = !showKey"
          >
            <EyeOff v-if="showKey" class="h-4 w-4" />
            <Eye v-else class="h-4 w-4" />
          </button>
        </div>
      </SettingsField>
      <SettingsField label="环境变量名" toml-key="api_key_env" hint="api_key 为空时从这里读，不落盘">
        <input
          :value="provider.api_key_env ?? ''"
          :class="INPUT_CLASS"
          spellcheck="false"
          placeholder="DEEPSEEK_API_KEY"
          @input="update({ api_key_env: ($event.target as HTMLInputElement).value || null })"
        >
      </SettingsField>
    </div>

    <p class="mt-2 text-[12px] text-[var(--color-text-muted)]">
      {{ sourceText }}
    </p>

    <p
      v-if="probe && !probe.loading && probe.result"
      class="mt-2 flex items-start gap-1.5 text-[12px]"
      :class="probe.result.ok ? 'text-[var(--color-success)]' : 'text-[var(--color-danger)]'"
    >
      <CircleCheck v-if="probe.result.ok" class="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
      <CircleAlert v-else class="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
      <span class="min-w-0 break-words">
        <template v-if="probe.result.ok">
          连接成功，{{ probe.result.url }} 返回 {{ probe.result.count }} 个模型
          <span v-if="probe.result.models?.length" class="text-[var(--color-text-faint)]">（{{ probe.result.models.slice(0, 4).join('、') }}…）</span>
        </template>
        <template v-else>连接失败：{{ probe.result.error }}</template>
      </span>
    </p>

    <div class="mt-4 border-t-[0.5px] border-[var(--color-line)] pt-3">
      <div class="mb-2 flex items-center justify-between">
        <h3 class="text-[13px] font-medium text-[var(--color-text)]">
          模型
          <span class="ml-1 font-normal text-[var(--color-text-faint)]">{{ models.length }}</span>
        </h3>
        <code :class="CODE_CLASS">[models."{{ providerId }}/…"]</code>
      </div>

      <div class="space-y-1.5">
        <ModelRow v-for="[alias, model] in models" :key="alias" :alias="alias" :model="model" />
        <p v-if="models.length === 0" class="py-2 text-[12px] text-[var(--color-text-faint)]">
          这个 AI 服务下还没有模型，添加一个才能选为默认模型。
        </p>
      </div>

      <div class="mt-2.5 flex items-center gap-2">
        <input
          v-model="newModelId"
          :class="`${INPUT_CLASS} max-w-72`"
          spellcheck="false"
          placeholder="模型 id，例如 deepseek-v4"
          @keydown.enter.prevent="addModel"
        >
        <button type="button" :class="BTN_SECONDARY_CLASS" @click="addModel">
          <Plus class="h-3.5 w-3.5" />
          添加模型
        </button>
      </div>
      <p v-if="addError" class="mt-1.5 text-[12px] text-[var(--color-danger)]">
        {{ addError }}
      </p>
    </div>
  </section>
</template>
