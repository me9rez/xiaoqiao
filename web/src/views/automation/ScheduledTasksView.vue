<script setup lang="ts">
import { ArrowLeft, Clock, Info, Loader2, Pencil, Play, Plus, Sparkles, Square, Trash2 } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useAutomationStore } from '@/stores/automation'
import type { ScheduledTask } from '@/types/automation'

const store = useAutomationStore()

const showModal = ref(false)
const editingTask = ref<ScheduledTask | null>(null)
const saving = ref(false)
const selectedTaskId = ref<string | null>(null)

const selectedTask = computed(() => {
  if (!selectedTaskId.value) return null
  return store.tasks.find((t) => t.id === selectedTaskId.value) ?? null
})

const form = ref({
  name: '',
  description: '',
  command: '',
  frequency: 'daily' as ScheduledTask['frequency'],
  timeHour: 9,
  timeMinute: 0,
  skill: '',
  project: '',
  workspacePath: '',
  pushChannel: '',
})

const frequencyOptions: { value: ScheduledTask['frequency']; label: string }[] = [
  { value: 'hourly', label: '每小时' },
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每周' },
  { value: 'weekdays', label: '工作日' },
  { value: 'manual', label: '手动' },
]

const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))
const minutes = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, '0'))

function frequencyLabel(f: string): string {
  return frequencyOptions.find((o) => o.value === f)?.label ?? f
}

function formatSchedule(task: ScheduledTask): string {
  if (task.frequency === 'manual') return '手动触发'
  if (task.frequency === 'hourly') return '每小时'
  if (task.frequency === 'weekly') return '每周'
  if (task.frequency === 'weekdays') return '工作日'
  const h = String(task.timeHour).padStart(2, '0')
  const m = String(task.timeMinute).padStart(2, '0')
  return `每天 ${h}:${m}`
}

function openCreate() {
  editingTask.value = null
  form.value = {
    name: '',
    description: '',
    command: '',
    frequency: 'daily',
    timeHour: 9,
    timeMinute: 0,
    skill: '',
    project: '',
    workspacePath: '',
    pushChannel: '',
  }
  showModal.value = true
}

function openEditFromDetail() {
  if (!selectedTask.value) return
  editingTask.value = selectedTask.value
  form.value = {
    name: selectedTask.value.name,
    description: selectedTask.value.description,
    command: selectedTask.value.command,
    frequency: selectedTask.value.frequency,
    timeHour: selectedTask.value.timeHour,
    timeMinute: selectedTask.value.timeMinute,
    skill: selectedTask.value.skill,
    project: selectedTask.value.project,
    workspacePath: selectedTask.value.workspacePath,
    pushChannel: selectedTask.value.pushChannel,
  }
  showModal.value = true
}

async function handleSave() {
  saving.value = true
  try {
    if (editingTask.value) {
      await store.updateTask(editingTask.value.id, form.value)
    } else {
      const task = await store.createTask(form.value)
      if (task) selectedTaskId.value = task.id
    }
    showModal.value = false
  } finally {
    saving.value = false
  }
}

async function handleDelete(id: string) {
  await store.deleteTask(id)
  if (selectedTaskId.value === id) selectedTaskId.value = null
}

async function handleToggle(task: ScheduledTask) {
  await store.toggleTask(task.id, !task.enabled)
}

function goBack() {
  selectedTaskId.value = null
}

onMounted(() => {
  store.fetchTasks()
})
</script>

<template>
  <div class="p-8 max-w-4xl mx-auto">
    <!-- ===== Detail View ===== -->
    <template v-if="selectedTask">
      <div class="flex items-center justify-between mb-6">
        <div class="flex items-center gap-3">
          <button
            class="p-1.5 rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition"
            @click="goBack"
          >
            <ArrowLeft class="w-5 h-5" />
          </button>
          <h1 class="text-xl font-semibold">{{ selectedTask.name || '未命名任务' }}</h1>
        </div>
        <button
          class="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition"
          @click="openEditFromDetail"
        >
          <Pencil class="w-4 h-4" />
          <span>编辑</span>
        </button>
      </div>

      <!-- 状态/调度/执行记录 -->
      <div class="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-[var(--shadow)] mb-4">
        <div class="flex items-center justify-between py-2 border-b border-[var(--border)]">
          <span class="text-sm text-[var(--text-muted)]">状态</span>
          <span class="flex items-center gap-1.5 text-sm font-medium" :class="selectedTask.enabled ? 'text-green-600' : 'text-gray-400'">
            <span class="w-2 h-2 rounded-full" :class="selectedTask.enabled ? 'bg-green-500' : 'bg-gray-300'" />
            {{ selectedTask.enabled ? '启用' : '停用' }}
          </span>
        </div>
        <div class="flex items-center justify-between py-2 border-b border-[var(--border)]">
          <span class="text-sm text-[var(--text-muted)]">调度</span>
          <span class="flex items-center gap-1.5 text-sm">
            <Clock class="w-3.5 h-3.5 text-[var(--text-muted)]" />
            {{ formatSchedule(selectedTask) }}
          </span>
        </div>
        <div class="flex items-center justify-between py-2">
          <span class="text-sm text-[var(--text-muted)]">执行记录</span>
          <span class="text-sm">共执行 {{ selectedTask.runCount }} 次</span>
        </div>
      </div>

      <!-- 任务描述 -->
      <div class="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-[var(--shadow)] mb-4">
        <div class="text-xs font-medium text-[var(--text-muted)] mb-2">任务描述</div>
        <div class="text-sm">{{ selectedTask.description || '—' }}</div>
      </div>

      <!-- 指令 -->
      <div class="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-[var(--shadow)] mb-4">
        <div class="text-xs font-medium text-[var(--text-muted)] mb-2">指令</div>
        <div class="text-sm whitespace-pre-wrap bg-[var(--bg-page)] rounded-xl px-4 py-3">{{ selectedTask.command || '—' }}</div>
      </div>

      <!-- 操作按钮 -->
      <div class="flex items-center gap-3 mb-6">
        <button class="flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-[#d9896d] text-white text-sm font-medium hover:opacity-90 transition">
          <Play class="w-4 h-4" />
          <span>立即执行</span>
        </button>
        <button
          class="flex items-center gap-1.5 px-5 py-2.5 rounded-xl border border-[var(--border)] text-sm hover:bg-[var(--bg-muted)] transition"
          @click="handleToggle(selectedTask)"
        >
          <Square class="w-4 h-4" />
          <span>{{ selectedTask.enabled ? '暂停' : '启用' }}</span>
        </button>
        <div class="flex-1" />
        <button
          class="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm text-red-500 hover:bg-red-50 transition"
          @click="handleDelete(selectedTask.id)"
        >
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
        <h1 class="text-xl font-semibold">定时任务</h1>
        <div class="flex items-center gap-3">
          <button class="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition">
            <Sparkles class="w-4 h-4" />
            <span>让小巧帮你创建</span>
          </button>
          <button
            class="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#d9896d] text-white text-sm font-medium hover:opacity-90 transition"
            @click="openCreate"
          >
            <Plus class="w-4 h-4" />
            <span>新建任务</span>
          </button>
        </div>
      </div>

      <div class="rounded-xl bg-[var(--bg-card)] border border-[var(--border)] px-4 py-3 mb-4 flex items-center gap-2 text-sm text-[var(--text-muted)]">
        <Info class="w-4 h-4 flex-shrink-0" />
        <span>定时任务仅在应用打开且电脑未休眠时运行</span>
      </div>

      <div v-if="store.loading" class="py-12 text-center text-sm text-[var(--text-muted)]">
        <Loader2 class="w-5 h-5 animate-spin mx-auto mb-2" />
        加载中…
      </div>

      <div v-else-if="store.tasks.length === 0" class="py-12 text-center text-sm text-[var(--text-muted)]">
        暂无定时任务
      </div>

      <div v-else class="space-y-2">
        <div
          v-for="task in store.tasks"
          :key="task.id"
          class="flex items-center justify-between px-4 py-3 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] shadow-[var(--shadow)] cursor-pointer hover:bg-[var(--bg-muted)] transition"
          @click="selectedTaskId = task.id"
        >
          <div class="flex items-center gap-3">
            <div class="w-2 h-2 rounded-full" :class="task.enabled ? 'bg-green-500' : 'bg-gray-300'" />
            <div>
              <div class="font-medium text-sm">{{ task.name || '未命名任务' }}</div>
              <div class="flex items-center gap-1.5 text-xs text-[var(--text-muted)] mt-0.5">
                <Clock class="w-3 h-3" />
                <span>{{ formatSchedule(task) }}</span>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2" @click.stop>
            <button
              class="relative w-11 h-6 rounded-full transition"
              :class="task.enabled ? 'bg-[#d9896d]' : 'bg-[var(--bg-muted)]'"
              @click="handleToggle(task)"
            >
              <span
                class="absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform"
                :class="task.enabled ? 'translate-x-5' : 'translate-x-0'"
              />
            </button>
            <button
              class="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-red-500 hover:bg-red-50 transition"
              @click="handleDelete(task.id)"
            >
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Create/Edit Modal -->
    <Teleport to="body">
      <div
        v-if="showModal"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        @click.self="showModal = false"
      >
        <div class="w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-2xl bg-[var(--bg-card)] p-6 shadow-xl">
          <div class="flex items-center justify-between mb-5">
            <h2 class="text-lg font-semibold">{{ editingTask ? '编辑任务' : '新建任务' }}</h2>
            <button class="text-[var(--text-muted)] hover:text-[var(--text)] transition" @click="showModal = false">
              <span class="text-xl">&times;</span>
            </button>
          </div>

          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium mb-1.5">任务名称</label>
              <input
                v-model="form.name"
                type="text"
                placeholder="例如：每日晨报"
                class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] outline-none focus:border-[var(--text-muted)] text-sm"
              >
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">任务描述</label>
              <input
                v-model="form.description"
                type="text"
                placeholder="描述这个任务的目的..."
                class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] outline-none focus:border-[var(--text-muted)] text-sm"
              >
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">任务指令</label>
              <textarea
                v-model="form.command"
                placeholder="输入小巧要执行的指令..."
                rows="4"
                class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] outline-none focus:border-[var(--text-muted)] text-sm resize-none"
              />
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">执行频率</label>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="opt in frequencyOptions"
                  :key="opt.value"
                  class="px-4 py-2 rounded-xl text-sm border transition"
                  :class="form.frequency === opt.value
                    ? 'bg-[#d9896d] text-white border-[#d9896d]'
                    : 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--bg-muted)]'"
                  @click="form.frequency = opt.value"
                >
                  {{ opt.label }}
                </button>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">执行时间</label>
              <div class="flex items-center gap-2">
                <select
                  v-model="form.timeHour"
                  class="px-3 py-2 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] text-sm outline-none"
                >
                  <option v-for="h in hours" :key="h" :value="Number(h)">{{ h }}</option>
                </select>
                <span class="text-[var(--text-muted)]">:</span>
                <select
                  v-model="form.timeMinute"
                  class="px-3 py-2 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] text-sm outline-none"
                >
                  <option v-for="m in minutes" :key="m" :value="Number(m)">{{ m }}</option>
                </select>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">绑定技能</label>
              <select
                v-model="form.skill"
                class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] text-sm outline-none"
              >
                <option value="">不绑定</option>
              </select>
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">所属项目</label>
              <select
                v-model="form.project"
                class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] text-sm outline-none"
              >
                <option value="">不关联项目</option>
              </select>
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">工作区路径</label>
              <input
                v-model="form.workspacePath"
                type="text"
                placeholder="可选，指定工作目录"
                class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] outline-none focus:border-[var(--text-muted)] text-sm"
              >
            </div>

            <div>
              <label class="block text-sm font-medium mb-1.5">结果推送频道</label>
              <select
                v-model="form.pushChannel"
                class="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-page)] text-sm outline-none"
              >
                <option value="">不推送</option>
              </select>
            </div>
          </div>

          <div class="flex justify-end gap-3 mt-6 pt-4 border-t border-[var(--border)]">
            <button
              class="px-5 py-2 rounded-xl text-sm border border-[var(--border)] hover:bg-[var(--bg-muted)] transition"
              @click="showModal = false"
            >
              取消
            </button>
            <button
              class="px-5 py-2 rounded-xl text-sm bg-[#d9896d] text-white font-medium hover:opacity-90 transition disabled:opacity-60"
              :disabled="saving"
              @click="handleSave"
            >
              <Loader2 v-if="saving" class="w-4 h-4 animate-spin inline-block mr-1" />
              保存
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
