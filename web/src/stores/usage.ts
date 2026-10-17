import { defineStore } from 'pinia'
import { ref } from 'vue'

import { gatewayService } from '@/services/gateway'
import type { UsageSummary } from '@/types/usage'

export const useUsageStore = defineStore('usage', () => {
  const summary = ref<UsageSummary | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(days = 1, botId?: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const params: Record<string, unknown> = { days }
      if (botId) params.botId = botId
      summary.value = await gatewayService.call<UsageSummary>('usageSummary', params)
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  return { summary, loading, error, load }
})
