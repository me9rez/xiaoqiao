<script setup lang="ts">
import { reactive, ref, watch } from 'vue'

import { useBotsStore } from '@/stores/bots'
import { useGroupsStore } from '@/stores/groups'
import { useRoutinesStore } from '@/stores/routines'
import type { Routine, RoutineDraftSuggestion, RoutineSchedule, ScheduleKind } from '@/types/routine'

const props = defineProps<{ open: boolean; routine: Routine | null; draft?: RoutineDraftSuggestion | null }>()
const emit = defineEmits<{ close: []; saved: [routine: Routine] }>()

const botsStore = useBotsStore()
const groupsStore = useGroupsStore()
const routinesStore = useRoutinesStore()

const saving = ref(false)
const formError = ref<string | null>(null)

const form = reactive({
  botId: '',
  name: '',
  kind: 'daily' as ScheduleKind,
  at: '09:00',
  minutes: 60,
  once: '',
  prompt: '',
  targetGroupId: '',
  enabled: true,
})

watch(
  () => [props.open, props.routine, props.draft] as const,
  ([open, routine, draft]) => {
    if (!open) return
    form.botId = routine?.botId ?? draft?.botId ?? botsStore.bots[0]?.id ?? ''
    form.name = routine?.name ?? draft?.name ?? ''
    form.kind = routine?.schedule.kind ?? draft?.schedule.kind ?? 'daily'
    form.at = routine?.schedule.at ?? draft?.schedule.at ?? '09:00'
    form.minutes = routine?.schedule.minutes ?? draft?.schedule.minutes ?? 60
    form.once = routine?.schedule.at ? routine.schedule.at.slice(0, 16) : ''
    form.prompt = routine?.prompt ?? draft?.prompt ?? ''
    form.targetGroupId = routine?.targetGroupId ?? draft?.targetGroupId ?? ''
    form.enabled = routine?.enabled ?? true
    formError.value = null
  },
  { immediate: true },
)

function buildSchedule(): RoutineSchedule | null {
  if (form.kind === 'daily') {
    if (!/^\d{2}:\d{2}$/.test(form.at)) return null
    return { kind: 'daily', at: form.at, tz: 'Asia/Shanghai' }
  }
  if (form.kind === 'interval') {
    const minutes = Number(form.minutes)
    if (!Number.isFinite(minutes) || minutes <= 0) return null
    return { kind: 'interval', minutes }
  }
  if (!form.once) return null
  const moment = new Date(form.once)
  if (Number.isNaN(moment.getTime())) return null
  return { kind: 'once', at: moment.toISOString() }
}

async function handleSave() {
  if (!form.name.trim()) {
    formError.value = '任务名称不能为空'
    return
  }
  if (!form.botId) {
    formError.value = '请选择一个 Bot'
    return
  }
  if (!form.prompt.trim()) {
    formError.value = '执行指令不能为空'
    return
  }
  const schedule = buildSchedule()
  if (!schedule) {
    formError.value = '时间设置不完整'
    return
  }

  saving.value = true
  formError.value = null
  try {
    const payload = {
      botId: form.botId,
      name: form.name.trim(),
      schedule,
      prompt: form.prompt,
      targetGroupId: form.targetGroupId || null,
      enabled: form.enabled,
      steps: props.routine ? undefined : (props.draft?.steps ?? []),
    }
    const saved = props.routine
      ? await routinesStore.update(props.routine.id, payload)
      : await routinesStore.create(payload)
    if (saved) {
      emit('saved', saved)
      emit('close')
    } else {
      formError.value = routinesStore.error ?? '保存失败'
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
      aria-label="编辑定时任务"
      @click="closeOverlay"
    >
      <div
        class="w-full max-w-[440px] max-h-[calc(100vh-64px)] flex flex-col rounded-[var(--radius-xl)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] shadow-[var(--shadow-xl)]"
      >
        <header class="px-5 pt-5 pb-3">
          <h2 class="text-[16px] font-[var(--weight-medium)] text-[var(--color-text-strong)]">
            {{ routine ? '编辑定时任务' : '新建定时任务' }}
          </h2>
          <p class="mt-1 text-[14px] text-[var(--color-text-muted)]">到点后由 Bot 自己执行，结果发到群聊。</p>
        </header>

        <div class="px-5 pb-4 overflow-y-auto space-y-4">
          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">名称</span>
            <input
              v-model="form.name"
              type="text"
              class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              placeholder="例如 每日简报"
            >
          </label>

          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">执行 Bot</span>
            <select
              v-model="form.botId"
              class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
            >
              <option v-for="bot in botsStore.bots" :key="bot.id" :value="bot.id">{{ bot.name }}</option>
            </select>
          </label>

          <div>
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">频率</span>
            <div class="flex items-center gap-2">
              <select
                v-model="form.kind"
                class="h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              >
                <option value="daily">每天</option>
                <option value="interval">间隔</option>
                <option value="once">一次</option>
              </select>

              <input
                v-if="form.kind === 'daily'"
                v-model="form.at"
                type="time"
                class="h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              >
              <template v-else-if="form.kind === 'interval'">
                <input
                  v-model.number="form.minutes"
                  type="number"
                  min="1"
                  class="w-20 h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
                >
                <span class="text-[13px] text-[var(--color-text-muted)]">分钟一次</span>
              </template>
              <input
                v-else
                v-model="form.once"
                type="datetime-local"
                class="h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[13px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              >
            </div>
            <span v-if="form.kind === 'daily'" class="block mt-1 text-[12px] text-[var(--color-text-faint)]">
              时区 Asia/Shanghai
            </span>
          </div>

          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">执行指令</span>
            <textarea
              v-model="form.prompt"
              rows="4"
              class="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[13px] leading-relaxed text-[var(--color-text)] outline-none resize-none focus-visible:shadow-[var(--p-focus-ring)]"
              placeholder="整理今天的行情，写一段简报发到群里。"
            />
          </label>

          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">
              结果发到（可选）
            </span>
            <select
              v-model="form.targetGroupId"
              class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
            >
              <option value="">不投递（只记录运行）</option>
              <option v-for="group in groupsStore.groups" :key="group.id" :value="group.id">
                {{ group.name }}
              </option>
            </select>
          </label>

          <label class="flex items-center gap-2 text-[13px] text-[var(--color-text)]">
            <input v-model="form.enabled" type="checkbox" class="accent-[var(--color-accent)]">
            启用
          </label>

          <p v-if="formError" class="text-[13px] text-[var(--color-danger)]" role="alert">{{ formError }}</p>
        </div>

        <footer class="px-5 py-3.5 flex items-center justify-end gap-2.5 border-t border-[var(--color-line)]">
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
