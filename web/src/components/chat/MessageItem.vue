<script setup lang="ts">
import { ChevronRight, Copy, Edit, RefreshCw, ThumbsDown, ThumbsUp, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import ToolCallBlock from '@/components/chat/ToolCallBlock.vue'
import type { UiMessage } from '@/types/session'
import { renderMarkdown } from '@/utils/markdown'

const props = withDefaults(
  defineProps<{
    message: UiMessage
    /** Author line above the bubble; groups pass the bot's name, direct chats pass nothing. */
    authorName?: string
    authorEmoji?: string
    /** Small role tag next to the author line, e.g. 管理员. */
    authorBadge?: string
  }>(),
  { authorName: '', authorEmoji: '', authorBadge: '' },
)

const emit = defineEmits<{
  copy: [content: string]
  edit: [message: UiMessage]
  delete: [message: UiMessage]
  regenerate: [message: UiMessage]
}>()

const isUser = computed(() => props.message.role === 'user')
const renderedContent = computed(() => renderMarkdown(props.message.content))
const showActions = ref(false)
const showThinking = ref(false)

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
    class="flex"
    :class="isUser ? 'justify-end' : 'justify-start'"
    @mouseenter="showActions = true"
    @mouseleave="showActions = false"
  >
    <div class="min-w-0 max-w-[85%] space-y-1.5">
      <!-- 作者行（群聊里由父组件传入） -->
      <div
        v-if="authorName"
        class="flex items-center gap-1.5 text-[12px] text-[var(--color-text-faint)]"
        :class="isUser ? 'justify-end' : ''"
      >
        <span v-if="authorEmoji" aria-hidden="true">{{ authorEmoji }}</span>
        <span class="font-medium text-[var(--color-text-muted)]">{{ authorName }}</span>
        <span
          v-if="authorBadge"
          class="rounded-[var(--radius-sm)] bg-[var(--color-surface)] px-1.5 py-0.5 text-[10px] leading-none text-[var(--color-text-muted)]"
        >{{ authorBadge }}</span>
      </div>

      <!-- 思考过程：折叠成一行 -->
      <button
        v-if="message.thinking"
        type="button"
        class="flex items-center gap-1 text-[12px] text-[var(--color-text-faint)] transition hover:text-[var(--color-text-muted)]"
        :aria-expanded="showThinking"
        @click="showThinking = !showThinking"
      >
        <ChevronRight class="h-3 w-3 transition" :class="showThinking ? 'rotate-90' : ''" />
        思考过程
      </button>
      <div
        v-if="message.thinking && showThinking"
        class="whitespace-pre-wrap break-words rounded-[var(--radius-md)] bg-[var(--color-surface)] px-3 py-2 text-[12px] leading-relaxed text-[var(--color-text-muted)]"
      >
        {{ message.thinking }}
      </div>

      <!-- 工具调用 -->
      <ToolCallBlock v-if="message.role === 'tool'" :message="message" />

      <!-- 等待首字 -->
      <div
        v-else-if="message.loading && !message.content.trim()"
        class="rounded-[var(--radius-xl)] rounded-tl-[var(--radius-sm)] bg-[var(--color-surface)] px-4 py-3"
      >
        <div class="flex items-center gap-1.5" aria-label="正在生成">
          <span class="h-2 w-2 animate-bounce rounded-full bg-[var(--color-text-quaternary)] [animation-delay:0ms] motion-reduce:animate-none" />
          <span class="h-2 w-2 animate-bounce rounded-full bg-[var(--color-text-quaternary)] [animation-delay:150ms] motion-reduce:animate-none" />
          <span class="h-2 w-2 animate-bounce rounded-full bg-[var(--color-text-quaternary)] [animation-delay:300ms] motion-reduce:animate-none" />
        </div>
      </div>

      <!-- 用户消息：深色填充气泡 -->
      <div
        v-else-if="isUser && message.content.trim()"
        class="whitespace-pre-wrap break-words rounded-[var(--radius-xl)] rounded-br-[var(--radius-sm)] bg-[var(--color-send-bg)] px-4 py-2.5 text-[14px] leading-relaxed text-[var(--color-send-icon)]"
      >
        {{ message.content }}
      </div>

      <!-- 助手消息：浅色气泡 + Markdown -->
      <div
        v-else-if="message.content.trim()"
        class="prose max-w-none break-words rounded-[var(--radius-xl)] rounded-tl-[var(--radius-sm)] bg-[var(--color-surface)] px-4 py-2.5 text-[14px] leading-relaxed text-[var(--color-text)] [&_pre]:rounded-[var(--radius-md)]"
        v-html="renderedContent"
      />

      <!-- 操作行 -->
      <div
        v-if="!message.loading && message.content.trim()"
        class="flex items-center gap-1 transition-opacity"
        :class="[showActions ? 'opacity-100' : 'opacity-0', isUser ? 'justify-end' : '']"
      >
        <button
          class="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-text-faint)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
          title="复制"
          @click="handleCopy"
        >
          <Copy class="h-3.5 w-3.5" />
        </button>
        <template v-if="isUser">
          <button
            class="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-text-faint)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
            title="编辑"
            @click="handleEdit"
          >
            <Edit class="h-3.5 w-3.5" />
          </button>
        </template>
        <template v-else>
          <button
            class="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-text-faint)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
            title="重新生成"
            @click="handleRegenerate"
          >
            <RefreshCw class="h-3.5 w-3.5" />
          </button>
          <button
            class="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-text-faint)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
            title="点赞"
          >
            <ThumbsUp class="h-3.5 w-3.5" />
          </button>
          <button
            class="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-text-faint)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
            title="点踩"
          >
            <ThumbsDown class="h-3.5 w-3.5" />
          </button>
        </template>
        <button
          class="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-text-faint)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
          title="删除"
          @click="handleDelete"
        >
          <Trash2 class="h-3.5 w-3.5" />
        </button>
        <span class="ml-1 text-[11px] text-[var(--color-text-faint)]">{{ formatTime(message.timestamp) }}</span>
      </div>
    </div>
  </div>
</template>
