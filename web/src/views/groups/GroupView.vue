<script setup lang="ts">
import { Settings2, SendHorizontal } from '@lucide/vue'
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import GroupEditorModal from '@/components/groups/GroupEditorModal.vue'
import MentionPicker from '@/components/groups/MentionPicker.vue'
import { useActivityStore } from '@/stores/activity'
import { useBotsStore } from '@/stores/bots'
import { useGroupsStore } from '@/stores/groups'
import type { Bot } from '@/types/bot'
import type { GroupMessage } from '@/types/group'

const props = defineProps<{ groupId: string }>()

const botsStore = useBotsStore()
const groupsStore = useGroupsStore()
const activityStore = useActivityStore()

const editorOpen = ref(false)
const draft = ref('')
const listEl = ref<HTMLElement | null>(null)

const group = computed(() => groupsStore.groups.find((item) => item.id === props.groupId) ?? null)
const members = computed(() => botsStore.bots.filter((bot) => group.value?.botIds.includes(bot.id)))
const messages = computed(() => groupsStore.messagesFor(props.groupId))

/**
 * Who is actually working right now. "Bot 正在回复…" is not wrong but it hides the
 * useful part — in a group you want to know *which* bot picked it up.
 */
const workingMembers = computed(() =>
  members.value.filter((bot) => activityStore.stateOf(bot.id) === 'working'),
)

const progressLabel = computed(() => {
  const names = workingMembers.value.map((bot) => bot.name)
  if (names.length === 0) return 'Bot 正在回复…'
  if (names.length === 1) return `${names[0]} 正在回复…`
  return `${names.slice(0, 2).join('、')}${names.length > 2 ? ` 等 ${names.length} 个 Bot` : ''} 正在回复…`
})

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

/** The group's manager bot gets a 管理员 tag next to its name. */
function authorBadge(message: GroupMessage): string {
  const admin = group.value?.adminBotId ?? group.value?.defaultBotId
  return admin && message.authorId === admin ? '管理员' : ''
}

interface TextSegment {
  text: string
  mention: boolean
}

/**
 * Split a message into plain and `@mention` runs. Only slugs/names that belong to
 * a member become a chip — a stray "@foo" stays plain text.
 */
function segments(text: string): TextSegment[] {
  const known = new Set<string>()
  for (const bot of members.value) {
    known.add(bot.slug.toLowerCase())
    known.add(bot.name.toLowerCase())
  }
  const parts: TextSegment[] = []
  const pattern = /@([^\s@，。！？、,.!?;:]+)/g
  let cursor = 0
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0
    const handle = (match[1] ?? '').toLowerCase()
    if (!known.has(handle)) continue
    if (start > cursor) parts.push({ text: text.slice(cursor, start), mention: false })
    parts.push({ text: match[0], mention: true })
    cursor = start + match[0].length
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), mention: false })
  return parts.length > 0 ? parts : [{ text, mention: false }]
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
  <div class="relative flex-1 flex flex-col min-h-0">
    <button
      type="button"
      class="absolute right-4 top-2 z-10 flex h-8 w-8 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-text-faint)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
      aria-label="群设置"
      title="群设置"
      @click="editorOpen = true"
    >
      <Settings2 class="w-4 h-4" />
    </button>

    <div ref="listEl" class="flex-1 overflow-y-auto px-6 pb-4 pt-2" role="log" aria-live="polite">
      <div class="max-w-[var(--p-content-max)] mx-auto space-y-4">
        <div v-if="messages.length === 0" class="py-16 text-center text-[13px] text-[var(--color-text-muted)]">
          还没有消息。@ 一个 Bot 开始协作。
        </div>

        <template v-for="message in messages" :key="message.id">
          <!-- 系统事件：居中的一行 -->
          <div v-if="message.authorType === 'system'" class="text-center text-[12px] text-[var(--color-text-faint)]">
            {{ message.text }}
          </div>

          <!-- 用户：深色填充气泡 -->
          <div v-else-if="message.authorType === 'user'" class="flex justify-end">
            <div class="max-w-[var(--p-bubble-max)] space-y-1">
              <div class="flex items-center justify-end gap-2 text-[12px] text-[var(--color-text-faint)]">
                <span>你</span>
                <span>{{ formatTime(message.createdAt) }}</span>
              </div>
              <div
                class="whitespace-pre-wrap break-words rounded-[var(--radius-xl)] rounded-br-[var(--radius-sm)] bg-[var(--color-send-bg)] px-4 py-2.5 text-[14px] leading-relaxed text-[var(--color-send-icon)]"
              >
                {{ message.text }}
              </div>
            </div>
          </div>

          <!-- Bot：作者行（emoji + 名字 + 管理员）+ 浅色气泡 -->
          <div v-else class="flex justify-start">
            <div class="min-w-0 max-w-[var(--p-bubble-max)] space-y-1">
              <div class="flex items-center gap-1.5 text-[12px] text-[var(--color-text-faint)]">
                <span aria-hidden="true">{{ authorBot(message)?.emoji || '🤖' }}</span>
                <span class="font-medium text-[var(--color-text-muted)]">{{ authorName(message) }}</span>
                <span
                  v-if="authorBadge(message)"
                  class="rounded-[var(--radius-sm)] bg-[var(--color-surface)] px-1.5 py-0.5 text-[10px] leading-none text-[var(--color-text-muted)]"
                >{{ authorBadge(message) }}</span>
                <span>{{ formatTime(message.createdAt) }}</span>
              </div>
              <div
                class="whitespace-pre-wrap break-words rounded-[var(--radius-xl)] rounded-tl-[var(--radius-sm)] bg-[var(--color-surface)] px-4 py-2.5 text-[14px] leading-relaxed text-[var(--color-text)]"
              >
                <template v-for="(segment, index) in segments(message.text)" :key="index">
                  <span
                    v-if="segment.mention"
                    class="rounded-[var(--radius-xs)] bg-[var(--color-accent-soft)] px-1 text-[var(--color-accent)]"
                  >{{ segment.text }}</span>
                  <span v-else>{{ segment.text }}</span>
                </template>
              </div>
            </div>
          </div>
        </template>

        <div
          v-if="groupsStore.sending"
          class="flex items-center gap-2 text-[12px] text-[var(--color-text-muted)]"
          role="status"
        >
          <span class="flex -space-x-1" aria-hidden="true">
            <span
              v-for="bot in workingMembers.slice(0, 3)"
              :key="bot.id"
              class="flex h-5 w-5 items-center justify-center rounded-full border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] text-[10px]"
            >{{ bot.emoji || '🤖' }}</span>
          </span>
          <span class="flex items-center gap-1" aria-hidden="true">
            <span class="w-1 h-1 rounded-full bg-[var(--color-text-faint)] animate-bounce [animation-delay:0ms] motion-reduce:animate-none" />
            <span class="w-1 h-1 rounded-full bg-[var(--color-text-faint)] animate-bounce [animation-delay:150ms] motion-reduce:animate-none" />
            <span class="w-1 h-1 rounded-full bg-[var(--color-text-faint)] animate-bounce [animation-delay:300ms] motion-reduce:animate-none" />
          </span>
          <span>{{ progressLabel }}</span>
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
            :placeholder="`给 ${group?.name ?? '群聊'} 发消息，@ 指定 Bot`"
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
