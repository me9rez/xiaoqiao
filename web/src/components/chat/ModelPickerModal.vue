<script setup lang="ts">
import { Check, Search, Star, X } from '@lucide/vue'
import { computed, nextTick, ref, watch } from 'vue'
import type { ModelChoice } from '@/utils/models'
import { loadFavorites, toggleFavorite } from '@/utils/models'

const props = defineProps<{
  open: boolean
  models: ModelChoice[]
  current: string
}>()

const emit = defineEmits<{
  select: [alias: string]
  close: []
}>()

const query = ref('')
const provider = ref<string>('all')
const activeIndex = ref(0)
const favorites = ref<string[]>(loadFavorites())
const searchRef = ref<HTMLInputElement | null>(null)
const listRef = ref<HTMLDivElement | null>(null)

const providers = computed(() => {
  const seen: string[] = []
  for (const model of props.models) {
    if (!seen.includes(model.provider)) seen.push(model.provider)
  }
  return seen
})

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return props.models.filter((model) => {
    if (provider.value !== 'all' && model.provider !== provider.value) return false
    if (!q) return true
    return [model.name, model.modelId, model.alias, model.provider, ...model.capabilities].some((value) =>
      value.toLowerCase().includes(q),
    )
  })
})

watch(filtered, () => {
  activeIndex.value = 0
})

watch(
  () => props.open,
  (open) => {
    if (!open) return
    query.value = ''
    provider.value = 'all'
    const index = props.models.findIndex((model) => model.alias === props.current)
    activeIndex.value = index > 0 ? index : 0
    nextTick(() => {
      searchRef.value?.focus()
      scrollActiveIntoView()
    })
  },
)

function scrollActiveIntoView() {
  const row = listRef.value?.querySelector<HTMLElement>(`[data-index="${activeIndex.value}"]`)
  row?.scrollIntoView({ block: 'nearest' })
}

function move(delta: number) {
  const total = filtered.value.length
  if (total === 0) return
  activeIndex.value = (activeIndex.value + delta + total) % total
  nextTick(scrollActiveIntoView)
}

function choose(model?: ModelChoice) {
  const target = model ?? filtered.value[activeIndex.value]
  if (!target) return
  emit('select', target.alias)
  emit('close')
}

function star(alias: string) {
  favorites.value = toggleFavorite(alias)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    move(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    move(-1)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    choose()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-6 pt-[10vh]"
      @click.self="emit('close')"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="切换模型"
        class="flex w-full max-w-2xl flex-col overflow-hidden rounded-[var(--radius-xl)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-overlay)] shadow-[var(--shadow-menu)]"
      >
        <header class="flex items-center justify-between px-5 pt-4">
          <h2 class="text-[16px] font-medium text-[var(--color-text-strong)]">
            切换模型
          </h2>
          <button
            type="button"
            class="flex h-8 w-8 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-text-muted)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
            aria-label="关闭"
            @click="emit('close')"
          >
            <X class="h-4 w-4" />
          </button>
        </header>

        <div class="px-5 pt-3">
          <div class="relative">
            <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-faint)]" />
            <input
              ref="searchRef"
              v-model="query"
              type="text"
              placeholder="搜索模型或提供商…"
              spellcheck="false"
              class="h-10 w-full rounded-[var(--radius-md)] border-[0.5px] border-[var(--color-accent)] bg-[var(--color-surface-overlay)] pl-9 pr-3 text-[14px] text-[var(--color-text)] shadow-[var(--p-focus-ring)] outline-none placeholder:text-[var(--color-text-faint)]"
              @keydown="onKeydown"
            >
          </div>

          <div class="mt-3 flex flex-wrap gap-1.5">
            <button
              type="button"
              class="h-7 rounded-[var(--radius-full)] px-3 text-[12px] transition"
              :class="provider === 'all'
                ? 'bg-[var(--color-send-bg)] text-[var(--color-send-icon)]'
                : 'bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-hover)]'"
              @click="provider = 'all'"
            >
              全部
            </button>
            <button
              v-for="id in providers"
              :key="id"
              type="button"
              class="h-7 rounded-[var(--radius-full)] px-3 text-[12px] transition"
              :class="provider === id
                ? 'bg-[var(--color-send-bg)] text-[var(--color-send-icon)]'
                : 'bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-hover)]'"
              @click="provider = id"
            >
              {{ id }}
            </button>
          </div>
        </div>

        <div ref="listRef" role="listbox" class="mt-3 max-h-[48vh] overflow-y-auto px-2 pb-2">
          <button
            v-for="(model, index) in filtered"
            :key="model.alias"
            type="button"
            role="option"
            :aria-selected="model.alias === current"
            :data-index="index"
            class="flex w-full items-start gap-2 rounded-[var(--radius-md)] px-3 py-2.5 text-left transition"
            :class="model.alias === current ? 'bg-[var(--color-selected)]' : index === activeIndex ? 'bg-[var(--color-hover)]' : ''"
            @mouseenter="activeIndex = index"
            @click="choose(model)"
          >
            <span class="min-w-0 flex-1">
              <span class="block truncate text-[15px] leading-6 text-[var(--color-text-strong)]">{{ model.name }}</span>
              <span class="mt-0.5 block truncate text-[12px] leading-4 text-[var(--color-text-faint)]">{{ model.subtitle }}</span>
            </span>
            <span
              class="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-[var(--radius-sm)] transition"
              :class="favorites.includes(model.alias) ? 'text-[var(--color-warning)]' : 'text-[var(--color-text-quaternary)] hover:text-[var(--color-text-muted)]'"
              :title="favorites.includes(model.alias) ? '取消收藏' : '收藏'"
              @click.stop="star(model.alias)"
            >
              <Star class="h-4 w-4" :class="favorites.includes(model.alias) ? 'fill-current' : ''" />
            </span>
            <Check v-if="model.alias === current" class="mt-1 h-4 w-4 flex-shrink-0 text-[var(--color-accent)]" />
            <span v-else class="mt-1 h-4 w-4 flex-shrink-0" />
          </button>

          <p v-if="filtered.length === 0" class="px-3 py-8 text-center text-[13px] text-[var(--color-text-faint)]">
            没有匹配的模型
          </p>
        </div>

        <footer class="flex items-center gap-3 border-t-[0.5px] border-[var(--color-line)] px-5 py-2.5 text-[12px] text-[var(--color-text-faint)]">
          <span class="flex items-center gap-1">
            <kbd class="rounded-[var(--radius-xs)] border-[0.5px] border-[var(--color-line-strong)] px-1.5 py-0.5 font-mono text-[11px]">↑</kbd>
            <kbd class="rounded-[var(--radius-xs)] border-[0.5px] border-[var(--color-line-strong)] px-1.5 py-0.5 font-mono text-[11px]">↓</kbd>
            导航
          </span>
          <span class="flex items-center gap-1">
            <kbd class="rounded-[var(--radius-xs)] border-[0.5px] border-[var(--color-line-strong)] px-1.5 py-0.5 font-mono text-[11px]">Enter</kbd>
            选择
          </span>
          <span class="flex items-center gap-1">
            <kbd class="rounded-[var(--radius-xs)] border-[0.5px] border-[var(--color-line-strong)] px-1.5 py-0.5 font-mono text-[11px]">Esc</kbd>
            关闭
          </span>
        </footer>
      </div>
    </div>
  </Teleport>
</template>
