<script setup lang="ts">
import {
  Activity,
  CalendarClock,
  ChevronDown,
  Clock,
  Folder,
  FolderOpen,
  Layout,
  HelpCircle,
  Plus,
  Settings,
  ShieldCheck,
  Upload,
  User,
  Wrench,
  Zap,
} from '@lucide/vue'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import BotStatusDot from '@/components/bots/BotStatusDot.vue'
import GroupEditorModal from '@/components/groups/GroupEditorModal.vue'
import GroupList from '@/components/groups/GroupList.vue'
import { gatewayService } from '@/services/gateway'
import { useActivityStore } from '@/stores/activity'
import { useApprovalsStore } from '@/stores/approvals'
import { useBotsStore } from '@/stores/bots'
import { useChatStore } from '@/stores/chat'
import { useSessionsStore } from '@/stores/sessions'
import { useWorkspaceStore } from '@/stores/workspace'
import type { Group } from '@/types/group'

const chatStore = useChatStore()
const sessionsStore = useSessionsStore()
const botsStore = useBotsStore()
const approvalsStore = useApprovalsStore()
const activityStore = useActivityStore()
const workspaceStore = useWorkspaceStore()

const firstBotId = computed(() => botsStore.bots[0]?.id ?? '')

/** Sessions belong to a bot; legacy rows without botId fall under the first bot. */
function belongsToActiveBot(session: { botId?: string }): boolean {
  const active = botsStore.activeBotId
  if (!active) return true
  return session.botId ? session.botId === active : firstBotId.value === active
}
const router = useRouter()

function sessionState(sessionId: string): 'idle' | 'working' | 'needs_you' | 'error' {
  const fromServer = activityStore.entryForSession(sessionId)?.state
  if (fromServer && fromServer !== 'idle') return fromServer
  const local = chatStore.sessions.get(sessionId)?.runState
  if (local === 'waiting_approval') return 'needs_you'
  if (local === 'running') return 'working'
  return 'idle'
}

let unsubscribe: (() => void) | null = null

const editingId = ref<string | null>(null)
const editingTitle = ref('')
const renameInputRef = ref<HTMLInputElement | null>(null)
const creating = ref(false)
const projectExpanded = ref(true)
const groupEditorOpen = ref(false)
const editingGroup = ref<Group | null>(null)

function openGroupEditor(group: Group | null) {
  editingGroup.value = group
  groupEditorOpen.value = true
}

function closeGroupEditor() {
  groupEditorOpen.value = false
  editingGroup.value = null
}

const contextMenu = ref<{
  show: boolean
  x: number
  y: number
  sessionId: string | null
}>({ show: false, x: 0, y: 0, sessionId: null })

async function loadSessions() {
  if (!gatewayService.isConnected()) return
  await sessionsStore.fetchSessions()
}

onMounted(() => {
  loadSessions()
  unsubscribe = gatewayService.on('open', () => {
    sessionsStore.fetchSessions()
  })
  window.addEventListener('click', closeContextMenu)
})

onUnmounted(() => {
  unsubscribe?.()
  window.removeEventListener('click', closeContextMenu)
})

const workspaceSessions = computed(() => {
  const ws = workspaceStore.workspace?.name || ''
  return sessionsStore.sessions.filter((s) => s.workspace === ws && belongsToActiveBot(s))
})

const recentSessions = computed(() => {
  const ws = workspaceStore.workspace?.name || ''
  return sessionsStore.sessions
    .filter((s) => (!s.workspace || s.workspace !== ws) && belongsToActiveBot(s))
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
})

function handleGoHome() {
  router.push({ name: 'chat-home' })
}

async function handleNewSessionInProject() {
  if (creating.value) return
  creating.value = true
  try {
    const ws = workspaceStore.workspace?.name || ''
    const session = await sessionsStore.createSession('新对话', '', ws, botsStore.activeBotId ?? '')
    if (session) {
      router.push({ name: 'chat-session', params: { sessionId: session.id } })
    }
  } finally {
    creating.value = false
  }
}

function openContextMenu(sessionId: string, event: MouseEvent) {
  if (editingId.value) return
  event.preventDefault()
  event.stopPropagation()
  contextMenu.value = {
    show: true,
    x: event.clientX,
    y: event.clientY,
    sessionId,
  }
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
  if (session) {
    await startRename(session, event)
  }
}

async function handleMenuDelete(event: MouseEvent) {
  event.stopPropagation()
  const id = contextMenu.value.sessionId
  closeContextMenu()
  if (id) {
    const isCurrent = sessionsStore.currentSessionId === id
    await sessionsStore.deleteSession(id)
    if (isCurrent) {
      router.push({ name: 'chat-home' })
    }
  }
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
  if (title) {
    await sessionsStore.updateSession(sessionId, title)
  }
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
</script>

<template>
  <aside class="h-full flex flex-col bg-[var(--bg-page)]">
    <div class="p-3">
      <button
        class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] text-sm font-medium hover:bg-[var(--bg-muted)] transition shadow-[var(--shadow)]"
        @click="handleGoHome"
      >
        <Plus class="w-4 h-4" />
        <span>新建任务</span>
      </button>
    </div>

    <nav class="px-3 space-y-1">
      <RouterLink
        to="/toolbox"
        class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition"
      >
        <Wrench class="w-4 h-4" />
        <span>工具箱</span>
      </RouterLink>
      <RouterLink to="/automation" class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition">
        <Zap class="w-4 h-4" />
        <span>自动化</span>
      </RouterLink>
      <RouterLink
        to="/routines"
        class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition"
      >
        <CalendarClock class="w-4 h-4" />
        <span>定时任务</span>
      </RouterLink>
      <RouterLink
        to="/runs"
        class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition"
      >
        <Activity class="w-4 h-4" />
        <span>运行记录</span>
      </RouterLink>
      <RouterLink
        to="/approvals"
        class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition"
      >
        <ShieldCheck class="w-4 h-4" />
        <span class="flex-1">审批</span>
        <span
          v-if="approvalsStore.pendingCount > 0"
          class="px-1.5 py-0.5 rounded-full text-[10px] bg-[var(--color-warning-soft)] text-[var(--color-warning)] border border-[var(--color-warning-bd)]"
        >
          {{ approvalsStore.pendingCount }}
        </span>
      </RouterLink>
    </nav>

    <GroupList @create="openGroupEditor(null)" @edit="openGroupEditor" />

    <div class="px-3 py-2">
      <div class="flex items-center gap-1.5 px-2 py-2 text-xs font-bold text-[var(--text-subtle)]">
        <Layout class="w-3.5 h-3.5" />
        <span>项目</span>
      </div>
      <button
        class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition"
        @click="projectExpanded = !projectExpanded"
      >
        <ChevronDown class="w-3.5 h-3.5 transition-transform" :class="projectExpanded ? '' : '-rotate-90'" />
        <Folder class="w-4 h-4" />
        <span class="flex-1 text-left">{{ workspaceStore.workspace?.name || '未指定项目' }}</span>
        <span
          class="p-0.5 rounded hover:bg-[var(--border)] transition"
          title="新建会话"
          @click.stop="handleNewSessionInProject"
        >
          <Plus class="w-3.5 h-3.5" />
        </span>
      </button>
    </div>

    <div v-show="projectExpanded" class="flex-1 overflow-y-auto px-3 pb-2">
      <div class="ml-5 space-y-0.5">
        <div v-if="sessionsStore.loading" class="px-3 py-4 text-sm text-[var(--text-muted)]">
          加载中…
        </div>
        <div
          v-else-if="workspaceSessions.length === 0"
          class="px-3 py-3 text-sm text-[var(--text-muted)]"
        >
          暂无会话
        </div>
        <div
          v-if="sessionsStore.error"
          class="mx-3 mb-2 px-3 py-2 text-xs text-red-600 bg-red-50 rounded-lg border border-red-100"
        >
          {{ sessionsStore.error }}
        </div>
        <template v-else>
          <RouterLink
            v-for="session in workspaceSessions"
            :key="session.id"
            :to="{ name: 'chat-session', params: { sessionId: session.id } }"
            class="group relative flex items-center justify-between px-3 py-1.5 rounded-lg cursor-pointer text-sm transition"
            :class="{
              'bg-[var(--bg-card)] border border-[var(--border)] shadow-[var(--shadow)] text-[var(--text)] font-medium': sessionsStore.currentSessionId === session.id,
              'text-[var(--text-muted)] hover:bg-[var(--bg-muted)]': sessionsStore.currentSessionId !== session.id,
            }"
            @contextmenu="openContextMenu(session.id, $event)"
          >
            <div class="min-w-0 flex-1">
              <div v-if="editingId === session.id" class="w-full">
                <input
                  ref="renameInputRef"
                  v-model="editingTitle"
                  type="text"
                  class="w-full text-sm px-2 py-1 rounded border border-[var(--border)] bg-[var(--bg-card)] outline-none focus:border-[var(--text-muted)]"
                  @blur="commitRename(session.id)"
                  @keydown="handleRenameKeydown(session.id, $event)"
                  @click.stop
                >
              </div>
              <div
                v-else
                class="flex items-center gap-1.5"
                @dblclick="startRename(session, $event)"
              >
                <BotStatusDot v-if="sessionState(session.id) !== 'idle'" :state="sessionState(session.id)" size="sm" />
                <span class="truncate">{{ session.title || '未命名会话' }}</span>
              </div>
            </div>
          </RouterLink>
        </template>
      </div>
    </div>

    <!-- 最近会话 -->
    <div v-if="recentSessions.length > 0" class="px-3 py-2">
      <div class="flex items-center gap-1.5 px-2 py-2 text-xs font-bold text-[var(--text-subtle)]">
        <Clock class="w-3.5 h-3.5" />
        <span>最近</span>
      </div>
      <div class="space-y-0.5">
        <RouterLink
          v-for="session in recentSessions"
          :key="session.id"
          :to="{ name: 'chat-session', params: { sessionId: session.id } }"
          class="group flex items-center px-3 py-1.5 rounded-lg text-sm cursor-pointer transition"
          :class="{
            'bg-[var(--bg-card)] border border-[var(--border)] shadow-[var(--shadow)] text-[var(--text)]': sessionsStore.currentSessionId === session.id,
            'text-[var(--text-muted)] hover:bg-[var(--bg-muted)]': sessionsStore.currentSessionId !== session.id,
          }"
          @contextmenu="openContextMenu(session.id, $event)"
        >
          <div class="flex items-center gap-1.5 min-w-0 flex-1">
            <BotStatusDot v-if="sessionState(session.id) !== 'idle'" :state="sessionState(session.id)" size="sm" />
            <span class="truncate">{{ session.title || '未命名会话' }}</span>
          </div>
        </RouterLink>
      </div>
    </div>

    <div v-show="!projectExpanded" class="flex-1" />

    <div class="p-3 border-t border-[var(--border)] flex items-center justify-between">
      <button class="flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition">
        <User class="w-4 h-4" />
        <span>我</span>
      </button>
      <div class="flex items-center gap-1">
        <button class="p-2 rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition" title="上传">
          <Upload class="w-4 h-4" />
        </button>
        <RouterLink
          to="/settings"
          class="p-2 rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition"
          title="设置"
        >
          <Settings class="w-4 h-4" />
        </RouterLink>
        <button class="p-2 rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition" title="帮助">
          <HelpCircle class="w-4 h-4" />
        </button>
      </div>
    </div>

    <GroupEditorModal :open="groupEditorOpen" :group="editingGroup" @close="closeGroupEditor" />

    <Teleport to="body">
      <div
        v-if="contextMenu.show"
        class="fixed z-50 min-w-[120px] rounded-xl border border-[var(--border)] bg-[var(--bg-card)] shadow-lg py-1 text-sm"
        :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
      >
        <button
          class="w-full text-left px-3 py-2 hover:bg-[var(--bg-muted)] transition"
          @click="handleMenuRename"
        >
          重命名
        </button>
        <button
          class="w-full text-left px-3 py-2 text-red-600 hover:bg-[var(--bg-muted)] transition"
          @click="handleMenuDelete"
        >
          删除
        </button>
      </div>
    </Teleport>
  </aside>
</template>
