<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import BotAvatar from '@/components/bots/BotAvatar.vue'
import BotStatusDot from '@/components/bots/BotStatusDot.vue'
import RoutineEditorModal from '@/components/routines/RoutineEditorModal.vue'
import { gatewayService } from '@/services/gateway'
import EmptyStateView from '@/views/EmptyStateView.vue'
import { useActivityStore } from '@/stores/activity'
import { useBotsStore } from '@/stores/bots'
import type { BotActivity } from '@/types/activity'
import type { Bot } from '@/types/bot'
import type { RoutineDraftSuggestion } from '@/types/routine'

/**
 * The home screen answers "现在在发生什么"，and falls back to the composer when
 * nothing is running. Order is fixed: 等你 > (出错的也算等你) > 在忙 > 刚完成.
 */
const activityStore = useActivityStore()
const botsStore = useBotsStore()
const router = useRouter()

const RECENT_WINDOW_MS = 60 * 60 * 1000

const draftOpen = ref(false)
const suggestion = ref<RoutineDraftSuggestion | null>(null)
const draftError = ref<string | null>(null)

onMounted(() => {
  if (!activityStore.snapshot) void activityStore.load()
})

function bot(botId: string): Bot | undefined {
  return botsStore.bots.find((candidate) => candidate.id === botId)
}

function botName(botId: string): string {
  return bot(botId)?.name || 'Bot'
}

interface Card extends BotActivity {
  name: string
  emoji: string
  target: { name: string; params?: Record<string, string> }
  hint: string
  time: string
}

function clock(iso?: string | null): string {
  if (!iso) return ''
  const when = new Date(iso)
  if (Number.isNaN(when.getTime())) return ''
  return when.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function targetOf(entry: BotActivity): { name: string; params?: Record<string, string> } {
  if (entry.groupId) return { name: 'group', params: { groupId: entry.groupId } }
  if (entry.sessionId) return { name: 'chat-session', params: { sessionId: entry.sessionId } }
  return { name: 'chat-home' }
}

function toCard(entry: BotActivity): Card {
  const summary = entry.lastFinished
  const finishedRecently =
    summary?.endedAt !== undefined && summary?.endedAt !== null
      ? Date.now() - new Date(summary.endedAt).getTime() < RECENT_WINDOW_MS
      : false
  const time = clock(entry.state === 'idle' ? summary?.endedAt : entry.startedAt)
  const hint =
    entry.state === 'needs_you'
      ? '卡在审批，等你处理'
      : entry.state === 'error'
        ? '最近一次运行失败了'
        : entry.state === 'working'
          ? entry.currentTool
            ? `正在用 ${entry.currentTool}`
            : '正在处理'
          : summary?.status === 'failed'
            ? `${time} 失败`
            : `${time} 已完成`
  return {
    ...entry,
    name: botName(entry.botId),
    emoji: bot(entry.botId)?.emoji || '🤖',
    target: targetOf(entry),
    hint,
    time: finishedRecently ? time : time,
  }
}

const needsYou = computed(() => activityStore.bots.filter((e) => e.state === 'needs_you').map(toCard))
const failing = computed(() => activityStore.bots.filter((e) => e.state === 'error').map(toCard))
const working = computed(() => activityStore.bots.filter((e) => e.state === 'working').map(toCard))
const recent = computed(() =>
  activityStore.bots
    .filter((entry) => {
      if (entry.state !== 'idle') return false
      const ended = entry.lastFinished?.endedAt
      return Boolean(ended) && Date.now() - new Date(ended as string).getTime() < RECENT_WINDOW_MS
    })
    .map(toCard),
)

const hasActivity = computed(
  () => needsYou.value.length + failing.value.length + working.value.length + recent.value.length > 0,
)

async function saveAsRoutine(card: Card) {
  const runId = card.runId || card.lastFinished?.runId
  if (!runId) return
  draftError.value = null
  try {
    suggestion.value = await gatewayService.call<RoutineDraftSuggestion>('draftRoutineFromRun', { runId })
    draftOpen.value = true
  } catch (err) {
    draftError.value = err instanceof Error ? err.message : String(err)
  }
}

function open(card: Card) {
  if (card.state === 'needs_you') {
    void router.push({ name: 'runs' })
    return
  }
  void router.push(card.target)
}
</script>

<template>
  <div class="flex-1 overflow-y-auto">
    <EmptyStateView v-if="!hasActivity" />

    <div v-else class="mx-auto max-w-3xl px-6 py-8 space-y-8">
      <section v-if="needsYou.length" aria-labelledby="now-needs-you">
        <h2 id="now-needs-you" class="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-[var(--color-warning)]">
          <span>等你</span>
          <span class="px-1.5 py-0.5 rounded-full bg-[var(--color-warning-soft)] border border-[var(--color-warning-bd)] text-[10px]">
            {{ needsYou.length }}
          </span>
        </h2>
        <ul class="mt-2 space-y-1.5">
          <li v-for="card in needsYou" :key="card.botId">
            <button
              type="button"
              class="w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-lg)] border border-[var(--color-warning-bd)] bg-[var(--color-warning-soft)] text-left transition-colors duration-[var(--duration-base)] hover:bg-[var(--color-surface-raised)] focus-visible:outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              @click="open(card)"
            >
              <BotAvatar :bot="{ name: card.name, emoji: card.emoji }" size="sm" />
              <span class="min-w-0 flex-1">
                <span class="block text-sm font-medium truncate">{{ card.name }}</span>
                <span class="block text-xs text-[var(--color-text-muted)] truncate">{{ card.title || card.hint }}</span>
              </span>
              <span class="text-xs text-[var(--color-warning)] shrink-0">去处理</span>
            </button>
          </li>
        </ul>
      </section>

      <section v-if="failing.length" aria-labelledby="now-failing">
        <h2 id="now-failing" class="text-xs font-bold uppercase tracking-wide text-[var(--color-danger)]">需要看一眼</h2>
        <ul class="mt-2 space-y-1.5">
          <li v-for="card in failing" :key="card.botId">
            <button
              type="button"
              class="w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-lg)] border border-[var(--color-danger-bd)] bg-[var(--color-danger-soft)] text-left transition-colors duration-[var(--duration-base)] hover:bg-[var(--color-surface-raised)] focus-visible:outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              @click="open(card)"
            >
              <BotAvatar :bot="{ name: card.name, emoji: card.emoji }" size="sm" />
              <span class="min-w-0 flex-1">
                <span class="block text-sm font-medium truncate">{{ card.name }}</span>
                <span class="block text-xs text-[var(--color-text-muted)] truncate">{{ card.title || '最近一次运行失败' }}</span>
              </span>
              <span class="text-xs text-[var(--color-danger)] shrink-0">看记录</span>
            </button>
          </li>
        </ul>
      </section>

      <section v-if="working.length" aria-labelledby="now-working">
        <h2 id="now-working" class="text-xs font-bold uppercase tracking-wide text-[var(--color-text-subtle)]">在忙</h2>
        <ul class="mt-2 space-y-1.5">
          <li v-for="card in working" :key="card.botId">
            <button
              type="button"
              class="w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] text-left transition-colors duration-[var(--duration-base)] hover:bg-[var(--color-hover)] focus-visible:outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              @click="open(card)"
            >
              <BotAvatar :bot="{ name: card.name, emoji: card.emoji }" size="sm" />
              <span class="min-w-0 flex-1">
                <span class="block text-sm font-medium truncate">{{ card.name }}</span>
                <span class="block text-xs text-[var(--color-text-muted)] truncate">{{ card.title || card.hint }}</span>
              </span>
              <BotStatusDot :state="card.state" :label="`${card.name} 正在忙`" size="sm" />
              <span class="text-xs text-[var(--color-text-subtle)] shrink-0">{{ card.hint }}</span>
            </button>
          </li>
        </ul>
      </section>

      <section v-if="recent.length" aria-labelledby="now-recent">
        <h2 id="now-recent" class="text-xs font-bold uppercase tracking-wide text-[var(--color-text-subtle)]">刚完成</h2>
        <ul class="mt-2 space-y-1.5">
          <li v-for="card in recent" :key="card.botId">
            <button
              type="button"
              class="w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-lg)] border border-transparent text-left transition-colors duration-[var(--duration-base)] hover:bg-[var(--color-hover)] focus-visible:outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              @click="open(card)"
            >
              <BotAvatar :bot="{ name: card.name, emoji: card.emoji }" size="sm" />
              <span class="min-w-0 flex-1">
                <span class="block text-sm truncate text-[var(--color-text-muted)]">{{ card.name }}</span>
                <span class="block text-xs text-[var(--color-text-subtle)] truncate">{{ card.title || '刚完成一次运行' }}</span>
              </span>
              <span class="text-xs text-[var(--color-text-subtle)] shrink-0">{{ card.hint }}</span>
              <span
                class="text-xs text-[var(--color-accent)] shrink-0 hover:underline"
                role="button"
                tabindex="0"
                @click.stop="saveAsRoutine(card)"
                @keydown.enter.stop="saveAsRoutine(card)"
              >存为定时任务</span>
            </button>
          </li>
        </ul>
      </section>

      <p v-if="draftError" class="text-xs text-[var(--color-danger)]" role="alert">{{ draftError }}</p>
    </div>

    <RoutineEditorModal :open="draftOpen" :routine="null" :draft="suggestion" @close="draftOpen = false" />
  </div>
</template>
