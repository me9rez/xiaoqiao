<script setup lang="ts">
import { ArrowLeft, Zap } from '@lucide/vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

const router = useRouter()
const route = useRoute()

const menuItems = [
  { name: 'automation-listeners', label: '监听事件', icon: Zap, to: '/automation/listeners' },
]

function goBack() {
  router.push('/')
}
</script>

<template>
  <div class="h-full flex flex-col bg-[var(--bg-page)] text-[var(--text)]">
    <header class="h-14 flex items-center px-5 border-b border-[var(--border)] bg-[var(--bg-page)] flex-shrink-0">
      <button
        class="flex items-center gap-2 text-sm text-[var(--text-muted)] hover:text-[var(--text)] transition"
        @click="goBack"
      >
        <ArrowLeft class="w-4 h-4" />
        <span>自动化</span>
      </button>
    </header>

    <div class="flex-1 flex min-h-0">
      <aside class="w-60 flex-shrink-0 border-r border-[var(--border)] bg-[var(--bg-page)] overflow-y-auto">
        <nav class="p-3 space-y-1">
          <RouterLink
            v-for="item in menuItems"
            :key="item.name"
            :to="item.to"
            class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition"
            :class="{
              'bg-[var(--bg-card)] border border-[var(--border)] shadow-[var(--shadow)] text-[var(--text)] font-medium': route.name === item.name,
              'text-[var(--text-muted)] hover:bg-[var(--bg-muted)]': route.name !== item.name,
            }"
          >
            <component :is="item.icon" class="w-4 h-4" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </nav>
      </aside>

      <main class="flex-1 overflow-y-auto bg-[var(--bg-page)]">
        <RouterView />
      </main>
    </div>
  </div>
</template>
