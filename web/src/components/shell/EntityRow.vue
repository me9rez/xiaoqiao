<script setup lang="ts">
import { computed } from 'vue'
import BotStatusDot from '@/components/bots/BotStatusDot.vue'
import type { BotActivityState } from '@/types/activity'

/**
 * One row in the sidebar list — groups and bots share it so the list reads as a
 * single "team" column instead of separate sections.
 */
const props = withDefaults(
  defineProps<{
    name: string
    subtitle: string
    /** Single emoji for a bot. */
    emoji?: string
    /** Emoji stack for a group. */
    memberEmojis?: string[]
    /** Unread / waiting count; hidden when 0. */
    count?: number
    state?: BotActivityState
    active?: boolean
  }>(),
  { emoji: '', memberEmojis: () => [], count: 0, state: 'idle', active: false },
)

const emit = defineEmits<{
  select: []
  edit: []
}>()

const stack = computed(() => props.memberEmojis.slice(0, 3))
const overflow = computed(() => Math.max(0, props.memberEmojis.length - stack.value.length))
</script>

<template>
  <button
    type="button"
    class="group flex w-full items-center gap-2.5 rounded-[var(--radius-md)] px-2 py-1.5 text-left transition-colors duration-[var(--duration-base)] focus-visible:outline-none focus-visible:shadow-[var(--p-focus-ring)]"
    :class="active ? 'bg-[var(--color-selected)]' : 'hover:bg-[var(--color-hover)]'"
    :aria-current="active ? 'true' : undefined"
    @click="emit('select')"
    @dblclick="emit('edit')"
  >
    <span
      v-if="emoji"
      class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-surface)] text-[16px] select-none"
      aria-hidden="true"
    >
      {{ emoji }}
    </span>
    <span
      v-else
      class="relative flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-surface)]"
      aria-hidden="true"
    >
      <span
        v-for="(item, index) in stack"
        :key="index"
        class="absolute text-[13px]"
        :style="{ transform: `translate(${(index - (stack.length - 1) / 2) * 9}px, ${index % 2 === 0 ? 1 : -1}px)` }"
      >
        {{ item }}
      </span>
      <span v-if="overflow" class="absolute -bottom-1 -right-1 rounded-full bg-[var(--color-surface-raised)] px-1 text-[9px] text-[var(--color-text-faint)]">
        +{{ overflow }}
      </span>
    </span>

    <span class="min-w-0 flex-1">
      <span class="flex items-center gap-1.5">
        <span class="truncate text-[14px] leading-5 text-[var(--color-text)]">{{ name }}</span>
        <BotStatusDot v-if="state !== 'idle'" :state="state" size="sm" />
      </span>
      <span class="mt-0.5 block truncate text-[12px] leading-4 text-[var(--color-text-faint)]">
        {{ subtitle || '还没有介绍' }}
      </span>
    </span>

    <span
      v-if="count > 0"
      class="flex h-5 min-w-5 flex-shrink-0 items-center justify-center rounded-[var(--radius-full)] border-[0.5px] border-[var(--color-warning-bd)] bg-[var(--color-warning-soft)] px-1.5 text-[11px] leading-none text-[var(--color-warning)]"
    >
      {{ count }}
    </span>
  </button>
</template>
