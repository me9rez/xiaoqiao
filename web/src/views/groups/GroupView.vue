<script setup lang="ts">
import { Settings2, SendHorizontal } from '@lucide/vue'
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import BotAvatar from '@/components/bots/BotAvatar.vue'
import GroupEditorModal from '@/components/groups/GroupEditorModal.vue'
import MentionPicker from '@/components/groups/MentionPicker.vue'
import { useBotsStore } from '@/stores/bots'
import { useGroupsStore } from '@/stores/groups'
import type { Bot } from '@/types/bot'
import type { GroupMessage } from '@/types/group'

const props = defineProps<{ groupId: string }>()

const botsStore = useBotsStore()
const groupsStore = useGroupsStore()

const editorOpen = ref(false)
const draft = ref('')
const listEl = ref<HTMLElement | null>(null)

const group = computed(() => groupsStore.groups.find((item) => item.id === props.groupId) ?? null)
const members = computed(() => botsStore.bots.filter((bot) => group.value?.botIds.includes(bot.id)))
const messages = computed(() => groupsStore.messagesFor(props.groupId))

const mentionQuery = computed(() => {
  const match = draft.value.match(/@([^\s@]*)$/)
  return match ? match[1] : null
})
const pickerOpen = computed(() => mentionQuery.value !== null)

function authorName(message: GroupMessage): string {
  if (message.authorType === 'user') return '你'
  if (message.authorType === 'system') return '系统'
  return botsStore.bots.find((bot) => bot.id === message.authorId)?.name ?? 'Bot'
}

function authorBot(message: GroupMessage): Bot | null {
  return botsStore.bots.find((bot) => bot.id === message.authorId) ?? null
}

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function insertMention(bot: Bot) {
  draft.value = draft.value.replace(/@([^\s@]*)$/, `@${bot.slug} `)
}

function send() {
  const text = draft.value.trim()
  if (!text || groupsStore.sending) return
  groupsStore.sendMessage(props.groupId, text)
  draft.value = ''
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    send()
  }
}

function scrollToBottom() {
  nextTick(() => {
    const el = listEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function load() {
  groupsStore.selectGroup(props.groupId)
  await groupsStore.loadMessages(props.groupId)
  scrollToBottom()
}

watch(() => props.groupId, load, { immediate: true })
watch(() => messages.value.length, scrollToBottom)

onMounted(() => {
  if (botsStore.bots.length === 0) void botsStore.load()
  if (groupsStore.groups.length === 0) void groupsStore.load()
})
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0">
    <header
      class="h-[var(--p-group-header-h)] flex items-center gap-3 px-6 border-b border-[var(--color-line)] bg-[var(--color-bg)]"
    >
      <h2 class="text-[15px] font-[var(--weight-medium)] text-[var(--color-text-strong)] truncate">
        {{ group?.name || '群聊' }}
      </h2>
      <div class="flex items-center -space-x-1.5">
        <BotAvatar
          v-for="bot in members.slice(0, 4)"
          :key="bot.id"
          :bot="bot"
          size="sm"
          class="ring-2 ring-[var(--color-bg)]"
        />
        <span v-if="members.length > 4" class="pl-3 text-[12px] text-[var(--color-text-faint)]">
          +{{ members.length - 4 }}
        </span>
      </div>
      <span class="flex-1" />
      <button
        type="button"
        class="p-2 rounded-[var(--radius-md)] text-[var(--color-text-muted)] hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
        aria-label="群设置"
        title="群设置"
        @click="editorOpen = true"
      >
        <Settings2 class="w-4 h-4" />
      </button>
    </header>

    <div ref="listEl" class="flex-1 overflow-y-auto px-6 py-4" role="log" aria-live="polite">
      <div class="max-w-[var(--p-content-max)] mx-auto space-y-4">
        <div v-if="messages.length === 0" class="py-16 text-center text-[13px] text-[var(--color-text-muted)]">
          还没有消息。@ 一个 Bot 开始协作。
        </div>

        <template v-for="message in messages" :key="message.id">
          <div v-if="message.authorType === 'system'" class="text-center text-[12px] text-[var(--color-text-faint)]">
            {{ message.text }}
          </div>

          <div v-else-if="message.authorType === 'user'" class="flex justify-end">
            <div class="max-w-[var(--p-bubble-max)]">
              <div class="flex items-center justify-end gap-2 mb-1 text-[12px] text-[var(--color-text-faint)]">
                <span>{{ formatTime(message.createdAt) }}</span>
                <span class="text-[var(--color-text)] font-[var(--weight-medium)]">你</span>
              </div>
              <div
                class="px-3.5 py-2.5 rounded-[var(--radius-xl)] bg-[var(--color-user-bubble-bg)] text-[14px] leading-relaxed text-[var(--color-text)] whitespace-pre-wrap break-words"
              >
                {{ message.text }}
              </div>
            </div>
          </div>

          <div v-else class="flex gap-2.5">
            <BotAvatar v-if="authorBot(message)" :bot="authorBot(message)!" size="sm" class="mt-0.5" />
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 mb-1 text-[12px] text-[var(--color-text-faint)]">
                <span class="text-[var(--color-text)] font-[var(--weight-medium)]">{{ authorName(message) }}</span>
                <span>{{ formatTime(message.createdAt) }}</span>
              </div>
              <div class="text-[14px] leading-relaxed text-[var(--color-text)] whitespace-pre-wrap break-words">
                {{ message.text }}
              </div>
            </div>
          </div>
        </template>

        <div v-if="groupsStore.sending" class="flex items-center gap-2 text-[12px] text-[var(--color-text-muted)]">
          <span class="flex items-center gap-1" aria-hidden="true">
            <span class="w-1 h-1 rounded-full bg-[var(--color-text-faint)] animate-bounce [animation-delay:0ms] motion-reduce:animate-none" />
            <span class="w-1 h-1 rounded-full bg-[var(--color-text-faint)] animate-bounce [animation-delay:150ms] motion-reduce:animate-none" />
            <span class="w-1 h-1 rounded-full bg-[var(--color-text-faint)] animate-bounce [animation-delay:300ms] motion-reduce:animate-none" />
          </span>
          <span>Bot 正在回复…</span>
        </div>
      </div>
    </div>

    <div class="px-4 pb-4">
      <div class="relative max-w-[var(--p-content-max)] mx-auto">
        <MentionPicker
          v-if="pickerOpen"
          :bots="members"
          :query="mentionQuery ?? ''"
          @select="insertMention"
        />
        <div
          class="flex items-end gap-2 px-4 py-3 rounded-[var(--radius-composer)] border-0.5 border-[var(--color-composer-line)] bg-[var(--color-composer-bg)] shadow-[var(--shadow-input)] focus-within:border-[var(--color-composer-focus-line)]"
        >
          <textarea
            v-model="draft"
            rows="1"
            class="flex-1 resize-none bg-transparent outline-none text-[14px] leading-relaxed text-[var(--color-text)] placeholder:text-[var(--color-text-faint)] max-h-40"
            placeholder="输入消息，@ 指定 Bot；不写 @ 走默认 Bot"
            aria-label="群聊消息"
            @keydown="onKeydown"
          />
          <button
            type="button"
            class="w-8 h-8 rounded-full flex items-center justify-center bg-[var(--color-send-bg)] text-[var(--color-send-icon)] hover:bg-[var(--color-send-bg-hover)] disabled:opacity-50"
            :disabled="!draft.trim() || groupsStore.sending"
            aria-label="发送"
            @click="send"
          >
            <SendHorizontal class="w-4 h-4" />
          </button>
        </div>
        <p v-if="groupsStore.error" class="mt-2 text-[12px] text-[var(--color-danger)]" role="alert">
          {{ groupsStore.error }}
        </p>
      </div>
    </div>

    <GroupEditorModal :open="editorOpen" :group="group" @close="editorOpen = false" />
  </div>
</template>
