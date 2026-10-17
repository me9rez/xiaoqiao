import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { gatewayService } from '@/services/gateway'
import { useApprovalsStore } from '@/stores/approvals'
import type { GatewayEvent } from '@/types/gateway'

const listeners = new Map<string, ((event: GatewayEvent) => void)[]>()

vi.mock('@/services/gateway', () => ({
  gatewayService: {
    call: vi.fn(),
    on: vi.fn((name: string, callback: (event: GatewayEvent) => void) => {
      const list = listeners.get(name) ?? []
      list.push(callback)
      listeners.set(name, list)
      return () => {
        listeners.set(name, (listeners.get(name) ?? []).filter((item) => item !== callback))
      }
    }),
  },
}))

const APPROVAL = {
  id: 'ap_1',
  runId: 'run_1',
  callId: 'call_1',
  botId: 'bot_1',
  groupId: null,
  tool: 'run_command',
  arguments: { command: 'ls' },
  status: 'pending' as const,
  createdAt: '2026-01-01T00:00:00Z',
  expiresAt: '2026-01-01T00:30:00Z',
  resolvedAt: null,
  resolvedBy: null,
}

describe('useApprovalsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    listeners.clear()
    vi.mocked(gatewayService.call).mockReset()
    vi.mocked(gatewayService.on).mockClear()
  })

  it('loads approvals and counts pending', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce([APPROVAL])

    const store = useApprovalsStore()
    await store.load()

    expect(store.items).toHaveLength(1)
    expect(store.pendingCount).toBe(1)
  })

  it('resolves and updates local status', async () => {
    vi.mocked(gatewayService.call)
      .mockResolvedValueOnce([APPROVAL])
      .mockResolvedValueOnce({ ok: true, status: 'approved' })

    const store = useApprovalsStore()
    await store.load()
    expect(await store.resolve('ap_1', true)).toBe(true)

    expect(store.items[0]?.status).toBe('approved')
    expect(store.pendingCount).toBe(0)
  })

  it('adds live approvals from events', () => {
    const store = useApprovalsStore()
    store.listen()

    for (const handler of listeners.get('approval_requested') ?? []) {
      handler({
        type: 'approval_requested',
        approvalId: 'ap_2',
        callId: 'call_2',
        botId: 'bot_1',
        groupId: 'grp_1',
        runId: 'run_2',
        tool: 'write_file',
        arguments: '{"path":"a.txt"}',
        expiresAt: '2026-01-01T00:30:00Z',
      })
    }

    expect(store.items[0]?.id).toBe('ap_2')
    expect(store.items[0]?.arguments).toEqual({ path: 'a.txt' })
  })

  it('applies resolutions from events', () => {
    const store = useApprovalsStore()
    store.upsert({ ...APPROVAL })
    store.listen()

    for (const handler of listeners.get('approval_resolved') ?? []) {
      handler({
        type: 'approval_resolved',
        approvalId: 'ap_1',
        callId: 'call_1',
        botId: 'bot_1',
        groupId: null,
        status: 'denied',
      })
    }

    expect(store.items[0]?.status).toBe('denied')
  })
})
