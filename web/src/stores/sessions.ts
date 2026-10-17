import { defineStore } from 'pinia'
import { ref } from 'vue'
import { gatewayService } from '@/services/gateway'
import type { SessionData, SessionInfo } from '@/types/session'

export const useSessionsStore = defineStore('sessions', () => {
  const sessions = ref<SessionInfo[]>([])
  const currentSessionId = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchSessions() {
    loading.value = true
    error.value = null
    try {
      const result = await gatewayService.call<SessionInfo[]>('listSessions')
      sessions.value = result
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  async function createSession(title = '', model = '', workspace = '', botId = '') {
    error.value = null
    try {
      const params: Record<string, unknown> = { title }
      if (model) params.model = model
      if (workspace) params.workspace = workspace
      if (botId) params.botId = botId
      const session = await gatewayService.call<SessionData>('createSession', params)
      await fetchSessions()
      currentSessionId.value = session.id
      return session
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  async function loadSession(sessionId: string) {
    error.value = null
    try {
      const session = await gatewayService.call<SessionData>('loadSession', { sessionId })
      currentSessionId.value = session.id
      return session
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  async function updateSession(sessionId: string, title: string) {
    error.value = null
    try {
      await gatewayService.call<SessionData>('updateSession', { sessionId, title })
      await fetchSessions()
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    }
  }

  async function updateSessionModel(sessionId: string, model: string) {
    error.value = null
    try {
      await gatewayService.call<SessionData>('updateSession', { sessionId, model })
      const local = sessions.value.find((s) => s.id === sessionId)
      if (local) {
        local.model = model
      }
      await fetchSessions()
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    }
  }

  async function deleteSession(sessionId: string) {
    error.value = null
    try {
      await gatewayService.call<{ ok: boolean }>('deleteSession', { sessionId })
      if (currentSessionId.value === sessionId) {
        currentSessionId.value = null
      }
      await fetchSessions()
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    }
  }

  function selectSession(sessionId: string) {
    currentSessionId.value = sessionId
  }

  function clearCurrentSession() {
    currentSessionId.value = null
  }

  return {
    sessions,
    currentSessionId,
    loading,
    error,
    fetchSessions,
    createSession,
    loadSession,
    updateSession,
    updateSessionModel,
    deleteSession,
    selectSession,
    clearCurrentSession,
  }
})
