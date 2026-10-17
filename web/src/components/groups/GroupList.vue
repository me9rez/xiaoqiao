<script setup lang="ts">
import { Plus, Users } from '@lucide/vue'
import { useRoute } from 'vue-router'

import { useGroupsStore } from '@/stores/groups'
import type { Group } from '@/types/group'

const emit = defineEmits<{ create: []; edit: [group: Group] }>()

const groupsStore = useGroupsStore()
const route = useRoute()

function isActive(groupId: string): boolean {
  return route.name === 'group' && route.params.groupId === groupId
}
</script>

<template>
  <section class="px-3 py-2">
    <div class="flex items-center gap-1.5 px-2 py-2 text-xs font-bold text-[var(--color-text-faint)]">
      <Users class="w-3.5 h-3.5" />
      <span class="flex-1">群聊</span>
      <button
        type="button"
        class="p-0.5 rounded hover:bg-[var(--color-hover)] text-[var(--color-text-muted)]"
        aria-label="新建群聊"
        title="新建群聊"
        @click="emit('create')"
      >
        <Plus class="w-3.5 h-3.5" />
      </button>
    </div>

    <div v-if="groupsStore.loading" class="px-3 py-2 text-[13px] text-[var(--color-text-muted)]">加载中…</div>
    <div v-else-if="groupsStore.groups.length === 0" class="px-3 py-2 text-[13px] text-[var(--color-text-muted)]">
      还没有群聊
    </div>

    <template v-else>
      <RouterLink
        v-for="group in groupsStore.groups"
        :key="group.id"
      :to="{ name: 'group', params: { groupId: group.id } }"
      class="flex items-center gap-2 px-3 py-1.5 rounded-[var(--radius-md)] text-[14px] transition-colors duration-[var(--duration-base)]"
        :class="
          isActive(group.id)
            ? 'bg-[var(--color-selected)] text-[var(--color-text)] font-[var(--weight-medium)]'
            : 'text-[var(--color-text-muted)] hover:bg-[var(--color-hover)]'
        "
        @dblclick.prevent="emit('edit', group)"
      >
        <span class="text-[13px]" aria-hidden="true">#</span>
        <span class="truncate flex-1">{{ group.name }}</span>
        <span class="text-[11px] text-[var(--color-text-faint)]">{{ group.botIds.length }}</span>
      </RouterLink>
    </template>
  </section>
</template>
