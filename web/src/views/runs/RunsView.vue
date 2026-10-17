<script setup lang="ts">
import { Activity, RefreshCw } from '@lucide/vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { useBotsStore } from '@/stores/bots'
import { useGroupsStore } from '@/stores/groups'
import { useRunsStore } from '@/stores/runs'
import type { RunRecord, RunStatus } from '@/types/run'

const runsStore = useRunsStore()
const botsStore = useBotsStore()
const groupsStore = useGroupsStore()

const tab = ref<'all' | 'failed' | 'active'>('all')
let unsubscribe: (() => void) | null = null

const visible = computed(() => {
  if (tab.value === 'failed') return runsStore.items.filter((run) => run.status === 'failed')
  if (tab.value === 'active') {
    return runsStore.items.filter((run) => run.status === 'running' || run.status === 'waiting_approval')
  }
  return runsStore.items
})

function botName(botId: string): string {
  return botsStore.bots.find((bot) => bot.id === botId)?.name ?? 'Bot'
}

function groupName(groupId: string | null): string {
  if (!groupId) return '—'
  return groupsStore.groups.find((group) => group.id === groupId)?.name ?? '群聊'
}

function statusLabel(status: RunStatus): string {
  return {
    queued: '排队',
    running: '运行中',
    waiting_approval: '待审批',
    done: '完成',
    failed: '失败',
    cancelled: '已取消',
  }[status]
}

function statusClass(status: RunStatus): string {
  if (status === 'done') {
    return 'text-[var(--color-success)] bg-[var(--color-success-soft)] border-[var(--color-success-bd)]'
  }
  if (status === 'failed') {
    return 'text-[var(--color-danger)] bg-[var(--color-danger-soft)] border-[var(--color-danger-bd)]'
  }
  if (status === 'waiting_approval') {
    return 'text-[var(--color-warning)] bg-[var(--color-warning-soft)] border-[var(--color-warning-bd)]'
  }
  if (status === 'running') {
    return 'text-[var(--color-accent)] bg-[var(--color-accent-soft)] border-[var(--color-accent-bd)]'
  }
  return 'text-[var(--color-text-muted)] bg-[var(--color-surface)] border-[var(--color-line)]'
}

function triggerLabel(trigger: string): string {
  return { web: '网页', group: '群聊', telegram: 'Telegram', routine: '定时任务', api: 'API' }[trigger] ?? trigger
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
    second: '2-digit',
  })
}

function duration(run: RunRecord): string {
  if (!run.startedAt || !run.endedAt) return '—'
  const ms = new Date(run.endedAt).getTime() - new Date(run.startedAt).getTime()
  if (Number.isNaN(ms) || ms < 0) return '—'
  if (ms < 1000) return `${ms} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`
  return `${(ms / 60_000).toFixed(1)} min`
}

async function reload() {
  await runsStore.load()
}

onMounted(() => {
  void reload()
  if (botsStore.bots.length === 0) void botsStore.load()
  if (groupsStore.groups.length === 0) void groupsStore.load()
  unsubscribe = runsStore.listen()
})

onUnmounted(() => {
  unsubscribe?.()
})
</script>

<template>
  <div class="h-full overflow-y-auto p-8 max-w-4xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-[20px] font-[var(--weight-semibold)] text-[var(--color-text-strong)]">运行记录</h1>
        <p class="mt-1 text-[13px] text-[var(--color-text-muted)]">
          每次执行都可追溯：谁触发、用了多久、成功还是失败。失败
          {{ runsStore.failedCount }} · 进行中 {{ runsStore.runningCount }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <div class="flex items-center gap-1 p-0.5 rounded-[var(--radius-md)] bg-[var(--color-surface-sunken)] border border-[var(--color-line)]">
          <button
            v-for="option in (['all', 'active', 'failed'] as const)"
            :key="option"
            type="button"
            class="px-3 py-1 rounded-[var(--radius-sm)] text-[13px] transition-colors duration-[var(--duration-fast)]"
            :class="
              tab === option
                ? 'bg-[var(--color-surface-raised)] shadow-[var(--shadow-sm)] text-[var(--color-text)]'
                : 'text-[var(--color-text-muted)]'
            "
            @click="tab = option"
          >
            {{ option === 'all' ? '全部' : option === 'active' ? '进行中' : '失败' }}
          </button>
        </div>
        <button
          type="button"
          class="p-2 rounded-[var(--radius-md)] text-[var(--color-text-muted)] hover:bg-[var(--color-hover)]"
          aria-label="刷新"
          @click="reload"
        >
          <RefreshCw class="w-4 h-4" />
        </button>
      </div>
    </div>

    <p v-if="runsStore.error" class="mb-4 text-[13px] text-[var(--color-danger)]" role="alert">
      {{ runsStore.error }}
    </p>

    <div v-if="runsStore.loading" class="text-[13px] text-[var(--color-text-muted)]">加载中…</div>

    <div v-else-if="visible.length === 0" class="py-16 text-center text-[13px] text-[var(--color-text-muted)]">
      <Activity class="w-10 h-10 mx-auto mb-3 text-[var(--color-text-faint)]" />
      还没有运行记录。
    </div>

    <div v-else class="space-y-2">
      <article
        v-for="run in visible"
        :key="run.id"
        class="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] px-4 py-3 shadow-[var(--shadow-sm)]"
      >
        <div class="flex items-center gap-2 flex-wrap">
          <span class="px-2 py-0.5 rounded-full text-[11px] border" :class="statusClass(run.status)">
            {{ statusLabel(run.status) }}
          </span>
          <span class="text-[13px] font-[var(--weight-medium)] text-[var(--color-text-strong)]">
            {{ botName(run.botId) }}
          </span>
          <span class="text-[12px] text-[var(--color-text-muted)]">{{ triggerLabel(run.trigger) }}</span>
          <span class="text-[12px] text-[var(--color-text-muted)]">{{ groupName(run.groupId) }}</span>
          <span class="flex-1" />
          <span class="text-[12px] text-[var(--color-text-faint)]">{{ duration(run) }}</span>
          <span class="text-[12px] text-[var(--color-text-faint)]">{{ formatMoment(run.createdAt) }}</span>
        </div>
        <p v-if="run.error" class="mt-1.5 text-[12px] text-[var(--color-danger)] break-words">
          {{ run.error }}
        </p>
      </article>
    </div>
  </div>
</template>
