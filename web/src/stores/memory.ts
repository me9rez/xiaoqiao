import { defineStore } from 'pinia'
import { ref } from 'vue'

import { gatewayService } from '@/services/gateway'
import type { MemoryFact, MemoryNote } from '@/types/memory'

interface MemoryPayload {
  facts: MemoryFact[]
  notes: MemoryNote[]
}

export const useMemoryStore = defineStore('memory', () => {
  const facts = ref<MemoryFact[]>([])
  const notes = ref<MemoryNote[]>([])
  const results = ref<MemoryNote[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(botId: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const payload = await gatewayService.call<MemoryPayload>('listMemory', { botId })
      facts.value = payload.facts
      notes.value = payload.notes
      results.value = []
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  async function upsert(botId: string, key: string, value: string): Promise<boolean> {
    error.value = null
    try {
      const fact = await gatewayService.call<MemoryFact>('upsertMemory', { botId, key, value })
      const index = facts.value.findIndex((item) => item.key === fact.key)
      if (index >= 0) facts.value[index] = fact
      else facts.value = [fact, ...facts.value]
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return false
    }
  }

  async function remove(botId: string, key: string): Promise<boolean> {
    error.value = null
    try {
      const result = await gatewayService.call<{ ok: boolean }>('deleteMemory', { botId, key })
      if (result.ok) facts.value = facts.value.filter((item) => item.key !== key)
      return result.ok
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return false
    }
  }

  async function addNote(botId: string, text: string): Promise<boolean> {
    error.value = null
    try {
      const note = await gatewayService.call<MemoryNote>('addMemoryNote', { botId, text })
      notes.value = [note, ...notes.value]
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return false
    }
  }

  async function search(botId: string, query: string): Promise<void> {
    error.value = null
    try {
      results.value = query.trim()
        ? await gatewayService.call<MemoryNote[]>('searchMemory', { botId, query })
        : []
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    }
  }

  return { facts, notes, results, loading, error, load, upsert, remove, addNote, search }
})
