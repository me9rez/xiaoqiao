<script setup lang="ts">
import { ArrowLeft, Copy, Info, Loader2, Pencil, Plus, Square, Trash2, Zap } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useAutomationStore } from '@/stores/automation'
import type { EventListener } from '@/types/automation'

const store = useAutomationStore()

const showModal = ref(false)
const editingListener = ref<EventListener | null>(null)
const saving = ref(false)
const selectedListenerId = ref<string | null>(null)

const selectedListener = computed(() => {
  if (!selectedListenerId.value) return null
  return store.listeners.find((l) => l.id === selectedListenerId.value) ?? null
})

const form = ref({
  name: '',
  description: '',
  triggerType: 'http' as EventListener['triggerType'],
  command: '',
  triggerCondition: 'all' as EventListener['triggerCondition'],
  debounceSeconds: 300,
  debounceEnabled: true,
  quietHours: false,
  pushResult: false,
  skill: '',
  project: '',
  watchPath: '',
  watchEvents: [] as string[],
  fileNamePattern: '',
  intervalSeconds: 60,
  imChannel: '',
  imScope: 'mention' as 'mention' | 'private' | 'all',
  groupId: '',
  senderMatch: '',
})

const triggerTypeOptions: { value: EventListener['triggerType']; label: string }[] = [
  { value: 'http', label: 'HTTP 接收' },
  { value: 'file_change', label: '文件变更' },
  { value: 'scheduled', label: '定时触发' },
  { value: 'im_message', label: 'IM 消息源' },
]

const triggerConditionOptions: { value: EventListener['triggerCondition']; label: string }[] = [
  { value: 'all', label: '所有事件' },
  { value: 'keyword', label: '关键词匹配' },
  { value: 'regex', label: '正则匹配' },
]

const watchEventOptions = [
  { value: 'create', label: '创建' },
  { value: 'modify', label: '修改' },
  { value: 'delete', label: '删除' },
]

const imScopeOptions = [
  { value: 'mention' as const, label: '仅 @小巧 消息' },
  { value: 'private' as const, label: '仅私聊消息' },
  { value: 'all' as const, label: '所有消息' },
]

function triggerTypeLabel(t: string): string {
  return triggerTypeOptions.find((o) => o.value === t)?.label ?? t
}

function triggerConditionLabel(c: string): string {
  return triggerConditionOptions.find((o) => o.value === c)?.label ?? c
}

function toggleWatchEvent(event: string) {
  const idx = form.value.watchEvents.indexOf(event)
  if (idx >= 0) {
    form.value.watchEvents.splice(idx, 1)
  } else {
    form.value.watchEvents.push(event)
  }
}

function resetTriggerFields() {
  form.value.watchPath = ''
  form.value.watchEvents = []
  form.value.fileNamePattern = ''
  form.value.intervalSeconds = 60
  form.value.imChannel = ''
  form.value.imScope = 'mention'
  form.value.groupId = ''
  form.value.senderMatch = ''
}

function openCreate() {
  editingListener.value = null
  form.value = {
    name: '', description: '', triggerType: 'http', command: '',
    triggerCondition: 'all', debounceSeconds: 300, debounceEnabled: true,
    quietHours: false, pushResult: false, skill: '', project: '',
    watchPath: '', watchEvents: [], fileNamePattern: '',
    intervalSeconds: 60, imChannel: '', imScope: 'mention',
    groupId: '', senderMatch: '',
  }
  showModal.value = true
}

function openEditFromDetail() {
  if (!selectedListener.value) return
  const l = selectedListener.value
  editingListener.value = l
  form.value = {
    name: l.name, description: l.description, triggerType: l.triggerType,
    command: l.command, triggerCondition: l.triggerCondition,
    debounceSeconds: l.debounceSeconds, debounceEnabled: l.debounceSeconds > 0,
    quietHours: l.quietHours, pushResult: l.pushResult,
    skill: l.skill, project: l.project,
    watchPath: l.watchPath, watchEvents: [...l.watchEvents],
    fileNamePattern: l.fileNamePattern, intervalSeconds: l.intervalSeconds,
    imChannel: l.imChannel, imScope: l.imScope,
    groupId: l.groupId, senderMatch: l.senderMatch,
  }
  showModal.value = true
}

async function handleSave() {
  saving.value = true
  try {
    const data = {
      ...form.value,
      debounceSeconds: form.value.debounceEnabled ? form.value.debounceSeconds : 0,
    }
    if (editingListener.value) {
      await store.updateListener(editingListener.value.id, data)
    } else {
      await store.createListener(data)
    }
    showModal.value = false
  } finally {
    saving.value = false
  }
}

async function handleDelete(id: string) {
  await store.deleteListener(id)
  if (selectedListenerId.value === id) selectedListenerId.value = null
}

async function handleToggle(listener: EventListener) {
  await store.toggleListener(listener.id, !listener.enabled)
}

function goBack() {
  selectedListenerId.value = null
}

function copyUrl() {
  navigator.clipboard.writeText(`POST http://localhost:18080/trigger/${selectedListenerId.value}`)
}

onMounted(() => {
  store.fetchListeners()
})
</script>

<template>
  <div class="p-8 max-w-4xl mx-auto">
    <!-- ===== Detail View ===== -->
    <template v-if="selectedListener">
      <div class="flex items-center justify-between mb-6">
        <div class="flex items-center gap-3">
          <button class="p-1.5 rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition" @click="goBack">
            <ArrowLeft class="w-5 h-5" />
          </button>
          <h1 class="text-xl font-semibold">{{ selectedListener.name || '未命名监听' }}</h1>
        </div>
        <button class="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition" @click="openEditFromDetail">
          <Pencil class="w-4 h-4" />
          <span>编辑</span>
        </button>
      </div>

      <!-- 状态信息卡片 -->
      <div class="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-[var(--shadow)] mb-4">
        <div class="flex items-center justify-between py-2 border-b border-[var(--border)]">
          <span class="text-sm text-[var(--text-muted)]">状态</span>
          <span class="flex items-center gap-1.5 text-sm font-medium" :class="selectedListener.enabled ? 'text-green-600' : 'text-gray-400'">
            <span class="w-2 h-2 rounded-full" :class="selectedListener.enabled ? 'bg-green-500' : 'bg-gray-300'" />
            {{ selectedListener.enabled ? '启用' : '停用' }}
          </span>
        </div>
        <div class="flex items-center justify-between py-2 border-b border-[var(--border)]">
          <span class="text-sm text-[var(--text-muted)]">触发方式</span>
          <span class="text-sm">{{ triggerTypeLabel(selectedListener.triggerType) }}</span>
        </div>
        <!-- 文件变更: 监听路径 -->
        <template v-if="selectedListener.triggerType === 'file_change'">
          <div class="flex items-center justify-between py-2 border-b border-[var(--border)]">
            <span class="text-sm text-[var(--text-muted)]">监听路径</span>
            <span class="text-sm text-right max-w-[60%] truncate">{{ selectedListener.watchPath || '—' }}</span>
          </div>
        </template>
        <!-- 定时触发: 触发间隔 -->
        <template v-if="selectedListener.triggerType === 'scheduled'">
          <div class="flex items-center justify-between py-2 border-b border-[var(--border)]">
            <span class="text-sm text-[var(--text-muted)]">触发间隔（秒）</span>
            <span class="text-sm">每 {{ selectedListener.intervalSeconds }} 秒</span>
          </div>
        </template>
        <div class="flex items-center justify-between py-2 border-b border-[var(--border)]">
          <span class="text-sm text-[var(--text-muted)]">触发条件</span>
          <span class="text-sm">{{ triggerConditionLabel(selectedListener.triggerCondition) }}</span>
        </div>
        <div class="flex items-center justify-between py-2 border-b border-[var(--border)]">
          <span class="text-sm text-[var(--text-muted)]">防抖</span>
          <span class="text-sm">{{ selectedListener.debounceSeconds > 0 ? selectedListener.debounceSeconds + '秒' : '关闭' }}</span>
        </div>
        <div class="flex items-center justify-between py-2 border-b border-[var(--border)]">
          <span class="text-sm text-[var(--text-muted)]">静默时段</span>
          <span class="text-sm">{{ selectedListener.quietHours ? '开启' : '关闭' }}</span>
        </div>
        <div class="flex items-center justify-between py-2">
          <span class="text-sm text-[var(--text-muted)]">总执行次数</span>
          <span class="text-sm">{{ selectedListener.runCount }} 次</span>
        </div>
      </div>

      <!-- HTTP 接收地址 -->
      <div v-if="selectedListener.triggerType === 'http'" class="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-[var(--shadow)] mb-4">
        <div class="text-xs font-medium text-[var(--text-muted)] mb-3">HTTP 接收地址</div>
        <div class="flex items-center gap-2 mb-4">
          <div class="flex-1 px-4 py-2.5 rounded-xl bg-[var(--bg-page)] border border-[var(--border)] text-sm font-mono">
            POST http://localhost:18080/trigger/{{ selectedListener.id }}
          </div>
          <button class="p-2 rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition" title="复制" @click="copyUrl">
            <Copy class="w-4 h-4" />
          </button>
        </div>
        <div class="text-xs font-medium text-[var(--text-muted)] mb-2">curl 示例</div>
        <pre class="px-4 py-3 rounded-xl bg-[var(--bg-page)] border border-[var(--border)] text-sm font-mono whitespace-pre-wrap">curl -X POST http://localhost:18080/trigger/{{ selectedListener.id }} \
  -H "Content-Type: application/json" \
  -d '{"{"}"data": {"{"}"content": "test message"}{"}"}"'</pre>
      </div>

      <!-- 描述 -->
      <div class="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-[var(--shadow)] mb-4">
        <div class="text-xs font-medium text-[var(--text-muted)] mb-2">描述</div>
        <div class="text-sm">{{ selectedListener.description || '—' }}</div>
      </div>

      <!-- 指令 -->
      <div class="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-[var(--shadow)] mb-4">
        <div class="text-xs font-medium text-[var(--text-muted)] mb-2">指令</div>
        <div class="text-sm whitespace-pre-wrap bg-[var(--bg-page)] rounded-xl px-4 py-3">{{ selectedListener.command || '—' }}</div>
      </div>

      <!-- 操作按钮 -->
      <div class="flex items-center gap-3 mb-6">
        <button class="flex items-center gap-1.5 px-5 py-2.5 rounded-xl border border-[var(--border)] text-sm hover:bg-[var(--bg-muted)] transition" @click="handleToggle(selectedListener)">
          <Square class="w-4 h-4" />
          <span>{{ selectedListener.enabled ? '暂停' : '启用' }}</span>
        </button>
        <button class="flex items-center gap-1.5 px-5 py-2.5 rounded-xl border border-[var(--border)] text-sm hover:bg-[var(--bg-muted)] transition">
          <Zap class="w-4 h-4" />
          <span>测试触发</span>
        </button>
        <div class="flex-1" />
        <button class="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm text-red-500 hover:bg-red-50 transition" @click="handleDelete(selectedListener.id)">
          <Trash2 class="w-4 h-4" />
          <span>删除</span>
        </button>
      </div>

      <!-- 执行记录 -->
      <div class="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-[var(--shadow)]">
        <div class="px-5 py-3 border-b border-[var(--border)]">
          <h3 class="font-medium text-sm">执行记录</h3>
        </div>
        <div class="px-5 py-8 text-center text-sm text-[var(--text-muted)]">
          暂无执行记录
        </div>
      </div>
    </template>

    <!-- ===== List View ===== -->
    <template v-else>
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-xl font-semibold">监听事件</h1>
        <button class="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#d9896d] text-white text-sm font-medium hover:opacity-90 transition" @click="openCreate">
          <Plus class="w-4 h-4" />
          <span>新建监听</span>
        </button>
      </div>

      <div class="rounded-xl bg-[var(--bg-card)] border border-[var(--border)] px-4 py-3 mb-4 flex items-center gap-2 text-sm text-[var(--text-muted)]">
        <Info class="w-4 h-4 flex-shrink-0" />
        <span>监听事件可通过 HTTP、文件变化、IM 消息等触发小巧自动执行任务</span>
      </div>

      <div v-if="store.loading" class="py-12 text-center text-sm text-[var(--text-muted)]">
        <Loader2 class="w-5 h-5 animate-spin mx-auto mb-2" />
        加载中…
      </div>

      <div v-else-if="store.listeners.length === 0" class="py-12 text-center text-sm text-[var(--text-muted)]">
        暂无监听事件
      </div>

      <div v-else class="space-y-2">
        <div
          v-for="listener in store.listeners"
          :key="listener.id"
          class="flex items-center justify-between px-4 py-3 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] shadow-[var(--shadow)] cursor-pointer hover:bg-[var(--bg-muted)] transition"
          @click="selectedListenerId = listener.id"
        >
          <div class="flex items-center gap-3">
            <div class="w-2 h-2 rounded-full" :class="listener.enabled ? 'bg-green-500' : 'bg-gray-300'" />
            <div>
              <div class="font-medium text-sm">{{ listener.name || '未命名监听' }}</div>
              <div class="flex items-center gap-1.5 text-xs text-[var(--text-muted)] mt-0.5">
                <Zap class="w-3 h-3" />
                <span>{{ triggerTypeLabel(listener.triggerType) }}</span>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2" @click.stop>
            <button class="relative w-11 h-6 rounded-full transition" :class="listener.enabled ? 'bg-[#d9896d]' : 'bg-[var(--bg-muted)]'" @click="handleToggle(listener)">
              <span class="absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform" :class="listener.enabled ? 'translate-x-5' : 'translate-x-0'" />
            </button>
            <button class="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-red-500 hover:bg-red-50 transition" @click="handleDelete(listener.id)">
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Create/Edit Modal -->
    <Teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="showModal = false">
        <div class="w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-2xl bg-[var(--bg-card)] p-6 shadow-xl">
          <div class="flex items-center justify-between mb-5">
            <h2 class="text-lg font-semibold">{{ editingListener ? '编辑监听' : '新建监听' }}</h2>
            <button class="text-[var(--text-muted)] hover:text-[var(--text)] transition" @click="showModal = false">
              <span class="text-xl">&times;</span>
            </button>
          </div>

          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium mb-1.5">触发器名称</label>
              <input v-model="form.name" type="text" placeholder="例如：群消息告警处理" class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] outline-none focus:border-[var(--text-muted)] text-sm">
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">描述</label>
              <input v-model="form.description" type="text" placeholder="描述这个触发器的用途..." class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] outline-none focus:border-[var(--text-muted)] text-sm">
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">触发方式</label>
              <div class="flex flex-wrap gap-2">
                <button v-for="opt in triggerTypeOptions" :key="opt.value" class="px-4 py-2 rounded-xl text-sm border transition" :class="form.triggerType === opt.value ? 'bg-[#d9896d] text-white border-[#d9896d]' : 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--bg-muted)]'" @click="form.triggerType = opt.value; resetTriggerFields()">
                  {{ opt.label }}
                </button>
              </div>
            </div>

            <!-- file_change 专属 -->
            <template v-if="form.triggerType === 'file_change'">
              <div>
                <label class="block text-sm font-medium mb-1.5">监听路径</label>
                <input v-model="form.watchPath" type="text" placeholder="输入要监听的文件或目录路径" class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] outline-none focus:border-[var(--text-muted)] text-sm">
              </div>
              <div>
                <label class="block text-sm font-medium mb-1.5">监听事件</label>
                <div class="flex flex-wrap gap-2">
                  <button v-for="opt in watchEventOptions" :key="opt.value" class="px-4 py-2 rounded-xl text-sm border transition" :class="form.watchEvents.includes(opt.value) ? 'bg-[#d9896d] text-white border-[#d9896d]' : 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--bg-muted)]'" @click="toggleWatchEvent(opt.value)">
                    {{ opt.label }}
                  </button>
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1.5">文件名匹配</label>
                <input v-model="form.fileNamePattern" type="text" placeholder="例如：*.log 或 *.csv（留空监听全部）" class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] outline-none focus:border-[var(--text-muted)] text-sm">
              </div>
            </template>

            <!-- scheduled 专属 -->
            <template v-if="form.triggerType === 'scheduled'">
              <div>
                <label class="block text-sm font-medium mb-1.5">触发间隔（秒）</label>
                <div class="flex items-center gap-1.5">
                  <input v-model.number="form.intervalSeconds" type="number" min="1" class="w-28 px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] outline-none focus:border-[var(--text-muted)] text-sm">
                  <span class="text-sm text-[var(--text-muted)]">秒</span>
                </div>
              </div>
            </template>

            <!-- im_message 专属 -->
            <template v-if="form.triggerType === 'im_message'">
              <div>
                <label class="block text-sm font-medium mb-1.5">选择 IM 频道</label>
                <select v-model="form.imChannel" class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] text-sm outline-none">
                  <option value="">请先在设置 → IM 频道中添加频道</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1.5">监听范围</label>
                <div class="space-y-2">
                  <label v-for="opt in imScopeOptions" :key="opt.value" class="flex items-center gap-2.5 text-sm cursor-pointer">
                    <input v-model="form.imScope" type="radio" :value="opt.value" class="w-4 h-4 accent-[#d9896d]">
                    <span>{{ opt.label }}</span>
                  </label>
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1.5">群 ID（可选）</label>
                <input v-model="form.groupId" type="text" placeholder="从 IM 平台复制群 ID，不填=所有群" class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] outline-none focus:border-[var(--text-muted)] text-sm">
              </div>
              <div>
                <label class="block text-sm font-medium mb-1.5">发送者匹配（可选）</label>
                <input v-model="form.senderMatch" type="text" placeholder="机器人名称或 ID" class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] outline-none focus:border-[var(--text-muted)] text-sm">
              </div>
            </template>

            <div>
              <label class="block text-sm font-medium mb-1.5">执行指令</label>
              <textarea v-model="form.command" placeholder="收到事件后小巧要执行的指令..." rows="4" class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] outline-none focus:border-[var(--text-muted)] text-sm resize-none" />
              <p class="text-xs text-[var(--text-muted)] mt-1">使用 $EVENT_DATA 引用事件数据</p>
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">触发条件</label>
              <div class="flex flex-wrap gap-2">
                <button v-for="opt in triggerConditionOptions" :key="opt.value" class="px-4 py-2 rounded-xl text-sm border transition" :class="form.triggerCondition === opt.value ? 'bg-[#d9896d] text-white border-[#d9896d]' : 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--bg-muted)]'" @click="form.triggerCondition = opt.value">
                  {{ opt.label }}
                </button>
              </div>
            </div>

            <div class="flex items-center gap-3">
              <label class="flex items-center gap-2 text-sm font-medium cursor-pointer">
                <input v-model="form.debounceEnabled" type="checkbox" class="w-4 h-4 rounded accent-[#d9896d]">
                <span>防抖（相同内容去重）</span>
              </label>
              <div v-if="form.debounceEnabled" class="flex items-center gap-1.5">
                <input v-model.number="form.debounceSeconds" type="number" min="1" class="w-20 px-2 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-page)] text-sm outline-none">
                <span class="text-sm text-[var(--text-muted)]">秒</span>
              </div>
            </div>

            <div>
              <label class="flex items-center gap-2 text-sm font-medium cursor-pointer">
                <input v-model="form.quietHours" type="checkbox" class="w-4 h-4 rounded accent-[#d9896d]">
                <span>静默时段（该时段内不触发）</span>
              </label>
            </div>

            <div>
              <label class="flex items-center gap-2 text-sm font-medium cursor-pointer">
                <input v-model="form.pushResult" type="checkbox" class="w-4 h-4 rounded accent-[#d9896d]">
                <span>处理完成后推送结果</span>
              </label>
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">绑定技能</label>
              <select v-model="form.skill" class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] text-sm outline-none">
                <option value="">不绑定</option>
              </select>
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">所属项目</label>
              <select v-model="form.project" class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] text-sm outline-none">
                <option value="">不关联项目</option>
              </select>
            </div>
          </div>

          <div class="flex justify-end gap-3 mt-6 pt-4 border-t border-[var(--border)]">
            <button class="px-5 py-2 rounded-xl text-sm border border-[var(--border)] hover:bg-[var(--bg-muted)] transition" @click="showModal = false">取消</button>
            <button class="px-5 py-2 rounded-xl text-sm bg-[#d9896d] text-white font-medium hover:opacity-90 transition disabled:opacity-60" :disabled="saving" @click="handleSave">
              <Loader2 v-if="saving" class="w-4 h-4 animate-spin inline-block mr-1" />
              保存
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
