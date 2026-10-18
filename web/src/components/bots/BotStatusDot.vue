<script setup lang="ts">
import { computed } from 'vue'

import type { BotActivityState } from '@/types/activity'

/**
 * Bot status dot.
 *
 * Design rules (`docs/design.md` §9/§10): never rely on colour alone, so every
 * dot carries a full-sentence `title` + `aria-label`, and the status palette is
 * used as a set. Motion is opt-out under `prefers-reduced-motion`.
 */
const props = withDefaults(
  defineProps<{
    state: BotActivityState
    /** Full sentence for screen readers and the tooltip. */
    label?: string
    size?: 'sm' | 'md'
  }>(),
  { label: '', size: 'md' },
)

const FALLBACK: Record<BotActivityState, string> = {
  idle: '',
  working: '正在忙',
  needs_you: '等你审批',
  error: '最近一次运行失败',
}

const text = computed(() => props.label || FALLBACK[props.state])

const dotClass = computed(() => {
  switch (props.state) {
    case 'needs_you':
      return 'bg-[var(--color-warning)] motion-safe:animate-pulse'
    case 'working':
      return 'bg-[var(--color-accent)] motion-safe:animate-pulse'
    case 'error':
      return 'bg-[var(--color-danger)]'
    default:
      return ''
  }
})
</script>

<template>
  <span
    v-if="state !== 'idle'"
    class="pointer-events-none inline-flex items-center justify-center rounded-full ring-2 ring-[var(--color-sidebar-bg)]"
    :class="size === 'sm' ? 'w-2 h-2' : 'w-2.5 h-2.5'"
    role="img"
    :title="text"
    :aria-label="text"
  >
    <span class="w-full h-full rounded-full" :class="dotClass" />
  </span>
</template>
