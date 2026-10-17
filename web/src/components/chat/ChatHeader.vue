<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { gatewayService } from '@/services/gateway'
import { useSessionsStore } from '@/stores/sessions'

const sessionsStore = useSessionsStore()
const route = useRoute()
const connected = ref(gatewayService.isConnected())

let unsubscribeOpen: (() => void) | null = null
let unsubscribeClose: (() => void) | null = null

onMounted(() => {
  connected.value = gatewayService.isConnected()
  unsubscribeOpen = gatewayService.on('open', () => {
    connected.value = true
  })
  unsubscribeClose = gatewayService.on('close', () => {
    connected.value = false
  })
})

onUnmounted(() => {
  unsubscribeOpen?.()
  unsubscribeClose?.()
})

const currentTitle = computed(() => {
  const id = route.params.sessionId
  if (typeof id !== 'string' || id.length === 0) return '小巧'
  const session = sessionsStore.sessions.find((s) => s.id === id)
  return session?.title || '未命名会话'
})
</script>

<template>
  <header class="h-14 flex items-center justify-between px-6 border-b border-[var(--border)] bg-[var(--bg-page)]">
    <h1 class="text-sm font-medium truncate">
      {{ currentTitle }}
    </h1>

    <div class="flex items-center gap-2">
      <span
        class="w-2 h-2 rounded-full"
        :class="connected ? 'bg-green-500' : 'bg-red-500'"
      />
      <span class="text-xs text-[var(--text-subtle)]">
        {{ connected ? '已连接' : '未连接' }}
      </span>
    </div>
  </header>
</template>
