<script setup lang="ts">
import { CalendarClock, Plus } from '@lucide/vue'
import { onMounted, onUnmounted, ref } from 'vue'

import RoutineEditorModal from '@/components/routines/RoutineEditorModal.vue'
import { useBotsStore } from '@/stores/bots'
import { useGroupsStore } from '@/stores/groups'
import { useRoutinesStore } from '@/stores/routines'
import type { Routine } from '@/types/routine'

const routinesStore = useRoutinesStore()
const botsStore = useBotsStore()
const groupsStore = useGroupsStore()

const editorOpen = ref(false)
const editing = ref<Routine | null>(null)
let unsubscribe: (() => void) | null = null

function openEditor(routine: Routine | null) {
  editing.value = routine
  editorOpen.value = true
}

function closeEditor() {
  editorOpen.value = false
  editing.value = null
}

function botName(botId: string): string {
  return botsStore.bots.find((bot) => bot.id === botId)?.name ?? 'Bot'
}

function groupName(groupId: string | null): string {
  if (!groupId) return '—'
  return groupsStore.groups.find((group) => group.id === groupId)?.name ?? '群聊'
}

function summarize(routine: Routine): string {
  const schedule = routine.schedule
  if (schedule.kind === 'daily') return `每天 ${schedule.at}（${schedule.tz ?? 'UTC'}）`
  if (schedule.kind === 'interval') return `每 ${schedule.minutes} 分钟`
  if (schedule.kind === 'once' && schedule.at) {
    return `一次 · ${new Date(schedule.at).toLocaleString('zh-CN')}`
  }
  return '未设置'
}

function formatMoment(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function toggle(routine: Routine) {
  await routinesStore.toggle(routine.id, !routine.enabled)
}

async function remove(routine: Routine) {
  if (!window.confirm(`删除定时任务「${routine.name}」？`)) return
  await routinesStore.remove(routine.id)
}

onMounted(() => {
  void routinesStore.load()
  if (botsStore.bots.length === 0) void botsStore.load()
  if (groupsStore.groups.length === 0) void groupsStore.load()
  unsubscribe = routinesStore.listen()
})

onUnmounted(() => {
  unsubscribe?.()
})
</script>

<template>
  <div class="h-full overflow-y-auto p-8 max-w-3xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-[20px] font-[var(--weight-semibold)] text-[var(--color-text-strong)]">定时任务</h1>
        <p class="mt-1 text-[13px] text-[var(--color-text-muted)]">
          到点由 Bot 自己执行；结果会发到指定群聊。共 {{ routinesStore.routines.length }} 条，启用
          {{ routinesStore.enabledCount }} 条。
        </p>
      </div>
      <button
        type="button"
        class="flex items-center gap-1.5 h-[36px] px-4 rounded-[var(--radius-md)] text-[14px] font-[var(--weight-medium)] text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)]"
        @click="openEditor(null)"
      >
        <Plus class="w-4 h-4" />
        新建
      </button>
    </div>

    <p v-if="routinesStore.error" class="mb-4 text-[13px] text-[var(--color-danger)]" role="alert">
      {{ routinesStore.error }}
    </p>

    <div v-if="routinesStore.loading" class="text-[13px] text-[var(--color-text-muted)]">加载中…</div>

    <div
      v-else-if="routinesStore.routines.length === 0"
      class="py-16 text-center text-[13px] text-[var(--color-text-muted)]"
    >
      <CalendarClock class="w-10 h-10 mx-auto mb-3 text-[var(--color-text-faint)]" />
      还没有定时任务。建一条，让 Bot 每天自己开工。
    </div>

    <div v-else class="space-y-3">
      <article
        v-for="routine in routinesStore.routines"
        :key="routine.id"
        class="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]"
      >
        <div class="flex items-center gap-2">
          <span class="text-[14px] font-[var(--weight-medium)] text-[var(--color-text-strong)]">
            {{ routine.name }}
          </span>
          <span class="text-[12px] text-[var(--color-text-muted)]">{{ botName(routine.botId) }}</span>
          <span
            v-if="!routine.enabled"
            class="px-2 py-0.5 rounded-full text-[11px] text-[var(--color-text-muted)] bg-[var(--color-surface)] border border-[var(--color-line)]"
          >
            已暂停
          </span>
          <span class="flex-1" />
          <button
            type="button"
            class="h-[30px] px-3 rounded-[var(--radius-md)] text-[13px] border-0.5 border-[var(--color-line-strong)] text-[var(--color-text)] hover:bg-[var(--color-hover)]"
            @click="openEditor(routine)"
          >
            编辑
          </button>
          <button
            type="button"
            class="h-[30px] px-3 rounded-[var(--radius-md)] text-[13px] text-[var(--color-text-muted)] hover:bg-[var(--color-hover)]"
            @click="toggle(routine)"
          >
            {{ routine.enabled ? '暂停' : '启用' }}
          </button>
          <button
            type="button"
            class="h-[30px] px-3 rounded-[var(--radius-md)] text-[13px] text-[var(--color-danger)] hover:bg-[var(--color-danger-soft)]"
            @click="remove(routine)"
          >
            删除
          </button>
        </div>

        <div class="mt-2.5 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[12px] text-[var(--color-text-muted)]">
          <span class="flex items-center gap-1.5">
            <CalendarClock class="w-3.5 h-3.5" />
            {{ summarize(routine) }}
          </span>
          <span>下次：{{ formatMoment(routine.nextRunAt) }}</span>
          <span>上次：{{ formatMoment(routine.lastRunAt) }}</span>
          <span>投递：{{ groupName(routine.targetGroupId) }}</span>
        </div>

        <p class="mt-2 text-[13px] leading-relaxed text-[var(--color-text)] line-clamp-2">{{ routine.prompt }}</p>
      </article>
    </div>

    <RoutineEditorModal :open="editorOpen" :routine="editing" @close="closeEditor" />
  </div>
</template>
