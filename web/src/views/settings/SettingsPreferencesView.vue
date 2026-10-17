<script setup lang="ts">
import { Monitor, Moon, Sun } from '@lucide/vue'
import { ref, type Component } from 'vue'

import {
  getColorScheme,
  getFontScale,
  setColorScheme,
  setFontScale,
  type ColorScheme,
  type FontScale,
} from '../../theme'

const colorScheme = ref<ColorScheme>(getColorScheme())
const fontScale = ref<FontScale>(getFontScale())

const schemeOptions: { value: ColorScheme; label: string; desc: string; icon: Component }[] = [
  { value: 'light', label: '浅色', desc: '白底，适合白天', icon: Sun },
  { value: 'dark', label: '深色', desc: '深底，适合夜间', icon: Moon },
  { value: 'system', label: '跟随系统', desc: '随系统外观自动切换', icon: Monitor },
]

const scaleOptions: { value: FontScale; label: string; size: string }[] = [
  { value: 'small', label: '小', size: '12px' },
  { value: 'medium', label: '标准', size: '14px' },
  { value: 'large', label: '大', size: '16px' },
  { value: 'xlarge', label: '超大', size: '18px' },
]

function chooseScheme(value: ColorScheme) {
  colorScheme.value = value
  setColorScheme(value)
}

function chooseScale(value: FontScale) {
  fontScale.value = value
  setFontScale(value)
}
</script>

<template>
  <div class="p-8 max-w-3xl mx-auto">
    <div class="mb-6">
      <h1 class="text-xl font-semibold">
        偏好
      </h1>
      <p class="text-sm text-[var(--color-text-muted)] mt-1">
        外观与可读性设置，保存在本地，仅影响这台设备
      </p>
    </div>

    <section class="rounded-2xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-6 shadow-[var(--shadow-xs)] mb-4">
      <h2 class="font-medium mb-1">
        外观
      </h2>
      <p class="text-sm text-[var(--color-text-muted)] mb-4">
        深色主题单独定义了表面层级与阴影，不是浅色的简单反色
      </p>

      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3" role="radiogroup" aria-label="外观">
        <button
          v-for="option in schemeOptions"
          :key="option.value"
          type="button"
          role="radio"
          :aria-checked="colorScheme === option.value"
          class="text-left rounded-xl border p-4 transition-colors duration-160"
          :class="colorScheme === option.value
            ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)]'
            : 'border-[var(--color-line)] hover:bg-[var(--color-hover)]'"
          @click="chooseScheme(option.value)"
        >
          <div class="flex items-center gap-2 mb-2">
            <component :is="option.icon" class="w-4 h-4" />
            <span class="font-medium">{{ option.label }}</span>
          </div>
          <p class="text-xs text-[var(--color-text-muted)]">
            {{ option.desc }}
          </p>
        </button>
      </div>
    </section>

    <section class="rounded-2xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-6 shadow-[var(--shadow-xs)] mb-4">
      <h2 class="font-medium mb-1">
        字号
      </h2>
      <p class="text-sm text-[var(--color-text-muted)] mb-4">
        界面整体缩放，代码块同步变化
      </p>

      <div class="inline-flex gap-0.5 p-0.5 rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-surface-sunken)]" role="radiogroup" aria-label="字号">
        <button
          v-for="option in scaleOptions"
          :key="option.value"
          type="button"
          role="radio"
          :aria-checked="fontScale === option.value"
          class="px-3 py-1.5 rounded-[var(--radius-sm)] text-[var(--text-sm)] transition-colors duration-120"
          :class="fontScale === option.value
            ? 'bg-[var(--color-surface-raised)] shadow-[var(--shadow-sm)] text-[var(--color-text)]'
            : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'"
          @click="chooseScale(option.value)"
        >
          {{ option.label }}
          <span class="text-[var(--color-text-faint)]">{{ option.size }}</span>
        </button>
      </div>

      <div class="mt-4 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-4">
        <p class="text-[var(--text-base)]">
          这是一段预览文字。工具调用、思考过程和最终回答都会跟随这个字号。
        </p>
        <p class="mt-2 text-[var(--text-sm)] text-[var(--color-text-muted)]">
          次要信息使用 muted 层级，不靠降低透明度实现。
        </p>
        <pre class="mono mt-3 text-[var(--text-sm)] text-[var(--color-text-muted)]">$ xiaoqiao --web</pre>
      </div>
    </section>

    <p class="text-xs text-[var(--color-text-faint)]">
      存储键：<code class="mono">xiaoqiao:color-scheme</code> · <code class="mono">xiaoqiao:font-scale</code>（旧 <code class="mono">coding-agent:*</code> 会在首次读取时自动迁移）
    </p>
  </div>
</template>
