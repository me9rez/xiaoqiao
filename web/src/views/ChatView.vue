<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import BotEditorModal from '@/components/bots/BotEditorModal.vue'
import ChatHeader from '@/components/chat/ChatHeader.vue'
import ContextPanel from '@/components/chat/ContextPanel.vue'
import Sidebar from '@/components/chat/Sidebar.vue'
import { gatewayService } from '@/services/gateway'
import { useActivityStore } from '@/stores/activity'
import { useApprovalsStore } from '@/stores/approvals'
import { useBotsStore } from '@/stores/bots'
import { useGroupsStore } from '@/stores/groups'
import { useSessionsStore } from '@/stores/sessions'
import type { Bot } from '@/types/bot'

const sessionsStore = useSessionsStore()
const botsStore = useBotsStore()
const groupsStore = useGroupsStore()
const approvalsStore = useApprovalsStore()
const activityStore = useActivityStore()
const route = useRoute()

const editorOpen = ref(false)
const editingBot = ref<Bot | null>(null)
let unsubscribe: (() => void) | null = null

function openEditor(bot: Bot | null) {
  editingBot.value = bot
  editorOpen.value = true
}

function closeEditor() {
  editorOpen.value = false
  editingBot.value = null
}

function handleBotSaved() {
  void sessionsStore.fetchSessions()
}

onMounted(() => {
  groupsStore.listen()
  approvalsStore.listen()
  activityStore.listen()
  if (gatewayService.isConnected()) {
    void botsStore.load()
    void groupsStore.load()
    void activityStore.load()
  }
  unsubscribe = gatewayService.on('open', () => {
    void botsStore.load()
    void groupsStore.load()
    void activityStore.load()
  })
})

onUnmounted(() => {
  unsubscribe?.()
})

// Drive the active session from the route so the sidebar highlight and the
// chat input both agree with whatever URL the user is on.
const activeSessionId = computed<string | null>(() => {
  const id = route.params.sessionId
  if (typeof id === 'string' && id.length > 0) {
    if (sessionsStore.currentSessionId !== id) {
      sessionsStore.selectSession(id)
    }
    return id
  }
  if (sessionsStore.currentSessionId) {
    sessionsStore.clearCurrentSession()
  }
  return null
})

// Each session gets a stable, unique cache key so keep-alive can hold a
// separate instance per session. The home view uses the literal 'home' key.
const keepAliveKey = computed(() => {
  const groupId = route.params.groupId
  if (typeof groupId === 'string' && groupId.length > 0) {
    return `group:${groupId}`
  }
  if (activeSessionId.value) {
    return `session:${activeSessionId.value}`
  }
  return 'home'
})
</script>

<template>
  <div class="h-full flex bg-[var(--color-bg)] text-[var(--color-text)]">
    <Sidebar
      class="w-[var(--p-sidebar-w)] flex-shrink-0 border-r border-[var(--color-line)]"
      @edit-bot="openEditor"
    />

    <main class="flex-1 flex flex-col min-w-0 bg-[var(--color-bg)]">
      <ChatHeader />
      <RouterView v-slot="{ Component }">
        <keep-alive :max="10">
          <component :is="Component" :key="keepAliveKey" />
        </keep-alive>
      </RouterView>
    </main>

    <ContextPanel />

    <BotEditorModal :open="editorOpen" :bot="editingBot" @close="closeEditor" @saved="handleBotSaved" />
  </div>
</template>
