import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { gatewayService } from '@/services/gateway'
import { useRoutinesStore } from '@/stores/routines'

vi.mock('@/services/gateway', () => ({
  gatewayService: {
    call: vi.fn(),
    on: vi.fn(() => () => {}),
  },
}))

const ROUTINE = {
  id: 'rt_1',
  botId: 'bot_1',
  name: '日报',
  schedule: { kind: 'daily' as const, at: '09:00', tz: 'Asia/Shanghai' },
  prompt: '写日报',
  targetGroupId: 'grp_1',
  targetChannelId: null,
  enabled: true,
  nextRunAt: '2026-10-19T01:00:00+00:00',
  lastRunAt: null,
  createdAt: '2026-10-18T00:00:00+00:00',
}

describe('useRoutinesStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(gatewayService.call).mockReset()
  })

  it('loads routines and counts enabled ones', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce([ROUTINE, { ...ROUTINE, id: 'rt_2', enabled: false }])

    const store = useRoutinesStore()
    await store.load()

    expect(store.routines).toHaveLength(2)
    expect(store.enabledCount).toBe(1)
  })

  it('creates a routine', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(ROUTINE)

    const store = useRoutinesStore()
    const created = await store.create({
      botId: 'bot_1',
      name: '日报',
      schedule: { kind: 'daily', at: '09:00', tz: 'Asia/Shanghai' },
      prompt: '写日报',
    })

    expect(created?.id).toBe('rt_1')
    expect(store.routines).toHaveLength(1)
  })

  it('toggles a routine', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce({ ...ROUTINE, enabled: false })

    const store = useRoutinesStore()
    store.routines = [ROUTINE]
    await store.toggle('rt_1', false)

    expect(store.routines[0]?.enabled).toBe(false)
  })

  it('removes a routine', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce({ ok: true })

    const store = useRoutinesStore()
    store.routines = [ROUTINE]

    expect(await store.remove('rt_1')).toBe(true)
    expect(store.routines).toHaveLength(0)
  })

  it('surfaces errors', async () => {
    vi.mocked(gatewayService.call).mockRejectedValueOnce(new Error('boom'))

    const store = useRoutinesStore()
    await store.load()

    expect(store.error).toBe('boom')
    expect(store.loading).toBe(false)
  })
})
