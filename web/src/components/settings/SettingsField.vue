<script setup lang="ts">
import { CODE_CLASS } from './styles'

/**
 * One labelled field. `tomlKey` is printed next to the label so the page reads
 * as a view of `config.toml` — the same key the user would hand-edit.
 */
withDefaults(
  defineProps<{
    label: string
    tomlKey?: string
    hint?: string
    inputId?: string
  }>(),
  { tomlKey: '', hint: '', inputId: '' },
)
</script>

<template>
  <div class="min-w-0">
    <div class="mb-1.5 flex items-baseline justify-between gap-2">
      <label
        :for="inputId || undefined"
        class="text-[13px] font-medium text-[var(--color-text)]"
      >{{ label }}</label>
      <code v-if="tomlKey" :class="CODE_CLASS">{{ tomlKey }}</code>
    </div>
    <slot />
    <p v-if="hint" class="mt-1 text-[12px] leading-4 text-[var(--color-text-faint)]">
      {{ hint }}
    </p>
  </div>
</template>
