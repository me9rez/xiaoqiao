<script setup lang="ts">
import { Pencil, Plus } from '@lucide/vue'
import { computed } from 'vue'

import BotAvatar from '@/components/bots/BotAvatar.vue'
import { gatewayService } from '@/services/gateway'
import { useBotsStore } from '@/stores/bots'
import { useChatStore } from '@/stores/chat'
import { useSessionsStore } from '@/stores/sessions'
import type { Bot } from '@/types/bot'

const emit = defineEmits<{ edit: [bot: Bot | null] }>()

const botsStore = useBotsStore()
const sessionsStore = useSessionsStore()
const chatStore = useChatStore()

const runningBotIds = computed(() => {
  const ids = new Set<string>()
  for (const session of sessionsStore.sessions) {
    const state = chatStore.sessions.get(session.id)?.runState
    if (session.botId && (state === 'running' || state === 'waiting_approval')) {
      ids.add(session.botId)
    }
  }
  return ids
})

function handleSelect(botId: string) {
  if (botsStore.activeBotId === botId) return
  botsStore.selectBot(botId)
  sessionsStore.clearCurrentSession()
}

async function handleAdd() {
  if (!gatewayService.isConnected()) return
  emit('edit', null)
}
</script>

<template>
  <aside
    class="w-[var(--p-rail-w)] flex-shrink-0 flex flex-col items-center gap-2 py-3 border-r border-[var(--color-line)] bg-[var(--color-sidebar-bg)]"
    aria-label="Bot 列表"
  >
    <div
      v-if="botsStore.loading"
      class="w-10 h-10 rounded-[var(--radius-lg)] bg-[var(--color-surface)] animate-pulse"
    />

    <button
      v-for="bot in botsStore.bots"
      :key="bot.id"
      type="button"
      class="group relative w-10 h-10 rounded-[var(--radius-lg)] flex items-center justify-center transition-colors duration-[var(--duration-base)] focus-visible:outline-none focus-visible:shadow-[var(--p-focus-ring-strong)]"
      :class="
        botsStore.activeBotId === bot.id
          ? 'bg-[var(--color-selected)] shadow-[inset_0_0_0_0.5px_var(--color-line-strong)]'
          : 'hover:bg-[var(--color-hover)]'
      "
      :aria-pressed="botsStore.activeBotId === bot.id"
      :aria-label="`切换到 ${bot.name}`"
      :title="bot.name"
      @click="handleSelect(bot.id)"
      @dblclick="emit('edit', bot)"
    >
      <BotAvatar :bot="bot" />
      <span
        v-if="runningBotIds.has(bot.id)"
        class="absolute -right-0.5 -bottom-0.5 w-2.5 h-2.5 rounded-full bg-[var(--color-accent)] ring-2 ring-[var(--color-sidebar-bg)]"
        aria-label="运行中"
      />
      <span
        class="absolute -right-1 -top-1 hidden group-hover:flex items-center justify-center w-5 h-5 rounded-full bg-[var(--color-surface-raised)] border border-[var(--color-line)] text-[var(--color-text-muted)]"
        aria-hidden="true"
      >
        <Pencil class="w-3 h-3" />
      </span>
    </button>

    <button
      type="button"
      class="w-10 h-10 rounded-[var(--radius-lg)] flex items-center justify-center text-[var(--color-text-muted)] hover:bg-[var(--color-hover)] hover:text-[var(--color-text)] transition-colors duration-[var(--duration-base)] focus-visible:outline-none focus-visible:shadow-[var(--p-focus-ring)]"
      aria-label="新建 Bot"
      title="新建 Bot"
      @click="handleAdd"
    >
      <Plus class="w-5 h-5" />
    </button>

    <p
      v-if="botsStore.error"
      class="px-1 text-[10px] leading-tight text-[var(--color-danger)] text-center break-words"
      role="alert"
    >
      {{ botsStore.error }}
    </p>
  </aside>
</template>
