import { defineStore } from 'pinia'
import { ref } from 'vue'

import { gatewayService } from '@/services/gateway'
import type { Artifact } from '@/types/artifact'
import { isArtifactCreatedEvent } from '@/types/gateway'

export const useArtifactsStore = defineStore('artifacts', () => {
  const items = ref<Artifact[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let unsubscribe: (() => void) | null = null

  async function load(botId?: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      items.value = await gatewayService.call<Artifact[]>('listArtifacts', botId ? { botId } : {})
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  function upsert(artifact: Artifact): void {
    items.value = [artifact, ...items.value.filter((item) => item.id !== artifact.id)]
  }

  function listen(): () => void {
    if (unsubscribe) return unsubscribe
    unsubscribe = gatewayService.on('artifact_created', (event) => {
      if (isArtifactCreatedEvent(event)) upsert(event.artifact)
    })
    return unsubscribe
  }

  return { items, loading, error, load, upsert, listen }
})
