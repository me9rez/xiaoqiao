<script setup lang="ts">
import { BookOpen, CalendarClock, ChevronDown, ExternalLink, Folder, FolderOpen, History, List, Package, Wrench } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import ModelPicker from '@/components/chat/ModelPicker.vue'
import { useArtifactsStore } from '@/stores/artifacts'
import { useBotsStore } from '@/stores/bots'
import { useChatStore } from '@/stores/chat'
import { useMemoryStore } from '@/stores/memory'
import { useRoutinesStore } from '@/stores/routines'
import { useSettingsStore } from '@/stores/settings'
import { useUsageStore } from '@/stores/usage'
import { useWorkspaceStore } from '@/stores/workspace'

const chatStore = useChatStore()
const workspaceStore = useWorkspaceStore()
const artifactsStore = useArtifactsStore()
const botsStore = useBotsStore()
const settingsStore = useSettingsStore()
const memoryStore = useMemoryStore()
const usageStore = useUsageStore()
const routinesStore = useRoutinesStore()
const router = useRouter()

const progressExpanded = ref(true)
const workspaceExpanded = ref(true)
const artifactsExpanded = ref(true)
const opsExpanded = ref(true)

const bot = computed(() => botsStore.activeBot)
const isMainBot = computed(() => Boolean(bot.value && botsStore.bots[0]?.id === bot.value.id))
/** The bot's own model wins; older bots fall back to `default_model`. */
const botModel = computed(() => bot.value?.model || settingsStore.settings.default_model)

const memoryCount = computed(() => memoryStore.facts.length + memoryStore.notes.length)
const usageTotals = computed(() => usageStore.summary?.window)
const botRoutines = computed(() => routinesStore.routines.filter((routine) => routine.botId === bot.value?.id))

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`
  return String(value)
}

async function loadBotPanels(botId: string | undefined): Promise<void> {
  if (!botId) return
  await Promise.all([
    memoryStore.load(botId),
    usageStore.load(1, botId),
    routinesStore.routines.length === 0 ? routinesStore.load() : Promise.resolve(),
  ])
}

async function onModelChange(alias: string): Promise<void> {
  if (!alias || !bot.value) return
  await botsStore.update(bot.value.id, { model: alias })
  await settingsStore.setDefaultModel(alias)
}

function go(to: string): void {
  void router.push(to)
}

onMounted(() => {
  artifactsStore.listen()
  if (botsStore.activeBotId) {
    void artifactsStore.load(botsStore.activeBotId)
    void loadBotPanels(botsStore.activeBotId)
  }
})

watch(
  () => botsStore.activeBotId,
  (botId) => {
    if (botId) {
      void artifactsStore.load(botId)
      void loadBotPanels(botId)
    }
  },
)

function formatSize(size: number | null): string {
  if (!size) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

const recentOps = computed(() => {
  return chatStore.messages
    .filter((m) => m.role === 'tool' && (m.toolCall?.name || m.toolExecution?.name))
    .slice(-5)
    .map((m) => ({
      name: m.toolCall?.name || m.toolExecution?.name || '',
      ok: m.toolExecution?.finished === true ? m.toolExecution.ok : undefined,
    }))
})

const toolUsage = computed(() => {
  const counts: Record<string, number> = {}
  for (const m of chatStore.messages) {
    if (m.role === 'tool') {
      const name = m.toolCall?.name || m.toolExecution?.name || ''
      if (name) counts[name] = (counts[name] || 0) + 1
    }
  }
  return Object.entries(counts).map(([name, count]) => ({ name, count }))
})
</script>

<template>
  <aside class="h-full w-72 flex-shrink-0 border-l border-[var(--color-line)] bg-[var(--color-bg)] flex flex-col overflow-y-auto">
    <!-- Bot 详情 -->
    <div v-if="bot" class="border-b-[0.5px] border-[var(--color-line)] px-4 pb-3 pt-5">
      <div class="flex flex-col items-center gap-1">
        <span class="text-[36px] leading-none select-none" aria-hidden="true">{{ bot.emoji || '🤖' }}</span>
        <span class="mt-1 text-[15px] font-medium text-[var(--color-text-strong)]">{{ bot.name }}</span>
        <span class="text-[12px] text-[var(--color-text-faint)]">{{ isMainBot ? '主 Bot' : (bot.model || '未指定模型') }}</span>
      </div>

      <div class="mt-3 space-y-2">
        <!-- 模型 -->
        <div>
          <p class="mb-1 text-[12px] text-[var(--color-text-muted)]">模型</p>
          <ModelPicker :value="botModel" @change="onModelChange" />
        </div>

        <!-- 记忆 -->
        <button
          type="button"
          class="flex w-full items-center gap-2 rounded-[var(--radius-md)] border-[0.5px] border-[var(--color-line)] px-3 py-2 text-[13px] text-[var(--color-text)] transition hover:bg-[var(--color-hover)]"
          @click="go('/settings/memory')"
        >
          <BookOpen class="h-3.5 w-3.5 text-[var(--color-text-muted)]" />
          <span>记忆</span>
          <span class="ml-auto text-[12px] text-[var(--color-text-muted)]">{{ memoryCount }} 条</span>
          <span class="text-[12px] text-[var(--color-text-faint)]">管理 ›</span>
        </button>

        <!-- 用量 -->
        <div class="flex items-center gap-2 rounded-[var(--radius-md)] border-[0.5px] border-[var(--color-line)] px-3 py-2 text-[13px]">
          <span class="text-[var(--color-text)]">用量</span>
          <span v-if="usageTotals" class="ml-auto text-[12px] text-[var(--color-text-muted)]">
            {{ formatTokens(usageTotals.totalTokens) }} tok · {{ usageTotals.runs }} 次
          </span>
          <span v-else class="ml-auto text-[12px] text-[var(--color-text-faint)]">暂无</span>
        </div>

        <!-- 定时任务 -->
        <button
          type="button"
          class="flex w-full items-center gap-2 rounded-[var(--radius-md)] border-[0.5px] border-[var(--color-line)] px-3 py-2 text-[13px] text-[var(--color-text)] transition hover:bg-[var(--color-hover)]"
          @click="go('/routines')"
        >
          <CalendarClock class="h-3.5 w-3.5 text-[var(--color-text-muted)]" />
          <span>定时任务</span>
          <span class="ml-auto text-[12px] text-[var(--color-text-muted)]">
            {{ botRoutines.length ? `${botRoutines.length} 个` : '去添加 ›' }}
          </span>
        </button>
      </div>
    </div>

    <!-- 进度 -->
    <div class="border-b border-[var(--border)]">
      <button
        class="w-full flex items-center justify-between px-4 py-3 hover:bg-[var(--bg-muted)] transition"
        @click="progressExpanded = !progressExpanded"
      >
        <div class="flex items-center gap-2 text-sm font-medium">
          <List class="w-4 h-4 text-[var(--text-muted)]" />
          <span>进度</span>
        </div>
        <ChevronDown class="w-4 h-4 text-[var(--text-muted)] transition-transform" :class="progressExpanded ? '' : '-rotate-90'" />
      </button>
      <div v-show="progressExpanded" class="px-4 pb-4">
        <div class="flex items-center justify-center gap-1 py-6">
          <div class="w-3 h-3 rounded-full border-2 border-[var(--text-subtle)]" />
          <div class="w-8 h-px bg-[var(--text-subtle)]" />
          <div class="w-3 h-3 rounded-full border-2 border-[var(--text-subtle)]" />
          <div class="w-8 h-px bg-[var(--text-subtle)]" />
          <div class="w-3 h-3 rounded-full border-2 border-[var(--text-subtle)]" />
          <div class="w-8 h-px bg-[var(--text-subtle)]" />
          <div class="w-3 h-3 rounded-full border-2 border-[var(--text-subtle)]" />
        </div>
        <p class="text-center text-xs text-[var(--text-subtle)]">
          任务执行进度将显示在这里
        </p>
      </div>
    </div>

    <!-- 工作区 -->
    <div class="border-b border-[var(--border)]">
      <button
        class="w-full flex items-center justify-between px-4 py-3 hover:bg-[var(--bg-muted)] transition"
        @click="workspaceExpanded = !workspaceExpanded"
      >
        <div class="flex items-center gap-2 text-sm font-medium">
          <Folder class="w-4 h-4 text-[var(--text-muted)]" />
          <span>工作区</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-[#d9896d]/10 text-[#d9896d] font-medium">
            {{ workspaceStore.workspace?.name || '-' }}
          </span>
        </div>
        <div class="flex items-center gap-1">
          <ExternalLink class="w-3.5 h-3.5 text-[var(--text-muted)]" />
          <ChevronDown class="w-4 h-4 text-[var(--text-muted)] transition-transform" :class="workspaceExpanded ? '' : '-rotate-90'" />
        </div>
      </button>
      <div v-show="workspaceExpanded" class="px-4 pb-4 space-y-2">
        <div class="rounded-xl bg-[var(--bg-card)] border border-[var(--border)] p-3 flex items-center gap-2.5">
          <div class="w-9 h-9 rounded-lg bg-orange-50 flex items-center justify-center flex-shrink-0">
            <FolderOpen class="w-5 h-5 text-orange-400" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-sm font-medium truncate">
              {{ workspaceStore.workspace?.name || '未获取到工作区' }}
            </div>
            <div class="text-xs text-[var(--text-subtle)] truncate">
              {{ workspaceStore.workspace?.path || '' }}
            </div>
          </div>
          <ChevronDown class="w-4 h-4 text-[var(--text-muted)] flex-shrink-0" />
        </div>

        <button class="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition">
          <span class="text-[var(--text-subtle)]">📋</span>
          <span>项目指令 · 点击添加</span>
        </button>

        <button class="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition">
          <span class="text-[var(--text-subtle)]">🧠</span>
          <span>项目记忆 · 暂无</span>
        </button>
      </div>
    </div>

    <!-- 产物 -->
    <div class="border-b border-[var(--color-line)]">
      <button
        class="w-full flex items-center justify-between px-4 py-3 hover:bg-[var(--color-hover)] transition"
        @click="artifactsExpanded = !artifactsExpanded"
      >
        <div class="flex items-center gap-2 text-sm font-medium">
          <Package class="w-4 h-4 text-[var(--color-text-muted)]" />
          <span>产物</span>
          <span v-if="artifactsStore.items.length" class="text-xs text-[var(--color-text-muted)]">
            {{ artifactsStore.items.length }}
          </span>
        </div>
        <ChevronDown
          class="w-4 h-4 text-[var(--color-text-muted)] transition-transform"
          :class="artifactsExpanded ? '' : '-rotate-90'"
        />
      </button>
      <div v-show="artifactsExpanded" class="px-4 pb-4 space-y-1.5">
        <div v-if="artifactsStore.items.length === 0" class="text-[13px] text-[var(--color-text-muted)]">
          这个 Bot 还没有产出文件
        </div>
        <div
          v-for="artifact in artifactsStore.items.slice(0, 6)"
          :key="artifact.id"
          class="flex items-center gap-2 px-2.5 py-2 rounded-[var(--radius-md)] bg-[var(--color-surface)]"
          :title="artifact.path"
        >
          <span class="text-[12px] text-[var(--color-text)] truncate flex-1">{{ artifact.path }}</span>
          <span class="text-[11px] text-[var(--color-text-faint)] shrink-0">{{ formatSize(artifact.size) }}</span>
        </div>
      </div>
    </div>

    <!-- 操作记录 -->
    <div>
      <button
        class="w-full flex items-center justify-between px-4 py-3 hover:bg-[var(--bg-muted)] transition"
        @click="opsExpanded = !opsExpanded"
      >
        <div class="flex items-center gap-2 text-sm font-medium">
          <History class="w-4 h-4 text-[var(--text-muted)]" />
          <span>操作记录</span>
          <span v-if="recentOps.length" class="text-xs text-[var(--text-muted)]">{{ recentOps.length }} ops</span>
        </div>
        <ChevronDown class="w-4 h-4 text-[var(--text-muted)] transition-transform" :class="opsExpanded ? '' : '-rotate-90'" />
      </button>
      <div v-show="opsExpanded" class="px-4 pb-4">
        <div v-if="toolUsage.length" class="space-y-2">
          <div class="text-xs text-[var(--text-muted)] px-1">工具使用</div>
          <div
            v-for="op in toolUsage"
            :key="op.name"
            class="flex items-center gap-2 text-sm px-3 py-2 rounded-lg bg-[var(--bg-card)] border border-[var(--border)]"
          >
            <Wrench class="w-3.5 h-3.5 text-[var(--text-subtle)]" />
            <span class="truncate">{{ op.name }}</span>
            <span class="ml-auto text-xs text-[var(--text-subtle)]">x{{ op.count }}</span>
          </div>
        </div>
        <div v-else class="text-sm text-[var(--text-muted)] px-1">
          暂无操作记录
        </div>
      </div>
    </div>
  </aside>
</template>
