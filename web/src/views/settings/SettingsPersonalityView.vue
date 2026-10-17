<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

const STORAGE_KEY = 'xiaoqiao:personality'
const LEGACY_STORAGE_KEY = 'coding-agent:personality'
const MAX_LENGTH = 2000

type Proactivity = 'shy' | 'partner' | 'butler'

const proactivity = ref<Proactivity>('partner')
const content = ref('')

const proactivityOptions: { value: Proactivity; label: string; desc: string; icon: string }[] = [
  { value: 'shy', label: '害羞', desc: '你让我做才提议', icon: '🌱' },
  { value: 'partner', label: '伙伴', desc: '明确能帮上时主动提议（推荐）', icon: '🌿' },
  { value: 'butler', label: '管家', desc: '积极沉淀，每个成功任务都考虑建 skill', icon: '🌳' },
]

const charCount = computed(() => content.value.length)

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY)
    if (raw) {
      const data = JSON.parse(raw)
      if (localStorage.getItem(STORAGE_KEY) === null) {
        localStorage.setItem(STORAGE_KEY, raw)
        localStorage.removeItem(LEGACY_STORAGE_KEY)
      }
      proactivity.value = data.proactivity ?? 'partner'
      content.value = data.content ?? ''
    } else {
      proactivity.value = 'partner'
      content.value = `# 语气\n你说话简洁直接，像一个靠谱的朋友在帮忙。不用敬语，不用"您"。\n\n# 称呼\n你叫"小巧"，称用户"你"\n\n# 回复风格\n- 先给结论或结果，过程按需展开\n- 遇到不确定的直接说，不要硬编\n- 中文回复为主\n\n# 边界\n（在这里写不希望小巧做的事）`
    }
  } catch {
    // ignore
  }
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ proactivity: proactivity.value, content: content.value }))
    localStorage.removeItem(LEGACY_STORAGE_KEY)
  } catch {
    // ignore
  }
}

onMounted(load)

watch([proactivity, content], save, { deep: true })
</script>

<template>
  <div class="p-8 max-w-3xl mx-auto">
    <div class="mb-6">
      <h1 class="text-xl font-semibold">
        性格
      </h1>
      <p class="text-sm text-[var(--text-muted)] mt-1">
        小巧出厂自带性格，你可以按自己的喜好调整
      </p>
    </div>

    <div class="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-[var(--shadow)] mb-6">
      <h2 class="font-medium mb-2">
        主动度
      </h2>
      <p class="text-sm text-[var(--text-muted)] mb-4">
        小巧在对话中要不要主动提议沉淀技能。害羞只在你明说时才建，伙伴明确可帮上时主动提议（推荐），管家每次成功任务都考虑提议。
      </p>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <button
          v-for="opt in proactivityOptions"
          :key="opt.value"
          class="text-left rounded-xl border p-4 transition"
          :class="proactivity === opt.value
            ? 'border-[#d9896d] bg-[#fdf7f4]'
            : 'border-[var(--border)] bg-[var(--bg-page)] hover:bg-[var(--bg-muted)]'"
          @click="proactivity = opt.value"
        >
          <div class="flex items-center gap-2 mb-2">
            <span class="text-lg">{{ opt.icon }}</span>
            <span class="font-medium">{{ opt.label }}</span>
          </div>
          <p class="text-xs text-[var(--text-muted)]">
            {{ opt.desc }}
          </p>
        </button>
      </div>
    </div>

    <div class="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-[var(--shadow)]">
      <textarea
        v-model="content"
        :maxlength="MAX_LENGTH"
        class="w-full h-80 p-4 rounded-xl border border-[var(--border)] bg-[var(--bg-muted)] outline-none focus:border-[var(--text-muted)] resize-none text-sm leading-relaxed"
      />
      <div class="flex items-center justify-between mt-3">
        <span class="text-xs text-[var(--text-subtle)]">
          文件位置：~/.xiaoqiao/SOUL.md（高级用户可直接编辑）
        </span>
        <span class="text-xs text-[var(--text-subtle)]">
          {{ charCount }} / {{ MAX_LENGTH }}
        </span>
      </div>
    </div>
  </div>
</template>
