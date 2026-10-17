import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { gatewayService } from '@/services/gateway'
import type { Bot, BotDraft } from '@/types/bot'

const ACTIVE_BOT_KEY = 'xiaoqiao:active-bot'

function readActiveBot(): string | null {
  try {
    return localStorage.getItem(ACTIVE_BOT_KEY)
  } catch {
    return null
  }
}

function persistActiveBot(botId: string | null): void {
  try {
    if (botId) {
      localStorage.setItem(ACTIVE_BOT_KEY, botId)
    } else {
      localStorage.removeItem(ACTIVE_BOT_KEY)
    }
  } catch {
    // localStorage may be unavailable; selection still works for this session.
  }
}

export const useBotsStore = defineStore('bots', () => {
  const bots = ref<Bot[]>([])
  const activeBotId = ref<string | null>(readActiveBot())
  const loading = ref(false)
  const error = ref<string | null>(null)

  const activeBot = computed(() => bots.value.find((bot) => bot.id === activeBotId.value) ?? null)

  function selectBot(botId: string | null): void {
    activeBotId.value = botId
    persistActiveBot(botId)
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      bots.value = await gatewayService.call<Bot[]>('listBots')
      const stored = activeBotId.value
      if (!stored || !bots.value.some((bot) => bot.id === stored)) {
        selectBot(bots.value[0]?.id ?? null)
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  async function create(draft: BotDraft): Promise<Bot | null> {
    error.value = null
    try {
      const bot = await gatewayService.call<Bot>('createBot', { ...draft })
      bots.value = [...bots.value, bot]
      selectBot(bot.id)
      return bot
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  async function update(botId: string, patch: Partial<BotDraft>): Promise<Bot | null> {
    error.value = null
    try {
      const bot = await gatewayService.call<Bot>('updateBot', { botId, ...patch })
      bots.value = bots.value.map((item) => (item.id === bot.id ? bot : item))
      return bot
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  async function remove(botId: string): Promise<boolean> {
    error.value = null
    try {
      const result = await gatewayService.call<{ ok: boolean }>('deleteBot', { botId })
      if (!result.ok) return false
      bots.value = bots.value.filter((bot) => bot.id !== botId)
      if (activeBotId.value === botId) {
        selectBot(bots.value[0]?.id ?? null)
      }
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return false
    }
  }

  return { bots, activeBotId, activeBot, loading, error, load, create, update, remove, selectBot }
})
