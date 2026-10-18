import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { gatewayService } from '@/services/gateway'
import type { Group, GroupDraft, GroupMessage } from '@/types/group'
import { isGroupMessageCreatedEvent } from '@/types/gateway'

export const useGroupsStore = defineStore('groups', () => {
  const groups = ref<Group[]>([])
  const messages = ref<Map<string, GroupMessage[]>>(new Map())
  const activeGroupId = ref<string | null>(null)
  const loading = ref(false)
  const sending = ref(false)
  const error = ref<string | null>(null)

  let unsubscribe: (() => void) | null = null

  const activeGroup = computed(() => groups.value.find((group) => group.id === activeGroupId.value) ?? null)

  function messagesFor(groupId: string): GroupMessage[] {
    return messages.value.get(groupId) ?? []
  }

  function ensureMessages(groupId: string): GroupMessage[] {
    let list = messages.value.get(groupId)
    if (!list) {
      list = []
      messages.value.set(groupId, list)
    }
    return list
  }

  function selectGroup(groupId: string | null): void {
    activeGroupId.value = groupId
    if (groupId) {
      messages.value.set(groupId, messages.value.get(groupId) ?? [])
    }
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      groups.value = await gatewayService.call<Group[]>('listGroups')
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  async function loadMessages(groupId: string): Promise<void> {
    error.value = null
    try {
      const items = await gatewayService.call<GroupMessage[]>('listGroupMessages', { groupId, limit: 200 })
      messages.value.set(groupId, items)
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    }
  }

  async function create(draft: GroupDraft): Promise<Group | null> {
    error.value = null
    try {
      const group = await gatewayService.call<Group>('createGroup', {
        name: draft.name,
        botIds: draft.botIds,
        defaultBotId: draft.defaultBotId ?? draft.botIds[0] ?? null,
        settings: draft.settings ?? {},
      })
      groups.value = [group, ...groups.value]
      selectGroup(group.id)
      return group
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  async function update(groupId: string, patch: Partial<GroupDraft>): Promise<Group | null> {
    error.value = null
    try {
      const group = await gatewayService.call<Group>('updateGroup', { groupId, ...patch })
      groups.value = groups.value.map((item) => (item.id === group.id ? group : item))
      return group
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  async function remove(groupId: string): Promise<boolean> {
    error.value = null
    try {
      const result = await gatewayService.call<{ ok: boolean }>('deleteGroup', { groupId })
      if (!result.ok) return false
      groups.value = groups.value.filter((group) => group.id !== groupId)
      messages.value.delete(groupId)
      if (activeGroupId.value === groupId) selectGroup(null)
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return false
    }
  }

  function sendMessage(groupId: string, text: string): void {
    const trimmed = text.trim()
    if (!trimmed || sending.value) return
    sending.value = true
    error.value = null
    gatewayService.sendGroupMessage(groupId, trimmed)
  }

  function receive(message: GroupMessage): void {
    const list = ensureMessages(message.groupId)
    if (list.some((item) => item.id === message.id)) return
    list.push(message)
    list.sort((a, b) => a.seq - b.seq)
    if (message.authorType !== 'user') {
      sending.value = false
    }
  }

  function listen(): () => void {
    if (unsubscribe) return unsubscribe
    unsubscribe = gatewayService.on('group_message_created', (event) => {
      if (isGroupMessageCreatedEvent(event)) {
        receive(event.message as GroupMessage)
      }
    })
    // A run can end without producing a message at all (empty reply / failure that
    // the gateway reports only in logs), so the composer must not stay in "sending".
    const stopOnDone = gatewayService.on('done', () => {
      sending.value = false
    })
    const stopOnError = gatewayService.on('error', () => {
      sending.value = false
    })
    return () => {
      unsubscribe?.()
      unsubscribe = null
      stopOnDone()
      stopOnError()
    }
  }

  return {
    groups,
    messages,
    activeGroupId,
    activeGroup,
    loading,
    sending,
    error,
    messagesFor,
    selectGroup,
    load,
    loadMessages,
    create,
    update,
    remove,
    sendMessage,
    receive,
    listen,
  }
})
