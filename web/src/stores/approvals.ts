import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { gatewayService } from '@/services/gateway'
import type { Approval, ApprovalStatus } from '@/types/approval'
import { isApprovalRequestedEvent, isApprovalResolvedEvent } from '@/types/gateway'

function parseArguments(raw: unknown): Record<string, unknown> {
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw) as Record<string, unknown>
    } catch {
      return { raw }
    }
  }
  if (raw && typeof raw === 'object') return raw as Record<string, unknown>
  return {}
}

export const useApprovalsStore = defineStore('approvals', () => {
  const items = ref<Approval[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let unsubscribe: (() => void) | null = null

  const pending = computed(() => items.value.filter((item) => item.status === 'pending'))
  const pendingCount = computed(() => pending.value.length)

  function upsert(approval: Approval): void {
    const index = items.value.findIndex((item) => item.id === approval.id)
    if (index >= 0) items.value[index] = approval
    else items.value = [approval, ...items.value]
  }

  function applyResolution(approvalId: string, status: ApprovalStatus): void {
    const item = items.value.find((candidate) => candidate.id === approvalId)
    if (item) {
      item.status = status
      item.resolvedAt = new Date().toISOString()
    }
  }

  async function load(status?: ApprovalStatus): Promise<void> {
    loading.value = true
    error.value = null
    try {
      items.value = await gatewayService.call<Approval[]>('listApprovals', status ? { status } : {})
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  async function resolve(approvalId: string, approved: boolean): Promise<boolean> {
    error.value = null
    try {
      await gatewayService.call<{ ok: boolean; status: string }>('resolveApproval', { approvalId, approved })
      applyResolution(approvalId, approved ? 'approved' : 'denied')
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return false
    }
  }

  function listen(): () => void {
    if (unsubscribe) return unsubscribe
    const offRequested = gatewayService.on('approval_requested', (event) => {
      if (!isApprovalRequestedEvent(event)) return
      upsert({
        id: event.approvalId,
        runId: event.runId,
        callId: event.callId,
        botId: event.botId,
        groupId: event.groupId,
        tool: event.tool,
        arguments: parseArguments(event.arguments),
        status: 'pending',
        createdAt: new Date().toISOString(),
        expiresAt: event.expiresAt,
        resolvedAt: null,
        resolvedBy: null,
      })
    })
    const offResolved = gatewayService.on('approval_resolved', (event) => {
      if (isApprovalResolvedEvent(event)) applyResolution(event.approvalId, event.status)
    })
    unsubscribe = () => {
      offRequested()
      offResolved()
    }
    return unsubscribe
  }

  return { items, pending, pendingCount, loading, error, load, resolve, upsert, applyResolution, listen }
})
