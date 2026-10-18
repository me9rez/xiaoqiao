import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { gatewayService } from '@/services/gateway'
import type { ActivityEvent, ActivitySnapshot, BotActivity, BotActivityState } from '@/types/activity'

/**
 * Bot activity, owned by the server.
 *
 * The chat store still tracks the *current* session's run state for the
 * composer, but it is client-local: it dies on reload. This store mirrors the
 * server snapshot so the rail, the sidebar and the Now view all agree — and
 * keep agreeing after a refresh or from a second window.
 */
export const useActivityStore = defineStore('activity', () => {
  const snapshot = ref<ActivitySnapshot | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  let unsubscribe: (() => void) | null = null

  const bots = computed<BotActivity[]>(() => snapshot.value?.bots ?? [])

  const byState = computed(() => ({
    needsYou: bots.value.filter((entry) => entry.state === 'needs_you'),
    working: bots.value.filter((entry) => entry.state === 'working'),
    failing: bots.value.filter((entry) => entry.state === 'error'),
  }))

  function entryOf(botId: string): BotActivity | undefined {
    return bots.value.find((entry) => entry.botId === botId)
  }

  function stateOf(botId: string): BotActivityState {
    return entryOf(botId)?.state ?? 'idle'
  }

  function entryForSession(sessionId: string): BotActivity | undefined {
    return bots.value.find((entry) => entry.sessionId === sessionId && entry.state !== 'idle')
  }

  function apply(payload: ActivitySnapshot): void {
    snapshot.value = {
      bots: payload.bots ?? [],
      pendingApprovals: payload.pendingApprovals ?? 0,
      generatedAt: payload.generatedAt,
    }
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      apply(await gatewayService.call<ActivitySnapshot>('getActivity'))
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  function listen(): () => void {
    if (unsubscribe) return unsubscribe
    const off = gatewayService.on('activity', (event) => {
      apply(event as ActivityEvent)
    })
    const offOpen = gatewayService.on('open', () => {
      void load()
    })
    unsubscribe = () => {
      off()
      offOpen()
      unsubscribe = null
    }
    return unsubscribe
  }

  function stop(): void {
    unsubscribe?.()
    unsubscribe = null
  }

  return { snapshot, bots, byState, loading, error, entryOf, stateOf, entryForSession, load, listen, stop }
})
