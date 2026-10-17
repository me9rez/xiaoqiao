import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { gatewayService } from '@/services/gateway'
import type { RunFilters, RunRecord } from '@/types/run'
import { isDoneEvent } from '@/types/gateway'

export const useRunsStore = defineStore('runs', () => {
  const items = ref<RunRecord[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let unsubscribe: (() => void) | null = null
  let refreshTimer: ReturnType<typeof setTimeout> | null = null

  const failedCount = computed(() => items.value.filter((run) => run.status === 'failed').length)
  const runningCount = computed(() =>
    items.value.filter((run) => run.status === 'running' || run.status === 'waiting_approval').length,
  )

  async function load(filters: RunFilters = {}): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const params: Record<string, unknown> = { limit: filters.limit ?? 50 }
      if (filters.botId) params.botId = filters.botId
      if (filters.groupId) params.groupId = filters.groupId
      if (filters.status) params.status = filters.status
      items.value = await gatewayService.call<RunRecord[]>('listRuns', params)
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  function scheduleRefresh(): void {
    if (refreshTimer) return
    refreshTimer = setTimeout(() => {
      refreshTimer = null
      void load()
    }, 800)
  }

  function listen(): () => void {
    if (unsubscribe) return unsubscribe
    unsubscribe = gatewayService.on('done', (event) => {
      if (isDoneEvent(event)) scheduleRefresh()
    })
    return unsubscribe
  }

  return { items, loading, error, failedCount, runningCount, load, listen }
})
