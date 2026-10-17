<script setup lang="ts">
import { Check, Loader2, RefreshCw } from '@lucide/vue'
import { ref } from 'vue'

import pkg from '../../../package.json'

const checking = ref(false)
const upToDate = ref(true)

async function checkUpdate() {
  checking.value = true
  await new Promise((resolve) => setTimeout(resolve, 1200))
  upToDate.value = true
  checking.value = false
}
</script>

<template>
  <div class="p-8 max-w-2xl mx-auto">
    <div class="flex flex-col items-center pt-8 pb-12">
      <div class="w-24 h-24 rounded-full bg-[var(--bg-muted)] flex items-center justify-center text-4xl mb-4 shadow-[var(--shadow)]">
        🤖
      </div>
      <h1 class="text-2xl font-semibold">
        小巧
      </h1>
      <p class="text-sm text-[var(--text-muted)] mt-1">
        交给小巧就行啦
      </p>
    </div>

    <div class="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-[var(--shadow)] mb-4">
      <div class="flex items-center justify-between">
        <span class="text-sm">当前版本</span>
        <span class="text-sm font-medium">v{{ pkg.version }}</span>
      </div>
    </div>

    <div class="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-[var(--shadow)] mb-4">
      <div class="flex items-center gap-2 text-sm text-green-600 mb-4">
        <Check class="w-4 h-4" />
        <span>已是最新版本</span>
      </div>
      <button
        class="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-[var(--border)] text-sm hover:bg-[var(--bg-muted)] transition disabled:opacity-60"
        :disabled="checking"
        @click="checkUpdate"
      >
        <Loader2 v-if="checking" class="w-4 h-4 animate-spin" />
        <RefreshCw v-else class="w-4 h-4" />
        <span>{{ checking ? '检查中…' : '检查更新' }}</span>
      </button>
    </div>

    <div class="text-center text-xs text-[var(--text-subtle)] mt-12 space-y-1">
      <p>Made with ❤ by 小巧 Team</p>
      <p>© {{ new Date().getFullYear() }} 小巧. All rights reserved. · 免责声明</p>
    </div>
  </div>
</template>
