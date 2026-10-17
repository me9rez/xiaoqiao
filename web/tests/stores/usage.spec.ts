import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { gatewayService } from '@/services/gateway'
import { useUsageStore } from '@/stores/usage'

vi.mock('@/services/gateway', () => ({
  gatewayService: {
    call: vi.fn(),
  },
}))

const SUMMARY = {
  today: { inputTokens: 10, outputTokens: 5, totalTokens: 15, costUsd: 0.01, runs: 1 },
  window: { inputTokens: 100, outputTokens: 50, totalTokens: 150, costUsd: 0.02, runs: 4 },
  byModel: [{ model: 'deepseek/v4', tokens: 150, costUsd: 0.02, runs: 4 }],
  budget: { dailyTokens: 1000, dailyUsd: 1 },
}

describe('useUsageStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(gatewayService.call).mockReset()
  })

  it('loads a summary for the requested window', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(SUMMARY)

    const store = useUsageStore()
    await store.load(7, 'bot_1')

    expect(store.summary?.window.totalTokens).toBe(150)
    expect(gatewayService.call).toHaveBeenCalledWith('usageSummary', { days: 7, botId: 'bot_1' })
  })

  it('omits the bot filter when none is active', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(SUMMARY)

    const store = useUsageStore()
    await store.load(1)

    expect(gatewayService.call).toHaveBeenCalledWith('usageSummary', { days: 1 })
  })

  it('surfaces errors', async () => {
    vi.mocked(gatewayService.call).mockRejectedValueOnce(new Error('boom'))

    const store = useUsageStore()
    await store.load()

    expect(store.error).toBe('boom')
    expect(store.loading).toBe(false)
  })
})
