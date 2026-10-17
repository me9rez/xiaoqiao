import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { gatewayService } from '@/services/gateway'
import { useGroupsStore } from '@/stores/groups'

vi.mock('@/services/gateway', () => ({
  gatewayService: {
    call: vi.fn(),
    sendGroupMessage: vi.fn(),
    on: vi.fn(() => () => {}),
  },
}))

const GROUP = {
  id: 'grp_1',
  name: 'Daily',
  defaultBotId: 'bot_1',
  botIds: ['bot_1', 'bot_2'],
  settings: { maxHops: 3 },
  archived: false,
  createdAt: '2026-01-01',
  updatedAt: '2026-01-01',
}

const MESSAGE = {
  id: 'msg_1',
  groupId: 'grp_1',
  seq: 1,
  authorType: 'user' as const,
  authorId: 'owner',
  text: '@watch 查行情',
  mentions: ['bot_2'],
  replyTo: null,
  runId: null,
  createdAt: '2026-01-01T00:00:00Z',
}

describe('useGroupsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(gatewayService.call).mockReset()
    vi.mocked(gatewayService.sendGroupMessage).mockReset()
  })

  it('loads groups', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce([GROUP])

    const store = useGroupsStore()
    await store.load()

    expect(store.groups).toHaveLength(1)
    expect(store.activeGroup).toBeNull()
  })

  it('creates and selects a group', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce(GROUP)

    const store = useGroupsStore()
    const created = await store.create({ name: 'Daily', botIds: ['bot_1', 'bot_2'] })

    expect(created?.id).toBe('grp_1')
    expect(store.activeGroupId).toBe('grp_1')
  })

  it('sends a group message once', () => {
    const store = useGroupsStore()
    store.sendMessage('grp_1', '  @watch 查行情  ')

    expect(gatewayService.sendGroupMessage).toHaveBeenCalledWith('grp_1', '@watch 查行情')
    expect(store.sending).toBe(true)
  })

  it('deduplicates incoming messages and clears sending', () => {
    const store = useGroupsStore()
    store.sendMessage('grp_1', 'hi')

    store.receive({ ...MESSAGE, id: 'msg_1' })
    store.receive({ ...MESSAGE, id: 'msg_1' })
    store.receive({ ...MESSAGE, id: 'msg_2', seq: 2, authorType: 'bot', text: '收到' })

    expect(store.messagesFor('grp_1').map((message) => message.id)).toEqual(['msg_1', 'msg_2'])
    expect(store.sending).toBe(false)
  })

  it('deletes a group and clears its messages', async () => {
    vi.mocked(gatewayService.call).mockResolvedValueOnce({ ok: true })

    const store = useGroupsStore()
    store.groups = [GROUP]
    store.selectGroup('grp_1')
    store.receive(MESSAGE)

    expect(await store.remove('grp_1')).toBe(true)
    expect(store.groups).toHaveLength(0)
    expect(store.activeGroupId).toBeNull()
  })
})
