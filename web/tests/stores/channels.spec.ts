import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { gatewayService } from '@/services/gateway'
import { useChannelsStore } from '@/stores/channels'

vi.mock('@/services/gateway', () => ({
  gatewayService: {
    call: vi.fn(),
  },
}))

const CHANNEL = {
  id: 'ch_1',
  botId: 'bot_1',
  kind: 'telegram',
  config: { token: '***', groupId: 'grp_1', chatId: '42' },
  enabled: true,
  createdAt: '2026-10-18T00:00:00Z',
}

describe('useChannelsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(gatewayService.call).mockReset()
  })

  it('loads channels for a bot', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce([CHANNEL])

    const store = useChannelsStore()
    await store.load('bot_1')

    expect(store.items).toHaveLength(1)
    expect(gatewayService.call).toHaveBeenCalledWith('listChannels', { botId: 'bot_1' })
  })

  it('creates a channel', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(CHANNEL)

    const store = useChannelsStore()
    const created = await store.create({
      botId: 'bot_1',
      kind: 'telegram',
      config: { token: 'T', groupId: 'grp_1' },
    })

    expect(created?.id).toBe('ch_1')
    expect(store.items).toHaveLength(1)
  })

  it('updates config and toggles', async () => {
    vi.mocked(gatewayService.call)
      .mockResolvedValueOnce({ ...CHANNEL, config: { ...CHANNEL.config, chatId: '99' } })
      .mockResolvedValueOnce({ ...CHANNEL, enabled: false })

    const store = useChannelsStore()
    store.items = [CHANNEL]

    await store.update('ch_1', { config: { chatId: '99' } })
    expect(store.items[0]?.config.chatId).toBe('99')

    await store.toggle('ch_1', false)
    expect(store.items[0]?.enabled).toBe(false)
  })

  it('removes a channel', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce({ ok: true })

    const store = useChannelsStore()
    store.items = [CHANNEL]

    expect(await store.remove('ch_1')).toBe(true)
    expect(store.items).toHaveLength(0)
  })

  it('surfaces errors', async () => {
    vi.mocked(gatewayService.call).mockRejectedValueOnce(new Error('boom'))

    const store = useChannelsStore()
    await store.load()

    expect(store.error).toBe('boom')
    expect(store.loading).toBe(false)
  })
})
