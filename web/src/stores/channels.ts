import { defineStore } from 'pinia'
import { ref } from 'vue'

import { gatewayService } from '@/services/gateway'
import type { Channel, ChannelDraft } from '@/types/channel'

export const useChannelsStore = defineStore('channels', () => {
  const items = ref<Channel[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(botId?: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      items.value = await gatewayService.call<Channel[]>('listChannels', botId ? { botId } : {})
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  async function create(draft: ChannelDraft): Promise<Channel | null> {
    error.value = null
    try {
      const channel = await gatewayService.call<Channel>('createChannel', { ...draft })
      items.value = [...items.value, channel]
      return channel
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  async function update(
    channelId: string,
    patch: { config?: Record<string, unknown>; enabled?: boolean },
  ): Promise<Channel | null> {
    error.value = null
    try {
      const channel = await gatewayService.call<Channel>('updateChannel', { channelId, ...patch })
      items.value = items.value.map((item) => (item.id === channel.id ? channel : item))
      return channel
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  async function toggle(channelId: string, enabled: boolean): Promise<boolean> {
    return (await update(channelId, { enabled })) !== null
  }

  async function remove(channelId: string): Promise<boolean> {
    error.value = null
    try {
      const result = await gatewayService.call<{ ok: boolean }>('deleteChannel', { channelId })
      if (result.ok) items.value = items.value.filter((item) => item.id !== channelId)
      return result.ok
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return false
    }
  }

  return { items, loading, error, load, create, update, toggle, remove }
})
