<script setup lang="ts">
import { ArrowLeft } from '@lucide/vue'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BotStatusDot from '@/components/bots/BotStatusDot.vue'
import { useActivityStore } from '@/stores/activity'
import { useBotsStore } from '@/stores/bots'
import { useGroupsStore } from '@/stores/groups'
import { useSessionsStore } from '@/stores/sessions'

const sessionsStore = useSessionsStore()
const botsStore = useBotsStore()
const groupsStore = useGroupsStore()
const activityStore = useActivityStore()
const route = useRoute()
const router = useRouter()

const groupId = computed(() => (typeof route.params.groupId === 'string' ? route.params.groupId : ''))
const sessionId = computed(() => (typeof route.params.sessionId === 'string' ? route.params.sessionId : ''))

const group = computed(() => groupsStore.groups.find((item) => item.id === groupId.value) ?? null)

/** Emoji stack for a group, single emoji otherwise. */
const emojis = computed<string[]>(() => {
  if (group.value) {
    const list = group.value.botIds
      .map((id) => botsStore.bots.find((bot) => bot.id === id)?.emoji || '🤖')
      .slice(0, 3)
    if (list.length > 0) return list
  }
  return [botsStore.activeBot?.emoji || '🤖']
})

const title = computed(() => {
  if (group.value) return group.value.name
  if (sessionId.value) {
    const session = sessionsStore.sessions.find((s) => s.id === sessionId.value)
    return session?.title || '未命名会话'
  }
  return botsStore.activeBot?.name || '小巧'
})

const state = computed(() => {
  if (group.value) {
    const states = group.value.botIds.map((id) => activityStore.stateOf(id))
    if (states.includes('needs_you')) return 'needs_you' as const
    if (states.includes('working')) return 'working' as const
    if (states.includes('error')) return 'error' as const
    return 'idle' as const
  }
  if (botsStore.activeBot) return activityStore.stateOf(botsStore.activeBot.id)
  return 'idle' as const
})

const showBack = computed(() => Boolean(groupId.value || sessionId.value))

function goBack() {
  void router.push({ name: 'chat-home' })
}
</script>

<template>
  <header class="relative flex h-14 flex-shrink-0 items-center justify-center px-4">
    <div
      class="flex max-w-[70%] items-center gap-2 rounded-[var(--radius-full)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] py-1 pl-2 pr-3 shadow-[var(--shadow-xs)]"
    >
      <span class="flex items-center gap-0.5 text-[14px]" aria-hidden="true">
        <span
          v-for="(emoji, index) in emojis"
          :key="index"
          :style="emojis.length > 1 ? { marginLeft: index === 0 ? '0' : '-4px' } : undefined"
        >{{ emoji }}</span>
      </span>
      <span class="truncate text-[14px] font-medium text-[var(--color-text-strong)]">{{ title }}</span>
      <BotStatusDot v-if="state !== 'idle'" :state="state" size="sm" />
      <button
        v-if="showBack"
        type="button"
        class="ml-0.5 flex h-6 w-6 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-text-muted)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
        aria-label="回到首页"
        title="回到首页"
        @click="goBack"
      >
        <ArrowLeft class="h-3.5 w-3.5" />
      </button>
    </div>
  </header>
</template>
