<script setup lang="ts">
import { computed, ref } from 'vue'

import { bridgeCall } from '@/services/endpoint'
import { useBootStore } from '@/stores/boot'

const boot = useBootStore()
const showLog = ref(false)

const visible = computed(() => boot.phase !== 'ready')
const isError = computed(() => boot.phase === 'error')
const logText = computed(() => boot.engineLog.slice(-14).join('\n'))

function openDataDir(): void {
  void bridgeCall()?.('openDataDir')
}
</script>

<template>
  <div v-if="visible" class="boot" role="status" aria-live="polite">
    <div class="boot-card">
      <div class="boot-brand">小巧</div>

      <template v-if="!isError">
        <div class="boot-spinner" aria-hidden="true"></div>
        <p class="boot-title">正在启动本地引擎…</p>
        <p class="boot-hint">首次启动需要加载 Python 运行时，通常几秒内完成。</p>
      </template>

      <template v-else>
        <p class="boot-title boot-title-error">本地引擎没能启动</p>
        <p class="boot-detail">{{ boot.detail }}</p>
        <pre v-if="showLog && logText" class="boot-log">{{ logText }}</pre>
        <div class="boot-actions">
          <button class="boot-btn boot-btn-primary" type="button" :disabled="boot.restarting" @click="boot.retry()">
            {{ boot.restarting ? '重启中…' : '重试' }}
          </button>
          <button class="boot-btn" type="button" @click="showLog = !showLog">
            {{ showLog ? '隐藏日志' : '查看日志' }}
          </button>
          <button class="boot-btn" type="button" @click="openDataDir">打开数据目录</button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.boot {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-page);
}

.boot-card {
  display: flex;
  max-width: 460px;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 32px;
  text-align: center;
}

.boot-brand {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0.02em;
}

.boot-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid var(--border);
  border-top-color: var(--text);
  border-radius: var(--radius-full);
  animation: boot-spin 0.9s linear infinite;
}

@keyframes boot-spin {
  to {
    transform: rotate(360deg);
  }
}

.boot-title {
  font-size: var(--text-base);
  color: var(--text);
}

.boot-title-error {
  color: var(--color-danger);
}

.boot-hint {
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.boot-detail {
  max-width: 100%;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-muted);
  word-break: break-word;
}

.boot-log {
  max-height: 200px;
  width: 100%;
  overflow: auto;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-muted);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-subtle);
  text-align: left;
  white-space: pre-wrap;
}

.boot-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.boot-btn {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.boot-btn:hover:not(:disabled) {
  background: var(--bg-muted);
}

.boot-btn:disabled {
  cursor: default;
  opacity: 0.6;
}

.boot-btn-primary {
  border-color: var(--color-danger-bd);
  background: var(--color-danger-soft);
  color: var(--color-danger);
}
</style>
