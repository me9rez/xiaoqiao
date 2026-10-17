<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { useBotsStore } from '@/stores/bots'
import { useMemoryStore } from '@/stores/memory'

const botsStore = useBotsStore()
const memoryStore = useMemoryStore()

const newKey = ref('')
const newValue = ref('')
const newNote = ref('')
const searchQuery = ref('')
const saving = ref(false)

async function reload() {
  const botId = botsStore.activeBotId
  if (botId) await memoryStore.load(botId)
}

async function addFact() {
  const botId = botsStore.activeBotId
  if (!botId || !newKey.value.trim() || !newValue.value.trim()) return
  saving.value = true
  try {
    if (await memoryStore.upsert(botId, newKey.value.trim(), newValue.value.trim())) {
      newKey.value = ''
      newValue.value = ''
    }
  } finally {
    saving.value = false
  }
}

async function removeFact(key: string) {
  const botId = botsStore.activeBotId
  if (!botId) return
  await memoryStore.remove(botId, key)
}

async function addNote() {
  const botId = botsStore.activeBotId
  if (!botId || !newNote.value.trim()) return
  saving.value = true
  try {
    if (await memoryStore.addNote(botId, newNote.value.trim())) newNote.value = ''
  } finally {
    saving.value = false
  }
}

async function runSearch() {
  const botId = botsStore.activeBotId
  if (botId) await memoryStore.search(botId, searchQuery.value)
}

watch(
  () => botsStore.activeBotId,
  () => {
    searchQuery.value = ''
    void reload()
  },
)

onMounted(async () => {
  if (botsStore.bots.length === 0) await botsStore.load()
  await reload()
})
</script>

<template>
  <div class="p-8 max-w-3xl mx-auto">
    <div class="mb-6">
      <h1 class="text-[20px] font-[var(--weight-semibold)] text-[var(--color-text-strong)]">记忆</h1>
      <p class="mt-1 text-[13px] text-[var(--color-text-muted)]">
        当前 Bot：{{ botsStore.activeBot?.name || '未选择' }}。事实会注入 system prompt，记录可被检索。
      </p>
    </div>

    <p v-if="memoryStore.error" class="mb-4 text-[13px] text-[var(--color-danger)]" role="alert">
      {{ memoryStore.error }}
    </p>

    <section class="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)] mb-4">
      <h2 class="text-[14px] font-[var(--weight-medium)] text-[var(--color-text-strong)] mb-3">事实</h2>

      <div v-if="memoryStore.loading" class="text-[13px] text-[var(--color-text-muted)]">加载中…</div>
      <div v-else-if="memoryStore.facts.length === 0" class="text-[13px] text-[var(--color-text-muted)]">
        还没有记忆。加一条“称呼：叫我老王”试试。
      </div>

      <ul v-else class="space-y-1.5">
        <li
          v-for="fact in memoryStore.facts"
          :key="fact.id"
          class="flex items-start gap-3 px-2.5 py-2 rounded-[var(--radius-md)] hover:bg-[var(--color-hover)]"
        >
          <span class="text-[13px] text-[var(--color-text-muted)] min-w-20 shrink-0">{{ fact.key }}</span>
          <span class="text-[13px] text-[var(--color-text)] flex-1 break-words">{{ fact.value }}</span>
          <button
            type="button"
            class="text-[12px] text-[var(--color-text-faint)] hover:text-[var(--color-danger)]"
            @click="removeFact(fact.key)"
          >
            删除
          </button>
        </li>
      </ul>

      <div class="mt-3 flex items-center gap-2">
        <input
          v-model="newKey"
          type="text"
          class="w-32 h-[34px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[13px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
          placeholder="键，如 称呼"
        >
        <input
          v-model="newValue"
          type="text"
          class="flex-1 h-[34px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[13px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
          placeholder="值，如 叫我老王"
          @keydown.enter.prevent="addFact"
        >
        <button
          type="button"
          class="h-[34px] px-3 rounded-[var(--radius-md)] text-[13px] font-[var(--weight-medium)] text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
          :disabled="saving || !newKey.trim() || !newValue.trim()"
          @click="addFact"
        >
          添加
        </button>
      </div>
    </section>

    <section class="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]">
      <div class="flex items-center gap-2 mb-3">
        <h2 class="text-[14px] font-[var(--weight-medium)] text-[var(--color-text-strong)]">记录</h2>
        <span class="flex-1" />
        <input
          v-model="searchQuery"
          type="search"
          class="w-48 h-[30px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[12px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
          placeholder="搜索记录…"
          @keydown.enter.prevent="runSearch"
        >
      </div>

      <ul v-if="searchQuery.trim() && memoryStore.results.length > 0" class="space-y-1.5 mb-3">
        <li v-for="note in memoryStore.results" :key="note.id" class="text-[13px] text-[var(--color-text)] px-2.5 py-1.5 rounded-[var(--radius-md)] bg-[var(--color-selected)]">
          {{ note.text }}
        </li>
      </ul>

      <div v-if="memoryStore.notes.length === 0" class="text-[13px] text-[var(--color-text-muted)]">还没有记录。</div>
      <ul v-else class="space-y-1.5">
        <li v-for="note in memoryStore.notes" :key="note.id" class="text-[13px] text-[var(--color-text)] leading-relaxed">
          · {{ note.text }}
        </li>
      </ul>

      <div class="mt-3 flex items-center gap-2">
        <input
          v-model="newNote"
          type="text"
          class="flex-1 h-[34px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[13px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
          placeholder="记一条，比如：周六要交周报"
          @keydown.enter.prevent="addNote"
        >
        <button
          type="button"
          class="h-[34px] px-3 rounded-[var(--radius-md)] text-[13px] font-[var(--weight-medium)] text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
          :disabled="saving || !newNote.trim()"
          @click="addNote"
        >
          记录
        </button>
      </div>
    </section>
  </div>
</template>
