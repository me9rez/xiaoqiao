<script setup lang="ts">
import { computed } from 'vue'

import BotAvatar from '@/components/bots/BotAvatar.vue'
import type { Bot } from '@/types/bot'

const props = defineProps<{ bots: Bot[]; query: string }>()
const emit = defineEmits<{ select: [bot: Bot] }>()

const matches = computed(() => {
  const query = props.query.trim().toLowerCase()
  const list = query
    ? props.bots.filter(
        (bot) => bot.slug.toLowerCase().includes(query) || bot.name.toLowerCase().includes(query),
      )
    : props.bots
  return list.slice(0, 6)
})
</script>

<template>
  <div
    v-if="matches.length > 0"
    class="absolute bottom-full left-0 mb-2 w-64 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-menu-bg)] shadow-[var(--shadow-menu)] backdrop-blur-[24px] p-1"
    role="listbox"
    aria-label="选择要 @ 的 Bot"
  >
    <button
      v-for="bot in matches"
      :key="bot.id"
      type="button"
      role="option"
      class="w-full flex items-center gap-2 px-2 py-1.5 rounded-[var(--radius-md)] text-left hover:bg-[var(--color-hover)] focus-visible:bg-[var(--color-selected)] outline-none"
      @click="emit('select', bot)"
    >
      <BotAvatar :bot="bot" size="sm" />
      <span class="flex-1 text-[13px] text-[var(--color-text)]">{{ bot.name }}</span>
      <span class="text-[12px] text-[var(--color-text-faint)]">@{{ bot.slug }}</span>
    </button>
  </div>
  <div
    v-else-if="query.length > 0"
    class="absolute bottom-full left-0 mb-2 w-64 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-menu-bg)] shadow-[var(--shadow-menu)] px-3 py-2 text-[12px] text-[var(--color-text-muted)]"
  >
    没有匹配的 Bot
  </div>
</template>
