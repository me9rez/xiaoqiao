<script setup lang="ts">
import { Plus, Send } from '@lucide/vue'
import { onMounted, ref, watch } from 'vue'

import ChannelEditorModal from '@/components/channels/ChannelEditorModal.vue'
import { useBotsStore } from '@/stores/bots'
import { useChannelsStore } from '@/stores/channels'
import { useGroupsStore } from '@/stores/groups'
import type { Channel } from '@/types/channel'

const botsStore = useBotsStore()
const groupsStore = useGroupsStore()
const channelsStore = useChannelsStore()

const editorOpen = ref(false)
const editing = ref<Channel | null>(null)

function groupName(groupId: unknown): string {
  if (typeof groupId !== 'string' || !groupId) return '未绑定'
  return groupsStore.groups.find((group) => group.id === groupId)?.name ?? '群聊已删除'
}

async function reload() {
  const botId = botsStore.activeBotId
  if (botId) await channelsStore.load(botId)
}

function openEditor(channel: Channel | null) {
  editing.value = channel
  editorOpen.value = true
}

function closeEditor() {
  editorOpen.value = false
  editing.value = null
}

async function removeChannel(channel: Channel) {
  if (!window.confirm('删除这个频道？Telegram 将不再接收消息。')) return
  await channelsStore.remove(channel.id)
}

watch(
  () => botsStore.activeBotId,
  () => void reload(),
)

onMounted(async () => {
  if (botsStore.bots.length === 0) await botsStore.load()
  if (groupsStore.groups.length === 0) await groupsStore.load()
  await reload()
})
</script>

<template>
  <div class="p-8 max-w-3xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-[20px] font-[var(--weight-semibold)] text-[var(--color-text-strong)]">频道</h1>
        <p class="mt-1 text-[13px] text-[var(--color-text-muted)]">
          当前 Bot：{{ botsStore.activeBot?.name || '未选择' }}。消息从 Telegram 进来，@ 路由与网页一致。
        </p>
      </div>
      <button
        type="button"
        class="flex items-center gap-1.5 h-[36px] px-4 rounded-[var(--radius-md)] text-[14px] font-[var(--weight-medium)] text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)]"
        @click="openEditor(null)"
      >
        <Plus class="w-4 h-4" />
        接入
      </button>
    </div>

    <p v-if="channelsStore.error" class="mb-4 text-[13px] text-[var(--color-danger)]" role="alert">
      {{ channelsStore.error }}
    </p>

    <div v-if="channelsStore.loading" class="text-[13px] text-[var(--color-text-muted)]">加载中…</div>

    <div
      v-else-if="channelsStore.items.length === 0"
      class="py-16 text-center text-[13px] text-[var(--color-text-muted)]"
    >
      <Send class="w-10 h-10 mx-auto mb-3 text-[var(--color-text-faint)]" />
      还没有接入频道。接一个 Telegram 群，Bot 就能在手机上继续干活。
    </div>

    <div v-else class="space-y-3">
      <article
        v-for="channel in channelsStore.items"
        :key="channel.id"
        class="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]"
      >
        <div class="flex items-center gap-2">
          <Send class="w-4 h-4 text-[var(--color-text-muted)]" />
          <span class="text-[14px] font-[var(--weight-medium)] text-[var(--color-text-strong)]">
            {{ channel.kind === 'telegram' ? 'Telegram' : channel.kind }}
          </span>
          <span class="text-[12px] text-[var(--color-text-muted)]">→ {{ groupName(channel.config.groupId) }}</span>
          <span
            class="px-2 py-0.5 rounded-full text-[11px] border"
            :class="
              channel.enabled
                ? 'text-[var(--color-success)] bg-[var(--color-success-soft)] border-[var(--color-success-bd)]'
                : 'text-[var(--color-text-muted)] bg-[var(--color-surface)] border-[var(--color-line)]'
            "
          >
            {{ channel.enabled ? '已启用' : '已停用' }}
          </span>
          <span class="flex-1" />
          <button
            type="button"
            class="h-[30px] px-3 rounded-[var(--radius-md)] text-[13px] border-0.5 border-[var(--color-line-strong)] text-[var(--color-text)] hover:bg-[var(--color-hover)]"
            @click="openEditor(channel)"
          >
            编辑
          </button>
          <button
            type="button"
            class="h-[30px] px-3 rounded-[var(--radius-md)] text-[13px] text-[var(--color-text-muted)] hover:bg-[var(--color-hover)]"
            @click="channelsStore.toggle(channel.id, !channel.enabled)"
          >
            {{ channel.enabled ? '停用' : '启用' }}
          </button>
          <button
            type="button"
            class="h-[30px] px-3 rounded-[var(--radius-md)] text-[13px] text-[var(--color-danger)] hover:bg-[var(--color-danger-soft)]"
            @click="removeChannel(channel)"
          >
            删除
          </button>
        </div>

        <div class="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[12px] text-[var(--color-text-muted)]">
          <span>Chat ID：{{ channel.config.chatId || '不限' }}</span>
          <span>Token：{{ channel.config.token === '***' ? '已保存' : '未保存' }}</span>
        </div>
      </article>
    </div>

    <ChannelEditorModal :open="editorOpen" :channel="editing" @close="closeEditor" />
  </div>
</template>
