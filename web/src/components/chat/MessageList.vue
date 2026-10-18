<script setup lang="ts">
import { ChevronDown } from '@lucide/vue'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import MessageItem from '@/components/chat/MessageItem.vue'
import { useChatStore } from '@/stores/chat'
import type { DynamicScrollerExposed } from 'vue-virtual-scroller'
import type { UiMessage } from '@/types/session'

const chatStore = useChatStore()
/** `DynamicScrollerExposed` omits `$el`, but the component instance does have one. */
type ScrollerInstance = DynamicScrollerExposed<UiMessage> & { $el: HTMLElement }
const scrollerRef = ref<ScrollerInstance | null>(null)
const showScrollBtn = ref(false)

function scrollToBottom(smooth = false) {
  const el = scrollerRef.value?.$el
  if (!el) return
  el.scrollTo({
    top: el.scrollHeight,
    behavior: smooth ? 'smooth' : 'instant',
  })
}

function checkScroll() {
  const el = scrollerRef.value?.$el
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100
  showScrollBtn.value = !atBottom
}

onMounted(() => {
  const el = scrollerRef.value?.$el
  if (el) {
    el.addEventListener('scroll', checkScroll, { passive: true })
  }
})

onUnmounted(() => {
  const el = scrollerRef.value?.$el
  if (el) {
    el.removeEventListener('scroll', checkScroll)
  }
})

watch(
  () => chatStore.messages.length,
  async () => {
    await nextTick()
    scrollToBottom()
  },
)

watch(
  () => chatStore.messages[chatStore.messages.length - 1]?.content,
  async () => {
    await nextTick()
    scrollToBottom()
  },
)

function sizeDependencies(message: UiMessage) {
  return [
    message.content,
    message.thinking,
    message.loading,
    message.toolExecution?.output,
    message.toolCall?.arguments,
  ]
}

function handleCopy(content: string) {
  navigator.clipboard.writeText(content)
}

function handleEdit(message: UiMessage) {
  console.log('Edit message:', message)
}

function handleDelete(message: UiMessage) {
  console.log('Delete message:', message)
}

function handleRegenerate(message: UiMessage) {
  console.log('Regenerate message:', message)
}
</script>

<template>
  <div class="relative h-full overflow-hidden">
    <DynamicScroller
      ref="scrollerRef"
      class="h-full pt-8"
      :items="chatStore.messages"
      key-field="id"
      :min-item-size="80"
    >
      <template #default="{ item, index, active }">
        <DynamicScrollerItem
          :item="item"
          :active="active"
          :data-index="index"
          :size-dependencies="sizeDependencies(item)"
          class="pb-6"
        >
          <div class="max-w-4xl mx-auto px-6">
            <MessageItem
              :message="item"
              @copy="handleCopy"
              @edit="handleEdit"
              @delete="handleDelete"
              @regenerate="handleRegenerate"
            />
          </div>
        </DynamicScrollerItem>
      </template>
    </DynamicScroller>

    <Transition name="fade">
      <button
        v-if="showScrollBtn"
        class="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-4 py-2 rounded-full bg-[var(--bg-card)] border border-[var(--border)] shadow-lg text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition z-10"
        @click="scrollToBottom(true)"
      >
        <ChevronDown class="w-4 h-4" />
        <span>回到底部</span>
      </button>
    </Transition>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
