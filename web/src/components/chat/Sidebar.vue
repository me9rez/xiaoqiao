<script setup lang="ts">
import {
  Activity,
  CalendarClock,
  ChevronDown,
  Clock,
  Ellipsis,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Star,
  Users,
  Wrench,
} from '@lucide/vue'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import GroupEditorModal from '@/components/groups/GroupEditorModal.vue'
import EntityRow from '@/components/shell/EntityRow.vue'
import { gatewayService } from '@/services/gateway'
import { useActivityStore } from '@/stores/activity'
import { useApprovalsStore } from '@/stores/approvals'
import { useBotsStore } from '@/stores/bots'
import { useChatStore } from '@/stores/chat'
import { useGroupsStore } from '@/stores/groups'
import { useSessionsStore } from '@/stores/sessions'
import { useWorkspaceStore } from '@/stores/workspace'
import type { BotActivityState } from '@/types/activity'
import type { Bot } from '@/types/bot'
import type { Group } from '@/types/group'
import { isSessionUnread } from '@/utils/unread'

const emit = defineEmits<{ editBot: [bot: Bot | null] }>()

const chatStore = useChatStore()
const sessionsStore = useSessionsStore()
const botsStore = useBotsStore()
const groupsStore = useGroupsStore()
const approvalsStore = useApprovalsStore()
const activityStore = useActivityStore()
const workspaceStore = useWorkspaceStore()
const router = useRouter()

const menuOpen = ref(false)
const filtering = ref(false)
const query = ref('')
const filterInput = ref<HTMLInputElement | null>(null)
const connected = ref(gatewayService.isConnected())

const editingId = ref<string | null>(null)
const editingTitle = ref('')
const renameInputRef = ref<HTMLInputElement | null>(null)
const creating = ref(false)
const groupEditorOpen = ref(false)
const editingGroup = ref<Group | null>(null)
const showRecent = ref(false)

let unsubscribeOpen: (() => void) | null = null
let unsubscribeClose: (() => void) | null = null

/** The first bot is the "main" one — the card at the top of the sidebar. */
const mainBot = computed<Bot | null>(() => botsStore.bots[0] ?? null)
const otherBots = computed(() => botsStore.bots.slice(1))
const groups = computed(() => groupsStore.groups.filter((group) => !group.archived))

const firstBotId = computed(() => botsStore.bots[0]?.id ?? '')

/** Sessions belong to a bot; legacy rows without botId fall under the first bot. */
function belongsToActiveBot(session: { botId?: string }): boolean {
  const active = botsStore.activeBotId
  if (!active) return true
  return session.botId ? session.botId === active : firstBotId.value === active
}

function matchesQuery(name: string): boolean {
  const q = query.value.trim().toLowerCase()
  return !q || name.toLowerCase().includes(q)
}

const visibleGroups = computed(() => groups.value.filter((group) => matchesQuery(group.name)))
const visibleBots = computed(() => otherBots.value.filter((bot) => matchesQuery(bot.name)))

function botName(id: string): string {
  return botsStore.bots.find((bot) => bot.id === id)?.name ?? id
}

function botEmoji(id: string): string {
  return botsStore.bots.find((bot) => bot.id === id)?.emoji || '🤖'
}

/** One short line under the name: what this bot is for. */
function botSubtitle(bot: Bot): string {
  if (bot.description) return bot.description
  const line = (bot.persona || '').split('\n').map((part) => part.trim()).find(Boolean) ?? ''
  if (line) return line.length > 40 ? `${line.slice(0, 40)}…` : line
  return bot.model || '还没有介绍'
}

function groupSubtitle(group: Group): string {
  const names = group.botIds.map(botName)
  if (names.length === 0) return '还没有成员'
  const admin = group.adminBotId ?? group.defaultBotId
  const members = names.slice(0, 3).join(' · ') + (names.length > 3 ? ` 等 ${names.length} 个` : '')
  return admin ? `管理员 ${botName(admin)} · ${members}` : members
}

function groupActivity(group: Group): BotActivityState {
  const states = group.botIds.map((id) => activityStore.stateOf(id))
  if (states.includes('needs_you')) return 'needs_you'
  if (states.includes('working')) return 'working'
  if (states.includes('error')) return 'error'
  return 'idle'
}

function sessionState(sessionId: string): BotActivityState {
  const fromServer = activityStore.entryForSession(sessionId)?.state
  if (fromServer && fromServer !== 'idle') return fromServer
  const local = chatStore.sessions.get(sessionId)?.runState
  if (local === 'waiting_approval') return 'needs_you'
  if (local === 'running') return 'working'
  return 'idle'
}

const workspaceSessions = computed(() => {
  const ws = workspaceStore.workspace?.name || ''
  return sessionsStore.sessions.filter((s) => s.workspace === ws && belongsToActiveBot(s))
})

const recentSessions = computed(() => {
  const ws = workspaceStore.workspace?.name || ''
  return sessionsStore.sessions
    .filter((s) => (!s.workspace || s.workspace !== ws) && belongsToActiveBot(s))
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
    .slice(0, 8)
})

const allRecentSessions = computed(() => [...workspaceSessions.value, ...recentSessions.value])

const activeGroupId = computed(() => router.currentRoute.value.params.groupId)

// ── actions ────────────────────────────────────────────────────

async function loadSessions() {
  if (!gatewayService.isConnected()) return
  await sessionsStore.fetchSessions()
}

function toggleFilter() {
  filtering.value = !filtering.value
  if (filtering.value) {
    nextTick(() => filterInput.value?.focus())
  } else {
    query.value = ''
  }
}

function handleGoHome() {
  router.push({ name: 'chat-home' })
}

function selectBot(bot: Bot) {
  botsStore.selectBot(bot.id)
  sessionsStore.clearCurrentSession()
  router.push({ name: 'chat-home' })
}

function selectGroup(group: Group) {
  router.push({ name: 'group', params: { groupId: group.id } })
}

async function handleNewSession() {
  if (creating.value) return
  creating.value = true
  try {
    const ws = workspaceStore.workspace?.name || ''
    const session = await sessionsStore.createSession('新对话', '', ws, botsStore.activeBotId ?? '')
    if (session) router.push({ name: 'chat-session', params: { sessionId: session.id } })
  } finally {
    creating.value = false
    menuOpen.value = false
  }
}

function openBotEditor(bot: Bot | null) {
  menuOpen.value = false
  emit('editBot', bot)
}

function openGroupEditor(group: Group | null) {
  menuOpen.value = false
  editingGroup.value = group
  groupEditorOpen.value = true
}

function closeGroupEditor() {
  groupEditorOpen.value = false
  editingGroup.value = null
}

async function go(to: string) {
  menuOpen.value = false
  await router.push(to)
}

// ── session context menu ───────────────────────────────────────

const contextMenu = ref<{ show: boolean; x: number; y: number; sessionId: string | null }>({
  show: false,
  x: 0,
  y: 0,
  sessionId: null,
})

function openContextMenu(sessionId: string, event: MouseEvent) {
  if (editingId.value) return
  event.preventDefault()
  event.stopPropagation()
  contextMenu.value = { show: true, x: event.clientX, y: event.clientY, sessionId }
}

function closeContextMenu() {
  contextMenu.value.show = false
  contextMenu.value.sessionId = null
}

function getSessionById(id: string | null) {
  if (!id) return null
  return sessionsStore.sessions.find((s) => s.id === id) ?? null
}

async function handleMenuRename(event: MouseEvent) {
  event.stopPropagation()
  const session = getSessionById(contextMenu.value.sessionId)
  closeContextMenu()
  if (session) await startRename(session, event)
}

async function handleMenuDelete(event: MouseEvent) {
  event.stopPropagation()
  const id = contextMenu.value.sessionId
  closeContextMenu()
  if (!id) return
  const isCurrent = sessionsStore.currentSessionId === id
  await sessionsStore.deleteSession(id)
  if (isCurrent) router.push({ name: 'chat-home' })
}

async function startRename(session: { id: string; title: string }, event: MouseEvent) {
  event.stopPropagation()
  editingId.value = session.id
  editingTitle.value = session.title || ''
  await nextTick()
  const el = Array.isArray(renameInputRef.value)
    ? (renameInputRef.value[0] as HTMLInputElement | undefined)
    : renameInputRef.value
  el?.focus()
}

function cancelRename() {
  editingId.value = null
  editingTitle.value = ''
}

async function commitRename(sessionId: string) {
  const title = editingTitle.value.trim()
  if (title) await sessionsStore.updateSession(sessionId, title)
  editingId.value = null
  editingTitle.value = ''
}

function handleRenameKeydown(sessionId: string, event: KeyboardEvent) {
  if (event.key === 'Enter') {
    event.preventDefault()
    commitRename(sessionId)
  } else if (event.key === 'Escape') {
    cancelRename()
  }
}

function handleGlobalClick() {
  closeContextMenu()
  menuOpen.value = false
}

onMounted(() => {
  loadSessions()
  connected.value = gatewayService.isConnected()
  unsubscribeOpen = gatewayService.on('open', () => {
    connected.value = true
    sessionsStore.fetchSessions()
  })
  unsubscribeClose = gatewayService.on('close', () => {
    connected.value = false
  })
  window.addEventListener('click', handleGlobalClick)
})

onUnmounted(() => {
  unsubscribeOpen?.()
  unsubscribeClose?.()
  window.removeEventListener('click', handleGlobalClick)
})
</script>

<template>
  <aside class="flex h-full flex-col bg-[var(--color-sidebar-bg)]">
    <!-- 品牌行 -->
    <div class="flex items-center gap-1 px-3 pb-1 pt-3">
      <button
        type="button"
        class="truncate text-[15px] font-semibold tracking-tight text-[var(--color-text-strong)]"
        @click="handleGoHome"
      >
        小巧
      </button>
      <div class="flex-1" />
      <button
        type="button"
        class="flex h-8 w-8 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-text-muted)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
        aria-label="搜索"
        title="搜索"
        @click.stop="toggleFilter"
      >
        <Search class="h-4 w-4" />
      </button>
      <button
        type="button"
        class="flex h-8 w-8 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-text-muted)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
        aria-label="新建对话"
        title="新建对话"
        @click.stop="handleNewSession"
      >
        <Plus class="h-4 w-4" />
      </button>
      <div class="relative">
        <button
          type="button"
          class="flex h-8 w-8 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-text-muted)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
          aria-label="更多"
          aria-haspopup="menu"
          :aria-expanded="menuOpen"
          @click.stop="menuOpen = !menuOpen"
        >
          <Ellipsis class="h-4 w-4" />
        </button>
        <div
          v-if="menuOpen"
          class="absolute right-0 top-9 z-40 w-44 rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-overlay)] py-1 shadow-[var(--shadow-menu)]"
          role="menu"
          @click.stop
        >
          <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition hover:bg-[var(--color-hover)]" @click="openBotEditor(null)">
            <Plus class="h-3.5 w-3.5" />新建 Bot
          </button>
          <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition hover:bg-[var(--color-hover)]" @click="openGroupEditor(null)">
            <Users class="h-3.5 w-3.5" />新建群聊
          </button>
          <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition hover:bg-[var(--color-hover)]" @click="handleNewSession">
            <Clock class="h-3.5 w-3.5" />新建对话
          </button>
          <div class="my-1 h-[0.5px] bg-[var(--color-line)]" />
          <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition hover:bg-[var(--color-hover)]" @click="go('/toolbox')">
            <Wrench class="h-3.5 w-3.5" />工具箱
          </button>
          <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition hover:bg-[var(--color-hover)]" @click="go('/routines')">
            <CalendarClock class="h-3.5 w-3.5" />定时任务
          </button>
          <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition hover:bg-[var(--color-hover)]" @click="go('/runs')">
            <Activity class="h-3.5 w-3.5" />运行记录
          </button>
          <button type="button" class="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition hover:bg-[var(--color-hover)]" @click="go('/approvals')">
            <ShieldCheck class="h-3.5 w-3.5" />审批
            <span v-if="approvalsStore.pendingCount > 0" class="ml-auto text-[11px] text-[var(--color-warning)]">{{ approvalsStore.pendingCount }}</span>
          </button>
        </div>
      </div>
    </div>

    <div v-if="filtering" class="px-3 pb-1">
      <input
        ref="filterInput"
        v-model="query"
        type="text"
        placeholder="搜索 Bot 或群聊…"
        class="h-8 w-full rounded-[var(--radius-md)] border-[0.5px] border-[var(--color-line-strong)] bg-[var(--color-surface-overlay)] px-2.5 text-[13px] outline-none placeholder:text-[var(--color-text-faint)] focus:border-[var(--color-accent)]"
        @keydown.escape="toggleFilter"
      >
    </div>

    <!-- 主 Bot -->
    <button
      v-if="mainBot"
      type="button"
      class="mx-2.5 mt-2 flex flex-col items-center gap-1.5 rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] px-3 py-3 transition hover:border-[var(--color-line-strong)]"
      :class="botsStore.activeBotId === mainBot.id ? 'shadow-[inset_0_0_0_0.5px_var(--color-line-strong)]' : ''"
      @click="selectBot(mainBot)"
      @dblclick="openBotEditor(mainBot)"
    >
      <span class="text-[32px] leading-none select-none" aria-hidden="true">{{ mainBot.emoji || '🤖' }}</span>
      <span class="flex items-center gap-1">
        <span class="text-[14px] font-medium text-[var(--color-text-strong)]">{{ mainBot.name }}</span>
        <Star class="h-3.5 w-3.5 fill-current text-[var(--color-warning)]" />
      </span>
      <span class="rounded-[var(--radius-sm)] bg-[var(--color-surface)] px-1.5 py-0.5 text-[11px] leading-none text-[var(--color-text-muted)]">
        主 Bot
      </span>
    </button>

    <!-- 群 + Bot -->
    <div class="mt-2 flex-1 overflow-y-auto px-2">
      <div v-if="botsStore.loading || groupsStore.loading" class="px-2 py-3 text-[13px] text-[var(--color-text-faint)]">
        加载中…
      </div>
      <template v-else>
        <EntityRow
          v-for="group in visibleGroups"
          :key="group.id"
          :name="group.name"
          :subtitle="groupSubtitle(group)"
          :member-emojis="group.botIds.map(botEmoji)"
          :state="groupActivity(group)"
          :active="activeGroupId === group.id"
          @select="selectGroup(group)"
          @edit="openGroupEditor(group)"
        />
        <EntityRow
          v-for="bot in visibleBots"
          :key="bot.id"
          :name="bot.name"
          :subtitle="botSubtitle(bot)"
          :emoji="bot.emoji || '🤖'"
          :state="activityStore.stateOf(bot.id)"
          :active="!activeGroupId && botsStore.activeBotId === bot.id"
          @select="selectBot(bot)"
          @edit="openBotEditor(bot)"
        />
        <p
          v-if="visibleGroups.length === 0 && visibleBots.length === 0"
          class="px-2 py-3 text-[13px] text-[var(--color-text-faint)]"
        >
          {{ query ? '没有匹配的结果' : '还没有群聊或 Bot。' }}
        </p>
      </template>

      <!-- 最近对话 -->
      <div v-if="allRecentSessions.length > 0" class="mt-1">
        <button
          type="button"
          class="flex w-full items-center gap-1.5 px-2 py-1.5 text-[11px] font-medium uppercase tracking-wide text-[var(--color-text-faint)] transition hover:text-[var(--color-text-muted)]"
          :aria-expanded="showRecent"
          @click="showRecent = !showRecent"
        >
          <ChevronDown class="h-3 w-3 transition" :class="showRecent ? '' : '-rotate-90'" />
          最近对话
        </button>
        <div v-show="showRecent" class="space-y-0.5">
          <RouterLink
            v-for="session in allRecentSessions"
            :key="session.id"
            :to="{ name: 'chat-session', params: { sessionId: session.id } }"
            class="flex items-center gap-1.5 rounded-[var(--radius-md)] px-2 py-1.5 text-[13px] transition"
            :class="sessionsStore.currentSessionId === session.id
              ? 'bg-[var(--color-selected)] text-[var(--color-text)]'
              : 'text-[var(--color-text-muted)] hover:bg-[var(--color-hover)]'"
            @contextmenu="openContextMenu(session.id, $event)"
          >
            <BotStatusDot v-if="sessionState(session.id) !== 'idle'" :state="sessionState(session.id)" size="sm" />
            <input
              v-if="editingId === session.id"
              ref="renameInputRef"
              v-model="editingTitle"
              type="text"
              class="w-full rounded border-[0.5px] border-[var(--color-line-strong)] bg-[var(--color-surface-overlay)] px-1.5 py-0.5 text-[13px] outline-none"
              @blur="commitRename(session.id)"
              @keydown="handleRenameKeydown(session.id, $event)"
              @click.stop.prevent
            >
            <span v-else class="truncate" @dblclick.prevent="startRename(session, $event)">
              {{ session.title || '未命名会话' }}
            </span>
            <span
              v-if="session.id !== sessionsStore.currentSessionId && isSessionUnread(session)"
              class="ml-auto h-1.5 w-1.5 flex-shrink-0 rounded-full bg-[var(--color-accent)]"
              title="有新进展"
              aria-label="有新进展"
            />
          </RouterLink>
        </div>
      </div>
    </div>

    <!-- 底部：连接状态 + 设置 -->
    <div class="flex items-center gap-2 border-t-[0.5px] border-[var(--color-line)] px-3 py-2">
      <span
        class="flex h-7 w-7 items-center justify-center rounded-[var(--radius-full)] text-[14px]"
        :class="connected ? 'bg-[var(--color-success-soft)]' : 'bg-[var(--color-danger-soft)]'"
        :title="connected ? '引擎已连接' : '未连接引擎'"
        aria-hidden="true"
      >
        {{ mainBot?.emoji || '🤖' }}
      </span>
      <span
        class="flex items-center gap-1.5 text-[12px]"
        :class="connected ? 'text-[var(--color-text-muted)]' : 'text-[var(--color-danger)]'"
      >
        <span
          class="h-1.5 w-1.5 rounded-full"
          :class="connected ? 'bg-[var(--color-success)]' : 'bg-[var(--color-danger)]'"
        />
        {{ connected ? '已连接引擎' : '未连接' }}
      </span>
      <div class="flex-1" />
      <RouterLink
        to="/settings"
        class="flex h-8 items-center gap-1.5 rounded-[var(--radius-sm)] px-2 text-[12px] text-[var(--color-text-muted)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
        title="设置"
      >
        <Settings class="h-3.5 w-3.5" />
        设置
      </RouterLink>
    </div>

    <GroupEditorModal :open="groupEditorOpen" :group="editingGroup" @close="closeGroupEditor" />

    <Teleport to="body">
      <div
        v-if="contextMenu.show"
        class="fixed z-50 min-w-[120px] rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-overlay)] py-1 text-[13px] shadow-[var(--shadow-menu)]"
        :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
      >
        <button type="button" class="w-full px-3 py-2 text-left transition hover:bg-[var(--color-hover)]" @click="handleMenuRename">
          重命名
        </button>
        <button type="button" class="w-full px-3 py-2 text-left text-[var(--color-danger)] transition hover:bg-[var(--color-hover)]" @click="handleMenuDelete">
          删除
        </button>
      </div>
    </Teleport>
  </aside>
</template>
