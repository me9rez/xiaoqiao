import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { gatewayService } from '@/services/gateway'
import { useBotsStore } from '@/stores/bots'

vi.mock('@/services/gateway', () => ({
  gatewayService: {
    call: vi.fn(),
  },
}))

const CODER = {
  id: 'bot_1',
  name: 'Coder',
  slug: 'coder',
  emoji: '🧑‍💻',
  persona: '',
  model: '',
  tools: [],
  workspace: '',
  createdAt: '2026-01-01',
  updatedAt: '2026-01-01',
}

const WATCH = { ...CODER, id: 'bot_2', name: '盯盘', slug: 'watch', emoji: '📈' }

describe('useBotsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.mocked(gatewayService.call).mockReset()
  })

  it('loads bots and selects the first one', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce([CODER, WATCH])

    const store = useBotsStore()
    await store.load()

    expect(store.bots).toHaveLength(2)
    expect(store.activeBotId).toBe('bot_1')
    expect(store.activeBot?.name).toBe('Coder')
    expect(localStorage.getItem('xiaoqiao:active-bot')).toBe('bot_1')
  })

  it('keeps a stored selection that still exists', async () => {
    localStorage.setItem('xiaoqiao:active-bot', 'bot_2')
    vi.mocked(gatewayService.call).mockResolvedValueOnce([CODER, WATCH])

    const store = useBotsStore()
    await store.load()

    expect(store.activeBotId).toBe('bot_2')
  })

  it('selects a newly created bot', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce({ ...WATCH, id: 'bot_3', name: '生活助理' })

    const store = useBotsStore()
    const created = await store.create({ name: '生活助理' })

    expect(created?.id).toBe('bot_3')
    expect(store.activeBotId).toBe('bot_3')
    expect(store.bots).toHaveLength(1)
  })

  it('falls back to the next bot after deletion', async () => {
    vi.mocked(gatewayService.call)
      .mockResolvedValueOnce([CODER, WATCH])
      .mockResolvedValueOnce({ ok: true })

    const store = useBotsStore()
    await store.load()
    store.selectBot('bot_1')

    const removed = await store.remove('bot_1')

    expect(removed).toBe(true)
    expect(store.activeBotId).toBe('bot_2')
    expect(store.bots.map((bot) => bot.id)).toEqual(['bot_2'])
  })

  it('surfaces RPC errors', async () => {
    vi.mocked(gatewayService.call).mockRejectedValueOnce(new Error('boom'))

    const store = useBotsStore()
    await store.load()

    expect(store.error).toBe('boom')
    expect(store.loading).toBe(false)
  })
})
