<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { desktopAvailable, pickFolder } from '@/services/desktop'
import { gatewayService } from '@/services/gateway'
import { useBotsStore } from '@/stores/bots'
import type { Bot, ToolInfo } from '@/types/bot'

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
  role: '',
  description: '',
  persona: '',
  model: '',
  workspace: '',
  tools: [] as string[],
})

const tools = ref<ToolInfo[]>([])
const previewText = ref('')
const previewing = ref(false)

/** The native folder picker only exists in the desktop shell. */
const canPickFolder = computed(() => desktopAvailable())

async function chooseWorkspace(): Promise<void> {
  const picked = await pickFolder()
  if (picked) form.workspace = picked
}

async function loadPreview() {
  if (!props.bot) return
  previewing.value = true
  try {
    const result = await gatewayService.call<{ prompt: string }>('previewPrompt', { botId: props.bot.id })
    previewText.value = result.prompt
  } catch (err) {
    formError.value = err instanceof Error ? err.message : String(err)
  } finally {
    previewing.value = false
  }
}

async function loadTools() {
  if (tools.value.length > 0 || !gatewayService.isConnected()) return
  try {
    tools.value = await gatewayService.call<ToolInfo[]>('listTools')
  } catch {
    tools.value = []
  }
}

function toggleTool(name: string) {
  form.tools = form.tools.includes(name)
    ? form.tools.filter((item) => item !== name)
    : [...form.tools, name]
}

function reset(source: Bot | null) {
  form.name = source?.name ?? ''
  form.emoji = source?.emoji ?? '🤖'
  form.role = source?.role ?? ''
  form.description = source?.description ?? ''
  form.persona = source?.persona ?? ''
  form.model = source?.model ?? ''
  form.workspace = source?.workspace ?? ''
  form.tools = source ? [...source.tools] : []
  formError.value = null
  previewText.value = ''
  void loadTools()
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
      role: form.role.trim(),
      description: form.description.trim(),
      persona: form.persona,
      model: form.model.trim(),
      workspace: form.workspace.trim(),
      tools: form.tools,
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

          <div class="grid grid-cols-[130px_1fr] gap-3">
            <label class="block">
              <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">职位</span>
              <input
                v-model="form.role"
                type="text"
                maxlength="12"
                class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
                placeholder="总管"
              >
            </label>
            <label class="block">
              <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">一句话介绍</span>
              <input
                v-model="form.description"
                type="text"
                maxlength="60"
                class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
                placeholder="显示在侧栏名字下面"
              >
            </label>
          </div>

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
            <div class="flex gap-2">
              <input
                v-model="form.workspace"
                type="text"
                class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
                placeholder="D:\workspace\project"
              >
              <button
                v-if="canPickFolder"
                type="button"
                class="shrink-0 h-[38px] px-3 rounded-[var(--radius-md)] border-0.5 border-[var(--color-line-strong)] bg-[var(--color-surface-overlay)] text-[13px] text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]"
                @click="chooseWorkspace"
              >
                选择…
              </button>
            </div>
          </label>

          <div>
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">
              工具白名单（不选 = 全部工具）
            </span>
            <div v-if="tools.length === 0" class="text-[12px] text-[var(--color-text-faint)]">
              连接网关后可选择
            </div>
            <div v-else class="max-h-40 overflow-y-auto space-y-1">
              <label
                v-for="tool in tools"
                :key="tool.name"
                class="flex items-start gap-2 px-2 py-1.5 rounded-[var(--radius-md)] hover:bg-[var(--color-hover)] cursor-pointer"
              >
                <input
                  type="checkbox"
                  class="mt-0.5 accent-[var(--color-accent)]"
                  :checked="form.tools.includes(tool.name)"
                  @change="toggleTool(tool.name)"
                >
                <span class="min-w-0 flex-1">
                  <span class="block text-[13px] text-[var(--color-text)]">{{ tool.name }}</span>
                  <span class="block text-[11px] text-[var(--color-text-faint)] truncate">
                    {{ tool.description }}
                  </span>
                </span>
              </label>
            </div>
          </div>

          <div v-if="bot">
            <button
              type="button"
              class="h-[30px] px-3 rounded-[var(--radius-md)] text-[13px] text-[var(--color-text)] border-0.5 border-[var(--color-line-strong)] hover:bg-[var(--color-hover)] disabled:opacity-50"
              :disabled="previewing"
              @click="loadPreview"
            >
              {{ previewing ? '生成中…' : '预览 System Prompt' }}
            </button>
            <pre
              v-if="previewText"
              class="mt-2 max-h-48 overflow-y-auto p-2.5 rounded-[var(--radius-md)] bg-[var(--color-surface)] text-[11px] leading-relaxed text-[var(--color-text-muted)] whitespace-pre-wrap"
            >{{ previewText }}</pre>
          </div>

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
