<script setup lang="ts">
import { reactive, ref, watch } from 'vue'

import { useBotsStore } from '@/stores/bots'
import { useChannelsStore } from '@/stores/channels'
import { useGroupsStore } from '@/stores/groups'
import type { Channel } from '@/types/channel'

const props = defineProps<{ open: boolean; channel: Channel | null }>()
const emit = defineEmits<{ close: []; saved: [channel: Channel] }>()

const botsStore = useBotsStore()
const groupsStore = useGroupsStore()
const channelsStore = useChannelsStore()

const saving = ref(false)
const formError = ref<string | null>(null)

const form = reactive({
  token: '',
  groupId: '',
  chatId: '',
  enabled: true,
})

watch(
  () => [props.open, props.channel] as const,
  ([open, channel]) => {
    if (!open) return
    form.token = ''
    form.groupId = String(channel?.config.groupId ?? '')
    form.chatId = String(channel?.config.chatId ?? '')
    form.enabled = channel?.enabled ?? true
    formError.value = null
  },
  { immediate: true },
)

async function handleSave() {
  if (!props.channel && !form.token.trim()) {
    formError.value = '首次接入需要填写 Bot Token'
    return
  }
  if (!form.groupId) {
    formError.value = '请选择要接收消息的群聊'
    return
  }
  saving.value = true
  formError.value = null
  try {
    const config: Record<string, unknown> = {
      groupId: form.groupId,
      chatId: form.chatId.trim(),
    }
    if (form.token.trim()) config.token = form.token.trim()

    const saved = props.channel
      ? await channelsStore.update(props.channel.id, { config, enabled: form.enabled })
      : await channelsStore.create({
          botId: botsStore.activeBotId ?? '',
          kind: 'telegram',
          config,
          enabled: form.enabled,
        })
    if (saved) {
      emit('saved', saved)
      emit('close')
    } else {
      formError.value = channelsStore.error ?? '保存失败'
    }
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
      aria-label="编辑频道"
      @click="closeOverlay"
    >
      <div
        class="w-full max-w-[440px] max-h-[calc(100vh-64px)] flex flex-col rounded-[var(--radius-xl)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] shadow-[var(--shadow-xl)]"
      >
        <header class="px-5 pt-5 pb-3">
          <h2 class="text-[16px] font-[var(--weight-medium)] text-[var(--color-text-strong)]">
            {{ channel ? '编辑频道' : '接入 Telegram' }}
          </h2>
          <p class="mt-1 text-[14px] text-[var(--color-text-muted)]">
            把消息接到一个群聊；群里的 @ 路由与网页一致。
          </p>
        </header>

        <div class="px-5 pb-4 overflow-y-auto space-y-4">
          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">
              Bot Token
            </span>
            <input
              v-model="form.token"
              type="password"
              autocomplete="off"
              class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              :placeholder="channel ? '留空表示不修改' : '123456:ABC…'"
            >
          </label>

          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">接收群聊</span>
            <select
              v-model="form.groupId"
              class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
            >
              <option value="">请选择群聊</option>
              <option v-for="group in groupsStore.groups" :key="group.id" :value="group.id">{{ group.name }}</option>
            </select>
          </label>

          <label class="block">
            <span class="block text-[13px] font-[var(--weight-medium)] text-[var(--color-text)] mb-1.5">
              Chat ID（可选，限定来源）
            </span>
            <input
              v-model="form.chatId"
              type="text"
              class="w-full h-[38px] px-3 rounded-[var(--radius-md)] bg-[var(--color-surface-overlay)] border-0.5 border-[var(--color-line-strong)] text-[14px] text-[var(--color-text)] outline-none focus-visible:shadow-[var(--p-focus-ring)]"
              placeholder="例如 -1001234567890"
            >
          </label>

          <label class="flex items-center gap-2 text-[13px] text-[var(--color-text)]">
            <input v-model="form.enabled" type="checkbox" class="accent-[var(--color-accent)]">
            启用
          </label>

          <p v-if="formError" class="text-[13px] text-[var(--color-danger)]" role="alert">{{ formError }}</p>
        </div>

        <footer class="px-5 py-3.5 flex items-center justify-end gap-2.5 border-t border-[var(--color-line)]">
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
