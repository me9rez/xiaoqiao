<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { useApprovalsStore } from '@/stores/approvals'
import { useBotsStore } from '@/stores/bots'
import type { Approval } from '@/types/approval'

const approvalsStore = useApprovalsStore()
const botsStore = useBotsStore()
const tab = ref<'pending' | 'all'>('pending')

const visible = computed(() =>
  tab.value === 'pending' ? approvalsStore.pending : approvalsStore.items,
)

function botName(botId: string): string {
  return botsStore.bots.find((bot) => bot.id === botId)?.name ?? 'Bot'
}

function statusLabel(status: Approval['status']): string {
  return { pending: '待处理', approved: '已批准', denied: '已拒绝', expired: '已过期' }[status]
}

function statusClass(status: Approval['status']): string {
  if (status === 'pending') return 'text-[var(--color-warning)] bg-[var(--color-warning-soft)] border-[var(--color-warning-bd)]'
  if (status === 'approved') return 'text-[var(--color-success)] bg-[var(--color-success-soft)] border-[var(--color-success-bd)]'
  if (status === 'denied') return 'text-[var(--color-danger)] bg-[var(--color-danger-soft)] border-[var(--color-danger-bd)]'
  return 'text-[var(--color-text-muted)] bg-[var(--color-surface)] border-[var(--color-line)]'
}

function expiresLabel(approval: Approval): string {
  const date = new Date(approval.expiresAt)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

async function resolve(approval: Approval, approved: boolean) {
  await approvalsStore.resolve(approval.id, approved)
}

onMounted(() => {
  void approvalsStore.load()
  if (botsStore.bots.length === 0) void botsStore.load()
})
</script>

<template>
  <div class="h-full overflow-y-auto p-8 max-w-3xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-[20px] font-[var(--weight-semibold)] text-[var(--color-text-strong)]">审批</h1>
        <p class="mt-1 text-[13px] text-[var(--color-text-muted)]">
          危险工具会在这里等你确认；Bot 之间不能互相批准。
        </p>
      </div>
      <div class="flex items-center gap-1 p-0.5 rounded-[var(--radius-md)] bg-[var(--color-surface-sunken)] border border-[var(--color-line)]">
        <button
          v-for="option in (['pending', 'all'] as const)"
          :key="option"
          type="button"
          class="px-3 py-1 rounded-[var(--radius-sm)] text-[13px] transition-colors duration-[var(--duration-fast)]"
          :class="
            tab === option
              ? 'bg-[var(--color-surface-raised)] shadow-[var(--shadow-sm)] text-[var(--color-text)]'
              : 'text-[var(--color-text-muted)]'
          "
          @click="tab = option"
        >
          {{ option === 'pending' ? `待处理 ${approvalsStore.pendingCount}` : '全部' }}
        </button>
      </div>
    </div>

    <p v-if="approvalsStore.error" class="mb-4 text-[13px] text-[var(--color-danger)]" role="alert">
      {{ approvalsStore.error }}
    </p>

    <div v-if="approvalsStore.loading" class="text-[13px] text-[var(--color-text-muted)]">加载中…</div>
    <div v-else-if="visible.length === 0" class="py-16 text-center text-[13px] text-[var(--color-text-muted)]">
      没有待处理的审批。
    </div>

    <div v-else class="space-y-3">
      <article
        v-for="approval in visible"
        :key="approval.id"
        class="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-sm)]"
      >
        <div class="flex items-center gap-2">
          <span class="text-[14px] font-[var(--weight-medium)] text-[var(--color-text-strong)]">
            {{ approval.tool }}
          </span>
          <span class="text-[12px] text-[var(--color-text-muted)]">{{ botName(approval.botId) }}</span>
          <span class="flex-1" />
          <span
            class="px-2 py-0.5 rounded-full text-[11px] border"
            :class="statusClass(approval.status)"
          >
            {{ statusLabel(approval.status) }}
          </span>
        </div>

        <pre
          class="mt-2.5 p-2.5 rounded-[var(--radius-md)] bg-[var(--color-surface)] text-[12px] leading-relaxed text-[var(--color-text-muted)] overflow-x-auto"
        >{{ JSON.stringify(approval.arguments, null, 2) }}</pre>

        <div class="mt-3 flex items-center gap-2">
          <span class="text-[12px] text-[var(--color-text-faint)]">有效至 {{ expiresLabel(approval) }}</span>
          <span class="flex-1" />
          <template v-if="approval.status === 'pending'">
            <button
              type="button"
              class="h-[30px] px-3 rounded-[var(--radius-md)] text-[13px] text-[var(--color-text)] bg-[var(--color-surface-raised)] border-0.5 border-[var(--color-line-strong)] hover:bg-[var(--color-hover)]"
              @click="resolve(approval, false)"
            >
              拒绝
            </button>
            <button
              type="button"
              class="h-[30px] px-3 rounded-[var(--radius-md)] text-[13px] font-[var(--weight-medium)] text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)]"
              @click="resolve(approval, true)"
            >
              批准
            </button>
          </template>
        </div>
      </article>
    </div>
  </div>
</template>
