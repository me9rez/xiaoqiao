<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { useBotsStore } from '@/stores/bots'
import { useUsageStore } from '@/stores/usage'

const botsStore = useBotsStore()
const usageStore = useUsageStore()

const ranges = [
  { label: '今日', days: 1 },
  { label: '7 天', days: 7 },
  { label: '30 天', days: 30 },
]
const activeDays = ref(1)

const totals = computed(() => usageStore.summary?.window ?? null)
const today = computed(() => usageStore.summary?.today ?? null)
const budget = computed(() => usageStore.summary?.budget ?? null)

const tokenUsagePercent = computed(() => {
  const limit = budget.value?.dailyTokens ?? 0
  const used = today.value?.totalTokens ?? 0
  if (limit <= 0) return null
  return Math.min(100, Math.round((used / limit) * 100))
})

const usdUsagePercent = computed(() => {
  const limit = budget.value?.dailyUsd ?? 0
  const used = today.value?.costUsd ?? 0
  if (limit <= 0) return null
  return Math.min(100, Math.round((used / limit) * 100))
})

const maxModelTokens = computed(() =>
  Math.max(1, ...(usageStore.summary?.byModel ?? []).map((row) => row.tokens)),
)

function compact(value: number | undefined): string {
  if (!value) return '0'
  if (value < 1000) return String(value)
  if (value < 1_000_000) return `${(value / 1000).toFixed(1)}k`
  return `${(value / 1_000_000).toFixed(2)}M`
}

async function reload() {
  await usageStore.load(activeDays.value, botsStore.activeBotId ?? undefined)
}

watch([activeDays, () => botsStore.activeBotId], () => void reload())

onMounted(async () => {
  if (botsStore.bots.length === 0) await botsStore.load()
  await reload()
})
</script>

<template>
  <div class="p-8 max-w-3xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-[20px] font-[var(--weight-semibold)] text-[var(--color-text-strong)]">用量</h1>
        <p class="mt-1 text-[13px] text-[var(--color-text-muted)]">
          当前 Bot：{{ botsStore.activeBot?.name || '全部' }}。用量按 run 记录，超预算会在下一次请求前拦截。
        </p>
      </div>
      <div class="flex items-center gap-1 p-0.5 rounded-[var(--radius-md)] bg-[var(--color-surface-sunken)] border border-[var(--color-line)]">
        <button
          v-for="range in ranges"
          :key="range.days"
          type="button"
          class="px-3 py-1 rounded-[var(--radius-sm)] text-[13px] transition-colors duration-[var(--duration-fast)]"
          :class="
            activeDays === range.days
              ? 'bg-[var(--color-surface-raised)] shadow-[var(--shadow-sm)] text-[var(--color-text)]'
              : 'text-[var(--color-text-muted)]'
          "
          @click="activeDays = range.days"
        >
          {{ range.label }}
        </button>
      </div>
    </div>

    <p v-if="usageStore.error" class="mb-4 text-[13px] text-[var(--color-danger)]" role="alert">
      {{ usageStore.error }}
    </p>

    <div v-if="usageStore.loading && !totals" class="text-[13px] text-[var(--color-text-muted)]">加载中…</div>

    <template v-else>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <div class="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
          <div class="text-[12px] text-[var(--color-text-muted)]">请求次数</div>
          <div class="mt-1 text-[20px] font-[var(--weight-semibold)] text-[var(--color-text-strong)]">
            {{ totals?.runs ?? 0 }}
          </div>
        </div>
        <div class="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
          <div class="text-[12px] text-[var(--color-text-muted)]">输入 token</div>
          <div class="mt-1 text-[20px] font-[var(--weight-semibold)] text-[var(--color-text-strong)]">
            {{ compact(totals?.inputTokens) }}
          </div>
        </div>
        <div class="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
          <div class="text-[12px] text-[var(--color-text-muted)]">输出 token</div>
          <div class="mt-1 text-[20px] font-[var(--weight-semibold)] text-[var(--color-text-strong)]">
            {{ compact(totals?.outputTokens) }}
          </div>
        </div>
        <div class="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
          <div class="text-[12px] text-[var(--color-text-muted)]">花费</div>
          <div class="mt-1 text-[20px] font-[var(--weight-semibold)] text-[var(--color-text-strong)]">
            ${{ (totals?.costUsd ?? 0).toFixed(4) }}
          </div>
        </div>
      </div>

      <section
        v-if="tokenUsagePercent !== null || usdUsagePercent !== null"
        class="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)] mb-4"
      >
        <h2 class="text-[14px] font-[var(--weight-medium)] text-[var(--color-text-strong)] mb-3">今日预算</h2>

        <div v-if="tokenUsagePercent !== null" class="mb-3">
          <div class="flex items-center justify-between text-[12px] text-[var(--color-text-muted)] mb-1">
            <span>token</span>
            <span>{{ compact(today?.totalTokens) }} / {{ compact(budget?.dailyTokens) }}</span>
          </div>
          <div class="h-1.5 rounded-full bg-[var(--color-surface-sunken)] overflow-hidden">
            <div
              class="h-full rounded-full"
              :class="tokenUsagePercent >= 100 ? 'bg-[var(--color-danger)]' : 'bg-[var(--color-accent)]'"
              :style="{ width: `${tokenUsagePercent}%` }"
            />
          </div>
        </div>

        <div v-if="usdUsagePercent !== null">
          <div class="flex items-center justify-between text-[12px] text-[var(--color-text-muted)] mb-1">
            <span>花费</span>
            <span>${{ (today?.costUsd ?? 0).toFixed(4) }} / ${{ (budget?.dailyUsd ?? 0).toFixed(2) }}</span>
          </div>
          <div class="h-1.5 rounded-full bg-[var(--color-surface-sunken)] overflow-hidden">
            <div
              class="h-full rounded-full"
              :class="usdUsagePercent >= 100 ? 'bg-[var(--color-danger)]' : 'bg-[var(--color-accent)]'"
              :style="{ width: `${usdUsagePercent}%` }"
            />
          </div>
        </div>
      </section>

      <section class="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
        <h2 class="text-[14px] font-[var(--weight-medium)] text-[var(--color-text-strong)] mb-3">按模型</h2>
        <div v-if="(usageStore.summary?.byModel ?? []).length === 0" class="text-[13px] text-[var(--color-text-muted)]">
          这段时间还没有用量。
        </div>
        <div v-else class="space-y-2.5">
          <div v-for="row in usageStore.summary?.byModel ?? []" :key="row.model">
            <div class="flex items-center justify-between text-[12px] text-[var(--color-text-muted)] mb-1">
              <span class="truncate">{{ row.model || '未知模型' }}</span>
              <span>{{ compact(row.tokens) }} · {{ row.runs }} 次</span>
            </div>
            <div class="h-1.5 rounded-full bg-[var(--color-surface-sunken)] overflow-hidden">
              <div
                class="h-full rounded-full bg-[var(--color-accent)]"
                :style="{ width: `${Math.round((row.tokens / maxModelTokens) * 100)}%` }"
              />
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
