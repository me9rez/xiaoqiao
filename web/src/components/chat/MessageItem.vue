<script setup lang="ts">
import { Bot, Copy, Edit, RefreshCw, ThumbsDown, ThumbsUp, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import ToolCallBlock from '@/components/chat/ToolCallBlock.vue'
import type { UiMessage } from '@/types/session'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{
  message: UiMessage
}>()

const emit = defineEmits<{
  copy: [content: string]
  edit: [message: UiMessage]
  delete: [message: UiMessage]
  regenerate: [message: UiMessage]
}>()

const renderedContent = computed(() => renderMarkdown(props.message.content))
const showActions = ref(false)

function handleCopy() {
  emit('copy', props.message.content)
}

function handleEdit() {
  emit('edit', props.message)
}

function handleDelete() {
  emit('delete', props.message)
}

function handleRegenerate() {
  emit('regenerate', props.message)
}

function formatTime(timestamp?: number) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))

  if (days > 0) {
    return `昨天 ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
  }
  return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
}
</script>

<template>
  <div
    class="flex gap-3"
    :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
    @mouseenter="showActions = true"
    @mouseleave="showActions = false"
  >
    <div
      v-if="message.role !== 'user'"
      class="w-8 h-8 rounded-full bg-[var(--bg-muted)] flex items-center justify-center flex-shrink-0"
    >
      <Bot class="w-4 h-4 text-[var(--text-muted)]" />
    </div>

    <div class="max-w-[85%] space-y-2">
      <div
        v-if="message.role === 'user' && message.content.trim()"
        class="px-4 py-2.5 rounded-2xl rounded-br-sm bg-[var(--text)] text-[var(--bg-card)] text-sm shadow-[var(--shadow)]"
      >
        {{ message.content }}
      </div>

      <div v-else-if="message.role === 'tool'" class="w-full">
        <ToolCallBlock :message="message" />
      </div>

      <div v-else-if="message.loading && !message.content.trim() && !message.thinking" class="space-y-2">
        <div class="flex items-center gap-2 text-xs text-[var(--text-subtle)]">
          <span class="font-medium text-[var(--text)]">小巧</span>
          <span>·</span>
          <span>助手</span>
        </div>
        <div class="px-4 py-3 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] shadow-[var(--shadow)]">
          <div class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-[var(--text-subtle)] animate-bounce" style="animation-delay: 0ms" />
            <span class="w-2 h-2 rounded-full bg-[var(--text-subtle)] animate-bounce" style="animation-delay: 150ms" />
            <span class="w-2 h-2 rounded-full bg-[var(--text-subtle)] animate-bounce" style="animation-delay: 300ms" />
          </div>
        </div>
      </div>

      <div v-else-if="message.thinking || message.content.trim()" class="space-y-2">
        <div class="flex items-center gap-2 text-xs text-[var(--text-subtle)]">
          <span class="font-medium text-[var(--text)]">小巧</span>
          <span>·</span>
          <span>助手</span>
        </div>

        <div
          v-if="message.thinking"
          class="px-4 py-3 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] text-sm text-[var(--text-muted)] italic shadow-[var(--shadow)]"
        >
          {{ message.thinking }}
        </div>

        <div
          v-if="message.content.trim()"
          class="px-4 py-3 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] text-sm shadow-[var(--shadow)] prose prose-neutral max-w-none"
          v-html="renderedContent"
        />
      </div>

      <div
        v-if="message.role === 'user' && message.content.trim()"
        class="flex items-center gap-1 opacity-0 transition-opacity"
        :class="{ 'opacity-100': showActions }"
      >
        <button
          class="p-1.5 rounded-lg text-[var(--text-subtle)] hover:bg-[var(--bg-muted)] hover:text-[var(--text)] transition"
          title="复制"
          @click="handleCopy"
        >
          <Copy class="w-3.5 h-3.5" />
        </button>
        <button
          class="p-1.5 rounded-lg text-[var(--text-subtle)] hover:bg-[var(--bg-muted)] hover:text-[var(--text)] transition"
          title="编辑"
          @click="handleEdit"
        >
          <Edit class="w-3.5 h-3.5" />
        </button>
        <button
          class="p-1.5 rounded-lg text-[var(--text-subtle)] hover:bg-[var(--bg-muted)] hover:text-[var(--text)] transition"
          title="删除"
          @click="handleDelete"
        >
          <Trash2 class="w-3.5 h-3.5" />
        </button>
        <span class="text-xs text-[var(--text-subtle)] ml-1">{{ formatTime(message.timestamp) }}</span>
      </div>

      <div
        v-if="message.role === 'assistant' && message.content.trim() && !message.loading"
        class="flex items-center gap-1 opacity-0 transition-opacity"
        :class="{ 'opacity-100': showActions }"
      >
        <button
          class="p-1.5 rounded-lg text-[var(--text-subtle)] hover:bg-[var(--bg-muted)] hover:text-[var(--text)] transition"
          title="复制"
          @click="handleCopy"
        >
          <Copy class="w-3.5 h-3.5" />
        </button>
        <button
          class="p-1.5 rounded-lg text-[var(--text-subtle)] hover:bg-[var(--bg-muted)] hover:text-[var(--text)] transition"
          title="重新生成"
          @click="handleRegenerate"
        >
          <RefreshCw class="w-3.5 h-3.5" />
        </button>
        <button
          class="p-1.5 rounded-lg text-[var(--text-subtle)] hover:bg-[var(--bg-muted)] hover:text-[var(--text)] transition"
          title="点赞"
        >
          <ThumbsUp class="w-3.5 h-3.5" />
        </button>
        <button
          class="p-1.5 rounded-lg text-[var(--text-subtle)] hover:bg-[var(--bg-muted)] hover:text-[var(--text)] transition"
          title="点踩"
        >
          <ThumbsDown class="w-3.5 h-3.5" />
        </button>
        <button
          class="p-1.5 rounded-lg text-[var(--text-subtle)] hover:bg-[var(--bg-muted)] hover:text-[var(--text)] transition"
          title="删除"
          @click="handleDelete"
        >
          <Trash2 class="w-3.5 h-3.5" />
        </button>
        <span class="text-xs text-[var(--text-subtle)] ml-1">{{ formatTime(message.timestamp) }}</span>
      </div>
    </div>
  </div>
</template>
