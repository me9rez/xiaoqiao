<script setup lang="ts">
import { computed, onActivated, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ApprovalPanel from '@/components/ApprovalPanel.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import MessageList from '@/components/chat/MessageList.vue'
import { useChatStore } from '@/stores/chat'
import { useSessionsStore } from '@/stores/sessions'

const props = defineProps<{
  sessionId: string
}>()

const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()
const sessionsStore = useSessionsStore()
const loading = ref(false)
const initialMessageSent = ref(false)

const currentSessionModel = computed(() => {
  const session = sessionsStore.sessions.find((s) => s.id === props.sessionId)
  return session?.model || ''
})

async function loadSessionData(id: string) {
  if (!id) return
  loading.value = true
  sessionsStore.selectSession(id)
  try {
    const session = await sessionsStore.loadSession(id)
    if (session) {
      chatStore.loadSession(session)
    }
  } finally {
    loading.value = false
    // Send initial message after session data is loaded
    const msg = route.query.initialMessage
    if (msg && typeof msg === 'string' && !initialMessageSent.value) {
      initialMessageSent.value = true
      router.replace({ query: { ...route.query, initialMessage: undefined } })
      chatStore.sendMessage(msg, props.sessionId)
    }
  }
}

watch(
  () => props.sessionId,
  () => {
    initialMessageSent.value = false
    loadSessionData(props.sessionId)
  },
  { immediate: true },
)

// When the keep-alive cached instance becomes active again (e.g. user switches
// back from another session), make sure the chat store reflects the latest
// backend state for this session.
onActivated(() => {
  if (route.params.sessionId === props.sessionId) {
    loadSessionData(props.sessionId)
  }
})

function handleSend(text: string) {
  chatStore.sendMessage(text, props.sessionId)
}

async function handleModelChange(model: string) {
  await sessionsStore.updateSessionModel(props.sessionId, model)
}

function handleStop() {
  chatStore.stop()
}
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0">
    <MessageList
      v-if="chatStore.messages.length > 0"
      class="flex-1 overflow-y-auto"
    />
    <div v-else class="flex-1 flex items-center justify-center text-sm text-[var(--text-muted)] select-none">
      <div class="text-center px-6 py-10">
        <div class="text-base text-[var(--text-primary)] mb-1">开始新的对话</div>
        <div class="text-xs text-[var(--text-muted)]">向小巧提问即可在此处查看回复</div>
      </div>
    </div>
    <div class="px-4 pb-2">
      <ApprovalPanel />
    </div>
    <ChatInput
      :model="currentSessionModel"
      :disabled="chatStore.isRunning"
      @send="handleSend"
      @stop="handleStop"
      @update:model="handleModelChange"
    />
  </div>
</template>
