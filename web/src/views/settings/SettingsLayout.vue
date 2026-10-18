<script setup lang="ts">
import {
  BarChart3,
  Bot,
  Brain,
  CalendarClock,
  Flag,
  Heart,
  Info,
  LayoutGrid,
  Monitor,
  Shield,
  SlidersHorizontal,
  Wrench,
  X,
} from '@lucide/vue'
import { onMounted, onUnmounted } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

const router = useRouter()
const route = useRoute()

/**
 * Settings is an overlay, not a page: the reference opens it as a dialog over the
 * app and closes with ✕, so the routes below only describe the content pane.
 */
const menuItems = [
  { name: 'settings-preferences', label: '通用', icon: SlidersHorizontal, to: '/settings/preferences' },
  { name: 'settings-models', label: '模型', icon: Bot, to: '/settings/models' },
  { name: 'settings-channels', label: '频道', icon: LayoutGrid, to: '/settings/channels' },
  { name: 'settings-memory', label: '记忆', icon: Brain, to: '/settings/memory' },
  { name: 'settings-personality', label: '性格', icon: Heart, to: '/settings/personality' },
  { name: 'settings-security', label: '安全', icon: Shield, to: '/settings/security' },
  { name: 'settings-usage', label: '用量', icon: BarChart3, to: '/settings/usage' },
  { name: 'settings-diagnostics', label: '诊断', icon: Monitor, to: '/settings/diagnostics' },
  { name: 'settings-feedback', label: '反馈', icon: Flag, to: '/settings/feedback' },
  { name: 'settings-version', label: '版本', icon: Info, to: '/settings/version' },
]

/** Pages that live outside the dialog but belong in the same nav, like the reference. */
const outsideItems = [
  { label: '定时任务', icon: CalendarClock, to: '/routines' },
  { label: '工具箱', icon: Wrench, to: '/toolbox' },
]

function close() {
  if (window.history.length > 1) router.back()
  else void router.push('/')
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4 sm:p-8">
    <div
      role="dialog"
      aria-modal="true"
      aria-label="系统设置"
      class="flex h-full max-h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-[var(--radius-xl)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] shadow-[var(--shadow-menu)] sm:flex-row"
    >
      <!-- 左栏 -->
      <aside class="flex w-full flex-shrink-0 flex-col border-b-[0.5px] border-[var(--color-line)] bg-[var(--color-surface)] p-3 sm:w-52 sm:border-b-0 sm:border-r-[0.5px]">
        <nav class="space-y-0.5 overflow-y-auto">
          <RouterLink
            v-for="item in menuItems"
            :key="item.name"
            :to="item.to"
            class="flex items-center gap-2.5 rounded-[var(--radius-md)] px-3 py-2 text-[13px] transition"
            :class="route.name === item.name
              ? 'bg-[var(--color-surface-raised)] font-medium text-[var(--color-text)] shadow-[var(--shadow-xs)]'
              : 'text-[var(--color-text-muted)] hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]'"
          >
            <component :is="item.icon" class="h-4 w-4" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </nav>

        <div class="mt-3 border-t-[0.5px] border-[var(--color-line)] pt-3">
          <button
            v-for="item in outsideItems"
            :key="item.to"
            type="button"
            class="flex w-full items-center gap-2.5 rounded-[var(--radius-md)] px-3 py-2 text-[13px] text-[var(--color-text-muted)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
            @click="router.push(item.to)"
          >
            <component :is="item.icon" class="h-4 w-4" />
            <span>{{ item.label }}</span>
          </button>
        </div>
      </aside>

      <!-- 内容 -->
      <div class="flex min-w-0 flex-1 flex-col">
        <header class="flex h-12 flex-shrink-0 items-center justify-between border-b-[0.5px] border-[var(--color-line)] px-4">
          <span class="text-[13px] font-medium text-[var(--color-text-strong)]">
            {{ menuItems.find((item) => item.name === route.name)?.label || '设置' }}
          </span>
          <button
            type="button"
            class="flex h-8 w-8 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-text-muted)] transition hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]"
            aria-label="关闭设置"
            @click="close"
          >
            <X class="h-4 w-4" />
          </button>
        </header>
        <main class="flex-1 overflow-y-auto bg-[var(--color-bg)]">
          <RouterView />
        </main>
      </div>
    </div>
  </div>
</template>
