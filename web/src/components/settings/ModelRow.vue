<script setup lang="ts">
import { ChevronDown, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import type { ModelEntry } from '@/types/session'
import SettingsField from './SettingsField.vue'
import { BTN_DANGER_CLASS, BTN_GHOST_CLASS, BTN_PRIMARY_CLASS, CODE_CLASS, INPUT_CLASS, SELECT_CLASS, badgeClass } from './styles'

const props = defineProps<{ alias: string; model: ModelEntry }>()

const store = useSettingsStore()
const open = ref(false)
const error = ref<string | null>(null)

const CAPABILITIES = [
  { value: 'thinking', label: 'thinking' },
  { value: 'always_thinking', label: 'always_thinking' },
  { value: 'tool_use', label: 'tool_use' },
  { value: 'image_in', label: 'image_in' },
  { value: 'video_in', label: 'video_in' },
  { value: 'audio_in', label: 'audio_in' },
]
const EFFORTS = ['low', 'medium', 'high', 'max']

interface Draft {
  model: string
  display_name: string
  max_context_size: number
  max_output_size: number | null
  capabilities: string[]
  support_efforts: string[]
  default_effort: string | null
}

const draft = ref<Draft>(clone(props.model))

function clone(model: ModelEntry): Draft {
  return {
    model: model.model,
    display_name: model.display_name ?? '',
    max_context_size: model.max_context_size,
    max_output_size: model.max_output_size ?? null,
    capabilities: [...model.capabilities],
    support_efforts: [...model.support_efforts],
    default_effort: model.default_effort ?? null,
  }
}

const isDefault = computed(() => store.settings.default_model === props.alias)
const nextAlias = computed(() => `${props.model.provider}/${draft.value.model.trim()}`)

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
}

function toggleCapability(value: string) {
  draft.value.capabilities = toggle(draft.value.capabilities, value)
}

function toggleEffort(value: string) {
  draft.value.support_efforts = toggle(draft.value.support_efforts, value)
  if (!draft.value.support_efforts.includes(draft.value.default_effort ?? '')) {
    draft.value.default_effort = null
  }
}

function startEdit() {
  draft.value = clone(props.model)
  error.value = null
  open.value = true
}

function save() {
  const modelId = draft.value.model.trim()
  if (!modelId) {
    error.value = '模型 id 不能为空'
    return
  }
  if (nextAlias.value !== props.alias && store.settings.models[nextAlias.value]) {
    error.value = `模型 ${nextAlias.value} 已存在`
    return
  }
  const contextSize = Number(draft.value.max_context_size)
  const outputSize = draft.value.max_output_size === null ? null : Number(draft.value.max_output_size)
  if (!Number.isFinite(contextSize) || contextSize <= 0) {
    error.value = 'max_context_size 必须是正整数'
    return
  }
  store.updateModel(props.alias, {
    model: modelId,
    display_name: draft.value.display_name.trim() || null,
    max_context_size: contextSize,
    max_output_size: outputSize && outputSize > 0 ? outputSize : null,
    capabilities: draft.value.capabilities,
    support_efforts: draft.value.support_efforts,
    default_effort: draft.value.default_effort,
  })
  open.value = false
  error.value = null
}

function remove() {
  store.removeModel(props.alias)
}

const contextLabel = computed(() => `${Math.round(props.model.max_context_size / 1000)}k`)
</script>

<template>
  <div class="rounded-[var(--radius-md)] border-[0.5px] border-[var(--color-line)]">
    <button
      type="button"
      class="flex w-full items-center gap-2 px-3 py-2 text-left transition hover:bg-[var(--color-hover)]"
      :aria-expanded="open"
      @click="open ? (open = false) : startEdit()"
    >
      <code class="min-w-0 flex-1 truncate font-mono text-[12px] text-[var(--color-text)]">{{ alias }}</code>
      <span :class="badgeClass('neutral')">{{ contextLabel }}</span>
      <span v-if="model.max_output_size" :class="badgeClass('neutral')">out {{ Math.round(model.max_output_size / 1000) }}k</span>
      <span v-if="model.support_efforts.length" :class="badgeClass('neutral')">{{ model.default_effort || model.support_efforts.at(-1) }}</span>
      <span v-if="isDefault" :class="badgeClass('ok')">默认</span>
      <span v-if="model.display_name" class="hidden max-w-40 truncate text-[12px] text-[var(--color-text-muted)] sm:block">
        {{ model.display_name }}
      </span>
      <ChevronDown class="h-4 w-4 flex-shrink-0 text-[var(--color-text-faint)] transition" :class="open ? 'rotate-180' : ''" />
    </button>

    <div v-if="open" class="border-t-[0.5px] border-[var(--color-line)] px-3 py-3">
      <div class="grid gap-3 sm:grid-cols-2">
        <SettingsField label="模型 id" toml-key="model" hint="服务方使用的模型名，例如 deepseek-v4-flash">
          <input v-model="draft.model" :class="INPUT_CLASS" spellcheck="false">
        </SettingsField>
        <SettingsField label="显示名" toml-key="display_name">
          <input v-model="draft.display_name" :class="INPUT_CLASS" placeholder="可留空">
        </SettingsField>
        <SettingsField label="上下文窗口" toml-key="max_context_size">
          <input v-model.number="draft.max_context_size" :class="INPUT_CLASS" type="number" min="1" step="1000">
        </SettingsField>
        <SettingsField label="单次输出上限" toml-key="max_output_size">
          <input v-model.number="draft.max_output_size" :class="INPUT_CLASS" type="number" min="1" step="500" placeholder="留空即不限制">
        </SettingsField>
      </div>

      <div class="mt-3">
        <SettingsField label="能力" toml-key="capabilities">
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="cap in CAPABILITIES"
              :key="cap.value"
              type="button"
              :class="draft.capabilities.includes(cap.value) ? badgeClass('ok') : badgeClass('neutral')"
              @click="toggleCapability(cap.value)"
            >
              {{ cap.label }}
            </button>
          </div>
        </SettingsField>
      </div>

      <div class="mt-3 grid gap-3 sm:grid-cols-2">
        <SettingsField label="支持的思考档位" toml-key="support_efforts" hint="留空表示该模型不支持 thinking">
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="effort in EFFORTS"
              :key="effort"
              type="button"
              :class="draft.support_efforts.includes(effort) ? badgeClass('ok') : badgeClass('neutral')"
              @click="toggleEffort(effort)"
            >
              {{ effort }}
            </button>
          </div>
        </SettingsField>
        <SettingsField label="默认思考档位" toml-key="default_effort">
          <select v-model="draft.default_effort" :class="SELECT_CLASS" :disabled="draft.support_efforts.length === 0">
            <option :value="null">跟随 [thinking] effort</option>
            <option v-for="effort in draft.support_efforts" :key="effort" :value="effort">{{ effort }}</option>
          </select>
        </SettingsField>
      </div>

      <p v-if="error" class="mt-2 text-[12px] text-[var(--color-danger)]">
        {{ error }}
      </p>

      <div class="mt-3 flex items-center justify-between gap-2">
        <button type="button" :class="BTN_DANGER_CLASS" @click="remove">
          <Trash2 class="h-3.5 w-3.5" />
          删除模型
        </button>
        <div class="flex items-center gap-2">
          <code :class="CODE_CLASS">[models."{{ nextAlias }}"]</code>
          <button type="button" :class="BTN_GHOST_CLASS" @click="open = false">
            取消
          </button>
          <button type="button" :class="BTN_PRIMARY_CLASS" @click="save">
            完成
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
