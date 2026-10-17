<script setup lang="ts">
import { reactive, ref, watch } from 'vue'

import { useBotsStore } from '@/stores/bots'
import type { Bot } from '@/types/bot'

const props = defineProps<{
  open: boolean
  bot: Bot | null
}>()

const emit = defineEmits<{ close: []; saved: [bot: Bot] }>()

const botsStore = useBotsStore()
const saving = ref(false)
const formError = ref<string | null>(null)

const form = reactive({
  name: '',
  emoji: '🤖',
  persona: '',
  model: '',
  workspace: '',
})

function reset(source: Bot | null) {
  form.name = source?.name ?? ''
  form.emoji = source?.emoji ?? '🤖'
  form.persona = source?.persona ?? ''
  form.model = source?.model ?? ''
  form.workspace = source?.workspace ?? ''
  formError.value = null
}

watch(
  () => [props.open, props.bot] as const,
  ([open, bot]) => {
    if (open) reset(bot)
  },
  { immediate: true },
)

async function handleSave() {
  if (!form.name.trim()) {
    formError.value = 'Bot 名称不能为空'
    return
  }
  saving.value = true
  formError.value = null
  try {
    const payload = {
      name: form.name.trim(),
      emoji: form.emoji.trim() || '🤖',
      persona: form.persona,
      model: form.model.trim(),
      workspace: form.workspace.trim(),
    }
    const saved = props.bot
      ? await botsStore.update(props.bot.id, payload)
      : await botsStore.create(payload)
    if (saved) {
      emit('saved', saved)
      emit('close')
    } else {
      formError.value = botsStore.error ?? '保存失败'
    }
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (!props.bot) return
  if (!window.confirm(`删除 Bot「${props.bot.name}」？该 Bot 的会话会一并删除，且不可恢复。`)) {
    return
  }
  saving.value = true
  try {
    const ok = await botsStore.remove(props.bot.id)
    if (ok) {
      emit('close')
    } else {
      formError.value = botsStore.error ?? '删除失败（最后一个 Bot 不能删除）'
    }
  } finally {
    saving.value = false
  }
}

function closeOverlay(event: MouseEvent) {
  if (event.target === event.currentTarget) emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center p-6 bg-[#0d111747]"
      role="dialog"
      aria-modal="true"
      aria-label="编辑 Bot"
      @click="closeOverlay"
    >
      <div
        class="w-full max-w-[440px] max-h-[calc(100vh-64px)] flex flex-col rounded-[var(--radius-xl)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] shadow-[var(--shadow-xl)]"
      >
        <header class="px-5 pt-5 pb-3">
          <h2 class="text-[16px] font-[var(--weight-medium)] text-[var(--color-text-strong)]">
            {{ bot ? '编辑 Bot' : '新建 Bot' }}
          </h2>
          <p class="mt-1 text-[14px] text-[var(--color-text-muted)]">
            人格、模型与工作目录都只作用于这个 Bot。
          </p>
        </header>

        <div class="px-5 pb-4 overflow-y-auto space-y-4">
          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">名称</span>
            <input
              v-model="form.name"
              type="text"
              class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              placeholder="例如 Coder、盯盘"
            >
          </label>

          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">头像</span>
            <input
              v-model="form.emoji"
              type="text"
              maxlength="4"
              class="w-24 h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[18px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              placeholder="🤖"
            >
          </label>

          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">人格</span>
            <textarea
              v-model="form.persona"
              rows="5"
              class="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[13px] leading-relaxed text-[var(--color-text)] outline-none resize-none focus-visible:shadow-[var(--p-focus-ring)]"
              placeholder="你说话简洁直接，像一个靠谱的朋友。"
            />
            <span class="block mt-1 text-[12px] text-[var(--color-text-faint)]">
              会拼进 system prompt，立即影响回答。
            </span>
          </label>

          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">
              模型（留空用全局默认）
            </span>
            <input
              v-model="form.model"
              type="text"
              class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              placeholder="deepseek/deepseek-v4-flash"
            >
          </label>

          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">
              工作目录（留空用当前目录）
            </span>
            <input
              v-model="form.workspace"
              type="text"
              class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              placeholder="D:\workspace\project"
            >
          </label>

          <p v-if="formError" class="text-[13px] text-[var(--color-danger)]" role="alert">
            {{ formError }}
          </p>
        </div>

        <footer class="px-5 py-3.5 flex items-center gap-2.5 border-t border-[var(--color-line)]">
          <button
            v-if="bot"
            type="button"
            class="h-[36px] px-4 rounded-[var(--radius-md)] text-[14px] font-[var(--weight-medium)] text-[var(--color-danger)] bg-[var(--color-danger-soft)] border-0.5 border-[var(--color-danger-bd)] hover:brightness-95 disabled:opacity-50"
            :disabled="saving"
            @click="handleDelete"
          >
            删除
          </button>
          <span class="flex-1" />
          <button
            type="button"
            class="h-[36px] px-4 rounded-[var(--radius-md)] text-[14px] text-[var(--color-text)] bg-[var(--color-surface-raised)] border-0.5 border-[var(--color-line-strong)] hover:bg-[var(--color-hover)] disabled:opacity-50"
            :disabled="saving"
            @click="emit('close')"
          >
            取消
          </button>
          <button
            type="button"
            class="h-[36px] px-4 rounded-[var(--radius-md)] text-[14px] font-[var(--weight-medium)] text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
            :disabled="saving"
            @click="handleSave"
          >
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>
