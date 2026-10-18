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
const activeDays = ref(7)

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

/** Series colours come from tokens; the legend always names the bot, never just a swatch. */
const SERIES_COLORS = [
  'var(--color-accent)',
  'var(--color-orange)',
  'var(--color-done)',
  'var(--color-success)',
  'var(--color-warning)',
]

function botName(id: string): string {
  return botsStore.bots.find((bot) => bot.id === id)?.name ?? id
}

function botEmoji(id: string): string {
  return botsStore.bots.find((bot) => bot.id === id)?.emoji || '🤖'
}

function botRole(id: string): string {
  return botsStore.bots.find((bot) => bot.id === id)?.role || ''
}

/** Day buckets for the stacked chart: one column per day, one segment per bot. */
const chart = computed(() => {
  const rows = usageStore.summary?.byDay ?? []
  const order: string[] = []
  const series: string[] = []
  const map = new Map<string, Map<string, number>>()
  for (const row of rows) {
    if (!map.has(row.date)) {
      map.set(row.date, new Map())
      order.push(row.date)
    }
    if (!series.includes(row.botId)) series.push(row.botId)
    const day = map.get(row.date)
    if (day) day.set(row.botId, (day.get(row.botId) ?? 0) + row.tokens)
  }
  const seriesIndex = new Map(series.map((id, index) => [id, index]))
  const days = order.map((date) => ({
    date,
    label: date.slice(5),
    segments: series
      .map((id) => ({ botId: id, tokens: map.get(date)?.get(id) ?? 0, color: SERIES_COLORS[(seriesIndex.get(id) ?? 0) % SERIES_COLORS.length] ?? SERIES_COLORS[0] }))
      .filter((segment) => segment.tokens > 0),
  }))
  const peak = Math.max(1, ...days.map((day) => day.segments.reduce((sum, seg) => sum + seg.tokens, 0)))
  return { series, days, peak }
})

const maxBotTokens = computed(() =>
  Math.max(1, ...(usageStore.summary?.byBot ?? []).map((row) => row.tokens)),
)

const maxModelTokens = computed(() =>
  Math.max(1, ...(usageStore.summary?.byModel ?? []).map((row) => row.tokens)),
)

const totalTokens = computed(() => Math.max(1, totals.value?.totalTokens ?? 0))

function compact(value: number | undefined): string {
  if (!value) return '0'
  if (value < 1000) return String(value)
  if (value < 1_000_000) return `${(value / 1000).toFixed(1)}K`
  return `${(value / 1_000_000).toFixed(1)}M`
}

function share(tokens: number, total: number): string {
  return `${Math.round((tokens / Math.max(1, total)) * 100)}%`
}

async function reload() {
  await usageStore.load(activeDays.value)
}

watch(activeDays, () => void reload())

onMounted(async () => {
  if (botsStore.bots.length === 0) await botsStore.load()
  await reload()
})
</script>

<template>
  <div class="mx-auto max-w-3xl p-8">
    <div class="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-[20px] font-semibold leading-7 text-[var(--color-text-strong)]">用量</h1>
        <p class="mt-1 text-[13px] text-[var(--color-text-muted)]">
          全部 Bot 的 token 与花费。超预算会在下一次请求前拦截。
        </p>
      </div>
      <div class="flex items-center gap-1 rounded-[var(--radius-md)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-sunken)] p-0.5">
        <button
          v-for="range in ranges"
          :key="range.days"
          type="button"
          class="rounded-[var(--radius-sm)] px-3 py-1 text-[13px] transition-colors duration-[var(--duration-fast)]"
          :class="activeDays === range.days
            ? 'bg-[var(--color-surface-raised)] text-[var(--color-text)] shadow-[var(--shadow-sm)]'
            : 'text-[var(--color-text-muted)]'"
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
      <!-- KPI -->
      <section class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div class="rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
          <p class="text-[12px] text-[var(--color-text-muted)]">
            最近 {{ activeDays }} 天
          </p>
          <p class="mt-1 text-[22px] font-semibold leading-7 text-[var(--color-text-strong)]">
            {{ compact(totals?.totalTokens) }}
          </p>
          <p class="text-[12px] text-[var(--color-text-faint)]">
            Token
          </p>
        </div>
        <div class="rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
          <p class="text-[12px] text-[var(--color-text-muted)]">
            输出
          </p>
          <p class="mt-1 text-[22px] font-semibold leading-7 text-[var(--color-text-strong)]">
            {{ compact(totals?.outputTokens) }}
          </p>
          <p class="text-[12px] text-[var(--color-text-faint)]">
            Token
          </p>
        </div>
        <div class="rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
          <p class="text-[12px] text-[var(--color-text-muted)]">
            调用次数
          </p>
          <p class="mt-1 text-[22px] font-semibold leading-7 text-[var(--color-text-strong)]">
            {{ totals?.runs ?? 0 }}
          </p>
          <p class="text-[12px] text-[var(--color-text-faint)]">
            次
          </p>
        </div>
        <div class="rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
          <p class="text-[12px] text-[var(--color-text-muted)]">
            花费
          </p>
          <p class="mt-1 text-[22px] font-semibold leading-7 text-[var(--color-text-strong)]">
            ${{ (totals?.costUsd ?? 0).toFixed(2) }}
          </p>
          <p class="text-[12px] text-[var(--color-text-faint)]">
            USD
          </p>
        </div>
      </section>

      <!-- Token 走势 -->
      <section class="mb-4 rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-[14px] font-medium text-[var(--color-text-strong)]">
            Token 走势
            <span class="ml-1 font-normal text-[var(--color-text-faint)]">按天</span>
          </h2>
          <span class="text-[12px] text-[var(--color-text-faint)]">峰值 {{ compact(chart.peak) }}</span>
        </div>

        <div v-if="chart.days.length === 0" class="py-10 text-center text-[13px] text-[var(--color-text-muted)]">
          这段时间还没有用量。
        </div>
        <template v-else>
          <div class="flex h-40 items-end gap-1.5">
            <div
              v-for="day in chart.days"
              :key="day.date"
              class="flex h-full flex-1 flex-col justify-end gap-px"
              :title="`${day.date}：${compact(day.segments.reduce((sum, seg) => sum + seg.tokens, 0))} token`"
            >
              <div
                v-for="segment in day.segments"
                :key="segment.botId"
                class="w-full rounded-[2px]"
                :style="{ height: `${Math.max(2, (segment.tokens / chart.peak) * 100)}%`, background: segment.color }"
              />
            </div>
          </div>
          <div class="mt-1.5 flex gap-1.5">
            <span
              v-for="day in chart.days"
              :key="`label-${day.date}`"
              class="flex-1 truncate text-center text-[10px] text-[var(--color-text-faint)]"
            >{{ day.label }}</span>
          </div>
          <div class="mt-2 flex flex-wrap gap-3">
            <span
              v-for="(botId, index) in chart.series"
              :key="botId"
              class="flex items-center gap-1.5 text-[12px] text-[var(--color-text-muted)]"
            >
              <span
                class="h-2 w-2 rounded-[2px]"
                :style="{ background: SERIES_COLORS[index % SERIES_COLORS.length] }"
                aria-hidden="true"
              />
              {{ botName(botId) }}
            </span>
          </div>
        </template>
      </section>

      <!-- Bot 榜 -->
      <section class="mb-4 rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
        <h2 class="mb-3 text-[14px] font-medium text-[var(--color-text-strong)]">
          Bot
          <span class="ml-1 font-normal text-[var(--color-text-faint)]">{{ usageStore.summary?.byBot.length ?? 0 }}</span>
        </h2>
        <div v-if="(usageStore.summary?.byBot ?? []).length === 0" class="text-[13px] text-[var(--color-text-muted)]">
          这段时间还没有用量。
        </div>
        <div v-else class="space-y-3">
          <div v-for="row in usageStore.summary?.byBot ?? []" :key="row.botId">
            <div class="mb-1 flex items-center gap-2 text-[13px]">
              <span aria-hidden="true">{{ botEmoji(row.botId) }}</span>
              <span class="truncate text-[var(--color-text)]">{{ botName(row.botId) }}</span>
              <span v-if="botRole(row.botId)" class="text-[11px] text-[var(--color-text-faint)]">{{ botRole(row.botId) }}</span>
              <span class="ml-auto text-[var(--color-text-muted)]">{{ compact(row.tokens) }}</span>
              <span class="w-9 text-right text-[11px] text-[var(--color-text-faint)]">{{ share(row.tokens, totalTokens) }}</span>
            </div>
            <div class="h-1.5 overflow-hidden rounded-full bg-[var(--color-surface-sunken)]">
              <div
                class="h-full rounded-full bg-[var(--color-accent)]"
                :style="{ width: `${Math.round((row.tokens / maxBotTokens) * 100)}%` }"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- 模型榜 -->
      <section class="mb-4 rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
        <h2 class="mb-3 text-[14px] font-medium text-[var(--color-text-strong)]">
          模型
          <span class="ml-1 font-normal text-[var(--color-text-faint)]">{{ usageStore.summary?.byModel.length ?? 0 }}</span>
        </h2>
        <div v-if="(usageStore.summary?.byModel ?? []).length === 0" class="text-[13px] text-[var(--color-text-muted)]">
          这段时间还没有用量。
        </div>
        <div v-else class="space-y-3">
          <div v-for="row in usageStore.summary?.byModel ?? []" :key="row.model">
            <div class="mb-1 flex items-center gap-2 text-[13px]">
              <span class="truncate text-[var(--color-text)]">{{ row.model || '未知模型' }}</span>
              <span class="ml-auto text-[var(--color-text-muted)]">{{ compact(row.tokens) }}</span>
              <span class="w-9 text-right text-[11px] text-[var(--color-text-faint)]">{{ share(row.tokens, totalTokens) }}</span>
            </div>
            <div class="h-1.5 overflow-hidden rounded-full bg-[var(--color-surface-sunken)]">
              <div
                class="h-full rounded-full bg-[var(--color-done)]"
                :style="{ width: `${Math.round((row.tokens / maxModelTokens) * 100)}%` }"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- 今日预算 -->
      <section
        v-if="tokenUsagePercent !== null || usdUsagePercent !== null"
        class="rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]"
      >
        <h2 class="mb-3 text-[14px] font-medium text-[var(--color-text-strong)]">
          今日预算
        </h2>
        <div v-if="tokenUsagePercent !== null" class="mb-3">
          <div class="mb-1 flex items-center justify-between text-[12px] text-[var(--color-text-muted)]">
            <span>token</span>
            <span>{{ compact(today?.totalTokens) }} / {{ compact(budget?.dailyTokens) }}</span>
          </div>
          <div class="h-1.5 overflow-hidden rounded-full bg-[var(--color-surface-sunken)]">
            <div
              class="h-full rounded-full"
              :class="tokenUsagePercent >= 100 ? 'bg-[var(--color-danger)]' : 'bg-[var(--color-accent)]'"
              :style="{ width: `${tokenUsagePercent}%` }"
            />
          </div>
        </div>
        <div v-if="usdUsagePercent !== null">
          <div class="mb-1 flex items-center justify-between text-[12px] text-[var(--color-text-muted)]">
            <span>花费</span>
            <span>${{ (today?.costUsd ?? 0).toFixed(4) }} / ${{ (budget?.dailyUsd ?? 0).toFixed(2) }}</span>
          </div>
          <div class="h-1.5 overflow-hidden rounded-full bg-[var(--color-surface-sunken)]">
            <div
              class="h-full rounded-full"
              :class="usdUsagePercent >= 100 ? 'bg-[var(--color-danger)]' : 'bg-[var(--color-accent)]'"
              :style="{ width: `${usdUsagePercent}%` }"
            />
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
