import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  bridgeCall,
  isDesktop,
  onEngineStatus,
  resolveGatewayEndpoint,
  type EngineStatus,
} from '@/services/endpoint'
import { gatewayService } from '@/services/gateway'

export type BootPhase = 'booting' | 'ready' | 'error'

const CONNECT_TIMEOUT_MS = 20_000

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

/**
 * Boot state for the desktop shell.
 *
 * In a browser the gateway URL is a constant, so the app is usable from the
 * first paint. In the desktop shell the engine has to come up first, and a
 * failure there must be visible instead of leaving a blank window.
 */
export const useBootStore = defineStore('boot', () => {
  const phase = ref<BootPhase>(isDesktop() ? 'booting' : 'ready')
  const detail = ref('')
  const engineLog = ref<string[]>([])
  const restarting = ref(false)

  let subscribed = false

  function applyStatus(status: EngineStatus): void {
    engineLog.value = status.log.slice(-60)
    if (status.state === 'stopped' && status.lastExit) {
      fail(`本地引擎已退出（code ${status.lastExit.code ?? '?'}）`)
    }
  }

  function subscribe(): void {
    if (subscribed) return
    subscribed = true
    onEngineStatus(applyStatus)
  }

  function fail(message: string): void {
    phase.value = 'error'
    detail.value = message
  }

  function markReady(): void {
    phase.value = 'ready'
    detail.value = ''
  }

  /** Wait until the gateway answered the handshake (`open`) or gave up. */
  function waitForConnection(): Promise<void> {
    if (gatewayService.isConnected()) return Promise.resolve()
    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        cleanup()
        reject(new Error(`连接超时（${CONNECT_TIMEOUT_MS / 1000}s）`))
      }, CONNECT_TIMEOUT_MS)
      const offOpen = gatewayService.on('open', () => {
        cleanup()
        resolve()
      })
      const offFailed = gatewayService.on('auth_failed', () => {
        cleanup()
        reject(new Error('鉴权失败：页面与引擎的 token 不一致'))
      })
      function cleanup(): void {
        clearTimeout(timer)
        offOpen()
        offFailed()
      }
    })
  }

  async function start(): Promise<void> {
    if (!isDesktop()) {
      gatewayService.connect()
      return
    }
    subscribe()
    phase.value = 'booting'
    try {
      const endpoint = await resolveGatewayEndpoint()
      gatewayService.connect(endpoint)
      await waitForConnection()
      markReady()
    } catch (error) {
      fail(describe(error))
    }
  }

  /** Ask the shell to restart the engine, then reconnect. */
  async function retry(): Promise<void> {
    if (restarting.value) return
    restarting.value = true
    phase.value = 'booting'
    detail.value = ''
    try {
      const call = bridgeCall()
      if (call) await call('restartEngine')
      gatewayService.close()
      await start()
    } catch (error) {
      fail(describe(error))
    } finally {
      restarting.value = false
    }
  }

  return { phase, detail, engineLog, restarting, start, retry, markReady, fail }
})
