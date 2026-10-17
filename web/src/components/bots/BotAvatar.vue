<script setup lang="ts">
import type { Bot } from '@/types/bot'

withDefaults(
  defineProps<{
    bot: Pick<Bot, 'emoji' | 'name'>
    size?: 'sm' | 'md'
  }>(),
  { size: 'md' },
)
</script>

<template>
  <span
    class="inline-flex items-center justify-center rounded-[var(--radius-lg)] bg-[var(--color-surface)] shrink-0 select-none"
    :class="size === 'sm' ? 'w-6 h-6 text-[13px]' : 'w-10 h-10 text-[20px]'"
    :title="bot.name"
    aria-hidden="true"
  >
    {{ bot.emoji || '🤖' }}
  </span>
</template>
