<script setup lang="ts">
import { Check, ChevronDown, ListTree } from '@lucide/vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { gatewayService } from '@/services/gateway'
import { useSettingsStore } from '@/stores/settings'
import { activeEffort, buildModelChoices, effortLabel } from '@/utils/models'
import ModelPickerModal from './ModelPickerModal.vue'

const props = withDefaults(
  defineProps<{
    /** Current model alias; falls back to `default_model` when empty. */
    value: string
    placement?: 'bottom' | 'top'
  }>(),
  { placement: 'bottom' },
)

const emit = defineEmits<{
  change: [alias: string]
}>()

const store = useSettingsStore()
const open = ref(false)
const modalOpen = ref(false)
const rootRef = ref<HTMLDivElement | null>(null)
const popoverRef = ref<HTMLDivElement | null>(null)
const pos = ref({ left: 0, top: 0, bottom: 0, placeAbove: false })

let unsubscribeOpen: (() => void) | null = null

const choices = computed(() => buildModelChoices(store.settings))
const current = computed(() => props.value || store.settings.default_model)
const currentChoice = computed(() => choices.value.find((model) => model.alias === current.value))
const effort = computed(() => activeEffort(store.settings, current.value))

/** The reference popover only lists the current provider's models. */
const siblings = computed(() =>
  currentChoice.value ? choices.value.filter((model) => model.provider === currentChoice.value?.provider) : choices.value,
)

function toggle() {
  open.value = !open.value
  if (!open.value) return
  const button = rootRef.value?.querySelector('button')
  if (!button) return
  const rect = button.getBoundingClientRect()
  const placeAbove = props.placement === 'top' || window.innerHeight - rect.bottom < 320
  pos.value = {
    left: Math.max(12, Math.min(rect.left, window.innerWidth - 300)),
    top: rect.bottom + 6,
    bottom: window.innerHeight - rect.top + 6,
    placeAbove,
  }
}

function pick(alias: string) {
  open.value = false
  modalOpen.value = false
  if (alias === current.value) return
  emit('change', alias)
}

function openModal() {
  open.value = false
  modalOpen.value = true
}

function setEffort(value: string | null) {
  void store.setThinkingEffort(value)
}

/**
 * The popover is teleported to `body`, so `rootRef` alone would treat a mousedown
 * inside it as "outside" and unmount the popover before the click lands.
 */
function handleClickOutside(event: MouseEvent) {
  const target = event.target as Node
  if (rootRef.value?.contains(target) || popoverRef.value?.contains(target)) return
  open.value = false
}

function handleWindowChange() {
  open.value = false
}

onMounted(() => {
  store.ensureLoaded()
  unsubscribeOpen = gatewayService.on('open', () => {
    store.ensureLoaded()
  })
  document.addEventListener('mousedown', handleClickOutside)
  window.addEventListener('resize', handleWindowChange)
  window.addEventListener('scroll', handleWindowChange, true)
})

onUnmounted(() => {
  unsubscribeOpen?.()
  document.removeEventListener('mousedown', handleClickOutside)
  window.removeEventListener('resize', handleWindowChange)
  window.removeEventListener('scroll', handleWindowChange, true)
})
</script>

<template>
  <div ref="rootRef" class="relative">
    <button
      type="button"
      class="flex max-w-64 items-center gap-1.5 rounded-[var(--radius-md)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-raised)] px-2.5 py-1.5 text-[12px] text-[var(--color-text-muted)] transition hover:border-[var(--color-line-strong)] hover:text-[var(--color-text)]"
      :aria-expanded="open"
      aria-haspopup="dialog"
      @click="toggle"
    >
      <span class="truncate">{{ currentChoice?.name || '选择模型' }}</span>
      <span v-if="effort" class="flex-shrink-0 text-[var(--color-accent)]">· {{ effortLabel(effort) }}</span>
      <ChevronDown class="h-3.5 w-3.5 flex-shrink-0 transition" :class="open ? 'rotate-180' : ''" />
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        ref="popoverRef"
        class="fixed z-40 w-72 overflow-hidden rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)] bg-[var(--color-surface-overlay)] shadow-[var(--shadow-menu)]"
        :style="pos.placeAbove
          ? { left: pos.left + 'px', bottom: pos.bottom + 'px' }
          : { left: pos.left + 'px', top: pos.top + 'px' }"
      >
        <p class="px-3 pb-1 pt-2.5 text-[13px] font-medium text-[var(--color-text-muted)]">
          {{ currentChoice?.provider || '模型' }}
        </p>

        <div class="pb-1">
          <button
            v-for="model in siblings"
            :key="model.alias"
            type="button"
            class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] transition hover:bg-[var(--color-hover)]"
            :class="model.alias === current ? 'bg-[var(--color-selected)] text-[var(--color-text-strong)]' : 'text-[var(--color-text)]'"
            :title="model.subtitle"
            @click="pick(model.alias)"
          >
            <span class="min-w-0 flex-1 truncate">{{ model.name }}</span>
            <Check v-if="model.alias === current" class="h-4 w-4 flex-shrink-0 text-[var(--color-accent)]" />
          </button>
        </div>

        <div
          v-if="currentChoice && currentChoice.efforts.length"
          class="flex items-center justify-between border-t-[0.5px] border-[var(--color-line)] px-3 py-2"
        >
          <span class="text-[13px] text-[var(--color-text)]">思考</span>
          <div class="flex items-center gap-1">
            <button
              type="button"
              class="h-6 rounded-[var(--radius-sm)] px-2 text-[12px] transition"
              :class="store.settings.thinking.effort === null
                ? 'bg-[var(--color-send-bg)] text-[var(--color-send-icon)]'
                : 'bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-hover)]'"
              title="不固定档位，跟随每个模型自己的 default_effort"
              @click="setEffort(null)"
            >
              默认
            </button>
            <button
              v-for="value in currentChoice.efforts"
              :key="value"
              type="button"
              class="h-6 rounded-[var(--radius-sm)] px-2 text-[12px] transition"
              :class="store.settings.thinking.effort === value
                ? 'bg-[var(--color-send-bg)] text-[var(--color-send-icon)]'
                : 'bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-hover)]'"
              @click="setEffort(value)"
            >
              {{ effortLabel(value) }}
            </button>
          </div>
        </div>

        <p class="border-t-[0.5px] border-[var(--color-line)] px-3 py-2 text-[12px] leading-[1.6] text-[var(--color-text-faint)]">
          提示：切换模型或思考档位会使已有的提示词缓存失效。建议新建会话，避免额外的 token 消耗。
        </p>

        <button
          type="button"
          class="flex w-full items-center gap-2 border-t-[0.5px] border-[var(--color-line)] px-3 py-2.5 text-[13px] text-[var(--color-text)] transition hover:bg-[var(--color-hover)]"
          @click="openModal"
        >
          <ListTree class="h-4 w-4 text-[var(--color-text-muted)]" />
          更多模型…
        </button>
      </div>
    </Teleport>

    <ModelPickerModal
      :open="modalOpen"
      :models="choices"
      :current="current"
      @select="pick"
      @close="modalOpen = false"
    />
  </div>
</template>
