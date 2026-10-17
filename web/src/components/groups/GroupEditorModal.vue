<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import BotAvatar from '@/components/bots/BotAvatar.vue'
import { useBotsStore } from '@/stores/bots'
import { useGroupsStore } from '@/stores/groups'
import type { Group } from '@/types/group'

const props = defineProps<{ open: boolean; group: Group | null }>()
const emit = defineEmits<{ close: []; saved: [group: Group] }>()

const botsStore = useBotsStore()
const groupsStore = useGroupsStore()
const saving = ref(false)
const formError = ref<string | null>(null)

const form = reactive({
  name: '',
  botIds: [] as string[],
  defaultBotId: '',
  maxHops: 3,
})

const selectedBots = computed(() => botsStore.bots.filter((bot) => form.botIds.includes(bot.id)))

watch(
  () => [props.open, props.group] as const,
  ([open, group]) => {
    if (!open) return
    form.name = group?.name ?? ''
    form.botIds = group ? [...group.botIds] : botsStore.bots.map((bot) => bot.id)
    form.defaultBotId = group?.defaultBotId ?? form.botIds[0] ?? ''
    form.maxHops = group?.settings.maxHops ?? 3
    formError.value = null
  },
  { immediate: true },
)

function toggleBot(botId: string) {
  if (form.botIds.includes(botId)) {
    form.botIds = form.botIds.filter((id) => id !== botId)
    if (form.defaultBotId === botId) {
      form.defaultBotId = form.botIds[0] ?? ''
    }
  } else {
    form.botIds = [...form.botIds, botId]
    if (!form.defaultBotId) form.defaultBotId = botId
  }
}

async function handleSave() {
  if (!form.name.trim()) {
    formError.value = '群名称不能为空'
    return
  }
  if (form.botIds.length === 0) {
    formError.value = '至少选择一个 Bot'
    return
  }
  saving.value = true
  formError.value = null
  try {
    const payload = {
      name: form.name.trim(),
      botIds: form.botIds,
      defaultBotId: form.defaultBotId || form.botIds[0],
      settings: { maxHops: form.maxHops },
    }
    const saved = props.group
      ? await groupsStore.update(props.group.id, payload)
      : await groupsStore.create(payload)
    if (saved) {
      emit('saved', saved)
      emit('close')
    } else {
      formError.value = groupsStore.error ?? '保存失败'
    }
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (!props.group) return
  if (!window.confirm(`删除群「${props.group.name}」？群内消息会一并删除。`)) return
  saving.value = true
  try {
    if (await groupsStore.remove(props.group.id)) emit('close')
    else formError.value = groupsStore.error ?? '删除失败'
  } finally {
    saving.value = false
  }
}

function closeOverlay(event: MouseEvent) {
  if (event.target === event.currentTarget) emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center p-6 bg-[#0d111747]"
      role="dialog"
      aria-modal="true"
      aria-label="编辑群聊"
      @click="closeOverlay"
    >
      <div
        class="w-full max-w-[440px] max-h-[calc(100vh-64px)] flex flex-col rounded-[var(--radius-xl)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] shadow-[var(--shadow-xl)]"
      >
        <header class="px-5 pt-5 pb-3">
          <h2 class="text-[16px] font-[var(--weight-medium)] text-[var(--color-text-strong)]">
            {{ group ? '编辑群聊' : '新建群聊' }}
          </h2>
          <p class="mt-1 text-[14px] text-[var(--color-text-muted)]">
            把人之外的几个 Bot 拉进一个线程，它们可以互相 @。
          </p>
        </header>

        <div class="px-5 pb-4 overflow-y-auto space-y-4">
          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">群名称</span>
            <input
              v-model="form.name"
              type="text"
              class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              placeholder="例如 每日简报"
            >
          </label>

          <div>
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">
              成员（{{ form.botIds.length }}）
            </span>
            <div class="space-y-1 max-h-48 overflow-y-auto">
              <button
                v-for="bot in botsStore.bots"
                :key="bot.id"
                type="button"
                class="w-full flex items-center gap-2 px-2.5 py-2 rounded-[var(--radius-md)] text-left transition-colors duration-[var(--duration-base)]"
                :class="
                  form.botIds.includes(bot.id)
                    ? 'bg-[var(--color-selected)]'
                    : 'hover:bg-[var(--color-hover)]'
                "
                :aria-pressed="form.botIds.includes(bot.id)"
                @click="toggleBot(bot.id)"
              >
                <BotAvatar :bot="bot" size="sm" />
                <span class="flex-1 text-[13px] text-[var(--color-text)]">{{ bot.name }}</span>
                <span class="text-[12px] text-[var(--color-text-faint)]">@{{ bot.slug }}</span>
              </button>
            </div>
          </div>

          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">
              默认应答 Bot
            </span>
            <select
              v-model="form.defaultBotId"
              class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
            >
              <option v-for="bot in selectedBots" :key="bot.id" :value="bot.id">{{ bot.name }}</option>
            </select>
            <span class="block mt-1 text-[12px] text-[var(--color-text-faint)]">没写 @ 时由它回应。</span>
          </label>

          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">
              最多交接跳数
            </span>
            <input
              v-model.number="form.maxHops"
              type="number"
              min="0"
              max="6"
              class="w-24 h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
            >
          </label>

          <p v-if="formError" class="text-[13px] text-[var(--color-danger)]" role="alert">{{ formError }}</p>
        </div>

        <footer class="px-5 py-3.5 flex items-center gap-2.5 border-t border-[var(--color-line)]">
          <button
            v-if="group"
            type="button"
            class="h-[36px] px-4 rounded-[var(--radius-md)] text-[14px] font-[var(--weight-medium)] text-[var(--color-danger)] bg-[var(--color-danger-soft)] border-0.5 border-[var(--color-danger-bd)] hover:brightness-95 disabled:opacity-50"
            :disabled="saving"
            @click="handleDelete"
          >
            删除
          </button>
          <span class="flex-1" />
          <button
            type="button"
            class="h-[36px] px-4 rounded-[var(--radius-md)] text-[14px] text-[var(--color-text)] bg-[var(--color-surface-raised)] border-0.5 border-[var(--color-line-strong)] hover:bg-[var(--color-hover)] disabled:opacity-50"
            :disabled="saving"
            @click="emit('close')"
          >
            取消
          </button>
          <button
            type="button"
            class="h-[36px] px-4 rounded-[var(--radius-md)] text-[14px] font-[var(--weight-medium)] text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
            :disabled="saving"
            @click="handleSave"
          >
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>
