<script setup lang="ts">
import {
  Briefcase,
  ChevronDown,
  Clock,
  Database,
  FileText,
  Folder,
  Globe,
  Plus,
  Send,
} from '@lucide/vue'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { gatewayService } from '@/services/gateway'
import { useSessionsStore } from '@/stores/sessions'
import { useWorkspaceStore } from '@/stores/workspace'
import type { ProviderConfig, Settings } from '@/types/session'
import ModelSelector from './ModelSelector.vue'

const emit = defineEmits<{
  send: [text: string, model: string]
  useSuggestion: [text: string, model: string]
}>()

const sessionsStore = useSessionsStore()
const workspaceStore = useWorkspaceStore()
const text = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const settings = ref<Settings | null>(null)
let unsubscribeOpen: (() => void) | null = null

const modelOptions = computed(() => {
  const opts: { value: string; label: string; providerId: string; providerName: string; modelId: string }[] = []
  if (!settings.value) return opts
  for (const [providerId, provider] of Object.entries(settings.value.providers)) {
    for (const model of (provider as ProviderConfig).models) {
      opts.push({
        value: `${providerId}/${model.id}`,
        label: `${providerId} / ${model.name || model.id}`,
        providerId,
        providerName: providerId,
        modelId: model.id,
      })
    }
  }
  return opts
})

const categories = [
  { key: 'office', label: '办公整理', icon: Briefcase },
  { key: 'data', label: '数据处理', icon: Database },
  { key: 'content', label: '内容创作', icon: FileText },
  { key: 'web', label: '网页生成', icon: Globe },
  { key: 'scheduled', label: '定时任务', icon: Clock },
]

const selectedCategory = ref<string | null>(null)

const suggestionsByCategory: Record<string, string[]> = {
  office: [
    '整理桌面文件，按类型分到不同文件夹',
    '列出下载文件夹里超过 100MB 的大文件',
    '把文档文件夹里的文件按年月归档',
    '批量重命名照片，加上拍摄日期前缀',
  ],
  data: [
    '帮我分析这份销售数据并生成图表',
    '从 CSV 文件中提取关键统计信息',
    '将 Excel 数据清洗后导出为新格式',
    '对比两份数据表的差异并生成报告',
  ],
  content: [
    '写一份本周项目进展周报',
    '帮我写一封商务合作邀请邮件',
    '生成一份产品发布会演讲稿',
    '为我的博客写一篇技术文章大纲',
  ],
  web: [
    '生成一个个人介绍网页',
    '做一个待办事项清单的网页应用',
    '创建一个响应式的 Landing Page',
    '搭建一个简单的数据看板页面',
  ],
  scheduled: [
    '每天早上 8 点推送今日科技资讯摘要',
    '每天早上抓取天气预报并推送给我',
    '每隔 2 小时提醒我喝水和休息',
    '每周一早上推送本周热门电影和书籍推荐',
  ],
}

const currentSuggestions = computed(() => {
  if (selectedCategory.value && suggestionsByCategory[selectedCategory.value]) {
    return suggestionsByCategory[selectedCategory.value]
  }
  return [
    '整理桌面文件，按类型分到不同文件夹',
    '帮我分析这份销售数据并生成图表',
    '写一份本周项目进展周报',
    '生成一个个人介绍网页',
    '每天早上 8 点推送今日科技资讯摘要',
    '每天早上抓取天气预报并推送给我',
    '每隔 2 小时提醒我喝水和休息',
    '每周一早上推送本周热门电影和书籍推荐',
  ]
})

async function loadSettings() {
  if (!gatewayService.isConnected()) return
  try {
    const data = await gatewayService.call<Settings>('getSettings')
    settings.value = data
  } catch (err) {
    console.error('Failed to load settings', err)
  }
}

const effectiveModel = computed(() => settings.value?.primaryModel || '')

async function handleModelChange(value: string) {
  if (!value || !settings.value) return
  try {
    await gatewayService.call<Settings>('updateSettings', { primaryModel: value })
    settings.value.primaryModel = value
  } catch (err) {
    console.error('Failed to update model', err)
  }
}

function adjustHeight() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

function handleSend() {
  const value = text.value.trim()
  if (!value) return
  emit('send', value, effectiveModel.value)
  text.value = ''
  nextTick(adjustHeight)
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

function selectCategory(key: string) {
  selectedCategory.value = selectedCategory.value === key ? null : key
}

function useSuggestion(suggestion: string) {
  text.value = suggestion
  nextTick(adjustHeight)
  textareaRef.value?.focus()
}

async function handleNewChat() {
  await sessionsStore.createSession('新对话')
}

onMounted(() => {
  unsubscribeOpen = gatewayService.on('open', () => {
    loadSettings()
  })
  loadSettings()
})

onUnmounted(() => {
  unsubscribeOpen?.()
})
</script>

<template>
  <div class="flex-1 flex flex-col items-center justify-center px-6 py-8 overflow-y-auto">
    <div class="w-20 h-20 rounded-full bg-[var(--bg-muted)] flex items-center justify-center text-4xl mb-5 shadow-[var(--shadow)]">
      🤖
    </div>

    <h2 class="text-2xl font-semibold mb-2 flex items-center gap-2">
      <span>交给小巧就行啦</span>
      <span class="text-2xl">✨</span>
    </h2>
    <p class="text-sm text-[var(--text-muted)] mb-8">
      嘿～我是你的桌面小伙伴！从今天起啥都交给我吧～
    </p>

    <div class="w-full max-w-2xl mb-5">
      <div class="rounded-3xl bg-[var(--bg-card)] border border-[var(--border)] shadow-[var(--shadow)] px-4 py-4">
        <textarea
          ref="textareaRef"
          v-model="text"
          rows="1"
          placeholder="描述你想定时执行的任务..."
          class="w-full resize-none bg-transparent outline-none text-base max-h-40 mb-3"
          @keydown="handleKeydown"
          @input="adjustHeight"
        />

        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <button class="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition">
              <Folder class="w-4 h-4" />
              <span>{{ workspaceStore.workspace?.name || '添加工作区' }}</span>
              <ChevronDown class="w-3.5 h-3.5" />
            </button>
            <button class="p-1.5 rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition">
              <Plus class="w-4 h-4" />
            </button>
          </div>

          <div class="flex items-center gap-2">
            <ModelSelector
              v-if="settings"
              :options="modelOptions"
              :value="effectiveModel"
              @change="handleModelChange"
            />
            <button
              class="p-2.5 rounded-xl bg-[var(--text)] text-[var(--bg-card)] hover:opacity-90 transition disabled:opacity-40"
              :disabled="!text.trim()"
              @click="handleSend"
            >
              <Send class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="flex flex-wrap items-center justify-center gap-2 mb-8 max-w-2xl">
      <button
        v-for="cat in categories"
        :key="cat.key"
        class="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm border transition"
        :class="selectedCategory === cat.key
          ? 'bg-[var(--text)] text-[var(--bg-card)] border-[var(--text)]'
          : 'bg-[var(--bg-card)] border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--text-subtle)] hover:text-[var(--text)]'"
        @click="selectCategory(cat.key)"
      >
        <component :is="cat.icon" class="w-4 h-4" />
        <span>{{ cat.label }}</span>
      </button>
    </div>

    <div class="w-full max-w-2xl">
      <div class="flex items-center gap-4 mb-4">
        <div class="flex-1 h-px bg-[var(--border)]" />
        <span class="text-xs text-[var(--text-subtle)]">试试这样说</span>
        <div class="flex-1 h-px bg-[var(--border)]" />
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <button
          v-for="(s, idx) in currentSuggestions"
          :key="idx"
          class="text-left px-4 py-3 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] text-sm text-[var(--text-muted)] hover:border-[var(--text-subtle)] hover:text-[var(--text)] transition shadow-[var(--shadow)]"
          @click="useSuggestion(s)"
        >
          "{{ s }}"
        </button>
      </div>
    </div>
  </div>
</template>
