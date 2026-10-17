import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { gatewayService } from '@/services/gateway'
import { useMemoryStore } from '@/stores/memory'

vi.mock('@/services/gateway', () => ({
  gatewayService: {
    call: vi.fn(),
  },
}))

const FACT = {
  id: 'fact_1',
  botId: 'bot_1',
  key: '称呼',
  value: '叫我老王',
  source: 'user',
  confidence: 1,
  updatedAt: '2026-10-18T00:00:00Z',
}

const NOTE = {
  id: 'note_1',
  botId: 'bot_1',
  sessionId: null,
  text: '周六交周报',
  createdAt: '2026-10-18T00:00:00Z',
}

describe('useMemoryStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(gatewayService.call).mockReset()
  })

  it('loads facts and notes', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce({ facts: [FACT], notes: [NOTE] })

    const store = useMemoryStore()
    await store.load('bot_1')

    expect(store.facts).toHaveLength(1)
    expect(store.notes).toHaveLength(1)
  })

  it('upserts a fact in place or at the front', async () => {
    vi.mocked(gatewayService.call)
      .mockResolvedValueOnce({ ...FACT, value: '叫他王工' })
      .mockResolvedValueOnce({ ...FACT, id: 'fact_2', key: '时区', value: 'Asia/Shanghai' })

    const store = useMemoryStore()
    store.facts = [FACT]
    await store.upsert('bot_1', '称呼', '叫他王工')
    await store.upsert('bot_1', '时区', 'Asia/Shanghai')

    expect(store.facts.map((fact) => fact.key)).toEqual(['时区', '称呼'])
    expect(store.facts[1]?.value).toBe('叫他王工')
  })

  it('removes a fact', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce({ ok: true })

    const store = useMemoryStore()
    store.facts = [FACT]

    expect(await store.remove('bot_1', '称呼')).toBe(true)
    expect(store.facts).toHaveLength(0)
  })

  it('adds a note at the front', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(NOTE)

    const store = useMemoryStore()
    await store.addNote('bot_1', '周六交周报')

    expect(store.notes[0]?.text).toBe('周六交周报')
  })

  it('searches notes and clears results for an empty query', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce([NOTE])

    const store = useMemoryStore()
    await store.search('bot_1', '周报')
    expect(store.results).toHaveLength(1)

    await store.search('bot_1', '  ')
    expect(store.results).toHaveLength(0)
  })
})
