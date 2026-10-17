import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { gatewayService } from '@/services/gateway'
import { useArtifactsStore } from '@/stores/artifacts'
import type { GatewayEvent } from '@/types/gateway'

const listeners = new Map<string, ((event: GatewayEvent) => void)[]>()

vi.mock('@/services/gateway', () => ({
  gatewayService: {
    call: vi.fn(),
    on: vi.fn((name: string, callback: (event: GatewayEvent) => void) => {
      const list = listeners.get(name) ?? []
      list.push(callback)
      listeners.set(name, list)
      return () => undefined
    }),
  },
}))

const ARTIFACT = {
  id: 'art_1',
  botId: 'bot_1',
  runId: 'run_1',
  path: 'reports/daily.md',
  mime: 'text/markdown',
  size: 120,
  createdAt: '2026-10-18T00:00:00Z',
}

describe('useArtifactsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    listeners.clear()
    vi.mocked(gatewayService.call).mockReset()
  })

  it('loads artifacts for a bot', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce([ARTIFACT])

    const store = useArtifactsStore()
    await store.load('bot_1')

    expect(store.items).toHaveLength(1)
  })

  it('prepends new artifacts from events without duplicates', () => {
    const store = useArtifactsStore()
    store.listen()

    const handler = (listeners.get('artifact_created') ?? [])[0]
    handler?.({ type: 'artifact_created', artifactId: 'art_1', botId: 'bot_1', groupId: null, artifact: ARTIFACT })
    handler?.({ type: 'artifact_created', artifactId: 'art_1', botId: 'bot_1', groupId: null, artifact: ARTIFACT })

    expect(store.items).toHaveLength(1)
    expect(store.items[0]?.path).toBe('reports/daily.md')
  })
})
