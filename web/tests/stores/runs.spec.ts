import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { gatewayService } from '@/services/gateway'
import { useRunsStore } from '@/stores/runs'

vi.mock('@/services/gateway', () => ({
  gatewayService: {
    call: vi.fn(),
    on: vi.fn(() => () => {}),
  },
}))

const RUN = {
  id: 'run_1',
  botId: 'bot_1',
  sessionId: null,
  groupId: 'grp_1',
  trigger: 'group',
  status: 'done' as const,
  hop: 0,
  error: null,
  createdAt: '2026-10-18T00:00:00Z',
  startedAt: '2026-10-18T00:00:00Z',
  endedAt: '2026-10-18T00:00:02Z',
}

describe('useRunsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(gatewayService.call).mockReset()
  })

  it('loads runs with filters', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce([RUN])

    const store = useRunsStore()
    await store.load({ botId: 'bot_1', status: 'failed', limit: 10 })

    expect(store.items).toHaveLength(1)
    expect(gatewayService.call).toHaveBeenCalledWith('listRuns', {
      limit: 10,
      botId: 'bot_1',
      status: 'failed',
    })
  })

  it('counts failed and active runs', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce([
      RUN,
      { ...RUN, id: 'run_2', status: 'failed' },
      { ...RUN, id: 'run_3', status: 'running' },
    ])

    const store = useRunsStore()
    await store.load()

    expect(store.failedCount).toBe(1)
    expect(store.runningCount).toBe(1)
  })

  it('surfaces errors', async () => {
    vi.mocked(gatewayService.call).mockRejectedValueOnce(new Error('boom'))

    const store = useRunsStore()
    await store.load()

    expect(store.error).toBe('boom')
    expect(store.loading).toBe(false)
  })
})
