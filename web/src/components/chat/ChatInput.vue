<script setup lang="ts">
import { Plus, Send, Square, X } from '@lucide/vue'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { onComposerInsert } from '@/services/composer'
import { useChatStore } from '@/stores/chat'
import { useSettingsStore } from '@/stores/settings'
import ModelPicker from './ModelPicker.vue'

const props = defineProps<{
  disabled?: boolean
  model?: string
}>()

const emit = defineEmits<{
  send: [text: string]
  stop: []
  'update:model': [value: string]
}>()

const chatStore = useChatStore()
const settingsStore = useSettingsStore()
const text = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

let unsubscribeComposer: (() => void) | null = null

const effectiveModel = computed(() => props.model || settingsStore.settings.default_model || '')
const hasModels = computed(() => Object.keys(settingsStore.settings.models).length > 0)

const estimatedTokens = computed(() => {
  let chars = 0
  for (const m of chatStore.messages) {
    chars += m.content.length
    if (m.thinking) chars += m.thinking.length
    if (m.toolExecution) chars += m.toolExecution.output.length
  }
  return Math.round(chars / 4)
})

function handleModelChange(value: string) {
  if (!value) return
  emit('update:model', value)
  void settingsStore.setDefaultModel(value)
}

function adjustHeight() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

function handleSend() {
  const value = text.value.trim()
  if (!value || props.disabled) return
  emit('send', value)
  text.value = ''
  nextTick(adjustHeight)
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

function handleInput() {
  adjustHeight()
}

function handleStop() {
  emit('stop')
}

function setText(value: string) {
  text.value = value
  nextTick(adjustHeight)
  nextTick(() => textareaRef.value?.focus())
}

defineExpose({ setText })

onMounted(() => {
  // Files dragged onto the desktop window land here as real paths.
  unsubscribeComposer = onComposerInsert((inserted) => {
    text.value = text.value ? `${text.value}\n${inserted}` : inserted
    nextTick(adjustHeight)
    nextTick(() => textareaRef.value?.focus())
  })
})

onUnmounted(() => {
  unsubscribeComposer?.()
})
</script>

<template>
  <div class="px-6 py-4 border-t border-[var(--border)] bg-[var(--bg-page)]">
    <div class="max-w-4xl mx-auto">
      <div class="rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] shadow-[var(--shadow)] px-4 py-3">
        <div
          v-if="chatStore.pendingQuote"
          class="mb-2 flex items-start gap-2 rounded-xl border-l-2 border-[var(--color-accent)] bg-[var(--color-surface-sunken)] px-2.5 py-1.5"
        >
          <div class="min-w-0 flex-1">
            <p class="text-[11px] font-medium text-[var(--color-text-muted)]">
              引用 {{ chatStore.pendingQuote.authorName }}
            </p>
            <p class="truncate text-[12px] text-[var(--color-text-faint)]">
              {{ chatStore.pendingQuote.text }}
            </p>
          </div>
          <button
            type="button"
            class="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-[var(--color-text-faint)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
            aria-label="取消引用"
            @click="chatStore.clearQuote()"
          >
            <X class="h-3.5 w-3.5" />
          </button>
        </div>
        <textarea
          ref="textareaRef"
          v-model="text"
          rows="2"
          :disabled="disabled"
          placeholder="想让小巧帮你做点什么？"
          class="w-full resize-none bg-transparent outline-none text-sm leading-relaxed mb-3 placeholder:text-[var(--text-subtle)]"
          @keydown="handleKeydown"
          @input="handleInput"
        />

        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <button class="p-1.5 rounded-lg text-[var(--text-subtle)] hover:bg-[var(--bg-muted)] transition">
              <Plus class="w-4 h-4" />
            </button>
          </div>

          <div class="flex items-center gap-2">
            <ModelPicker
              v-if="hasModels"
              :value="effectiveModel"
              placement="top"
              @change="handleModelChange"
            />
            <button
              v-if="disabled"
              class="p-2 rounded-xl bg-[var(--bg-muted)] text-[var(--text)] hover:bg-[var(--border)] transition"
              title="停止"
              @click="handleStop"
            >
              <Square class="w-4 h-4" />
            </button>
            <button
              v-else
              class="p-2 rounded-xl bg-[var(--text)] text-[var(--bg-card)] hover:opacity-90 transition disabled:opacity-40"
              :disabled="!text.trim()"
              @click="handleSend"
            >
              <Send class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-center mt-2 px-1">
        <div class="text-xs text-[var(--text-subtle)]">
          上下文水位 · 本地估算 {{ estimatedTokens.toLocaleString() }} tokens
        </div>
      </div>
    </div>
  </div>
</template>
