import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { gatewayService } from '@/services/gateway'
import type { Routine, RoutineDraft } from '@/types/routine'
import { isRoutineFiredEvent } from '@/types/gateway'

export const useRoutinesStore = defineStore('routines', () => {
  const routines = ref<Routine[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let unsubscribe: (() => void) | null = null

  const enabledCount = computed(() => routines.value.filter((routine) => routine.enabled).length)

  async function load(botId?: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      routines.value = await gatewayService.call<Routine[]>('listRoutines', botId ? { botId } : {})
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  async function create(draft: RoutineDraft): Promise<Routine | null> {
    error.value = null
    try {
      const routine = await gatewayService.call<Routine>('createRoutine', { ...draft })
      routines.value = [routine, ...routines.value]
      return routine
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  async function update(routineId: string, patch: Partial<RoutineDraft>): Promise<Routine | null> {
    error.value = null
    try {
      const routine = await gatewayService.call<Routine>('updateRoutine', { routineId, ...patch })
      routines.value = routines.value.map((item) => (item.id === routine.id ? routine : item))
      return routine
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  async function toggle(routineId: string, enabled: boolean): Promise<Routine | null> {
    error.value = null
    try {
      const routine = await gatewayService.call<Routine>('toggleRoutine', { routineId, enabled })
      routines.value = routines.value.map((item) => (item.id === routine.id ? routine : item))
      return routine
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  async function remove(routineId: string): Promise<boolean> {
    error.value = null
    try {
      const result = await gatewayService.call<{ ok: boolean }>('deleteRoutine', { routineId })
      if (!result.ok) return false
      routines.value = routines.value.filter((item) => item.id !== routineId)
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return false
    }
  }

  function listen(): () => void {
    if (unsubscribe) return unsubscribe
    unsubscribe = gatewayService.on('routine_fired', (event) => {
      if (isRoutineFiredEvent(event)) void load()
    })
    return unsubscribe
  }

  return { routines, enabledCount, loading, error, load, create, update, toggle, remove, listen }
})
