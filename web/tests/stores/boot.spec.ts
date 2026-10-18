import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { gatewayService } from '@/services/gateway'
import { useBootStore } from '@/stores/boot'

type TinyWindow = { tiny?: { api?: { call?: unknown; on?: unknown } } }

function installBridge(call: unknown) {
  ;(globalThis as unknown as TinyWindow).tiny = { api: { call, on: () => () => {} } }
}

describe('boot store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // The engine never completes a real handshake inside jsdom.
    vi.spyOn(gatewayService, 'isConnected').mockReturnValue(true)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    delete (globalThis as unknown as TinyWindow).tiny
  })

  it('starts ready in a browser and connects to the default endpoint', () => {
    const connect = vi.spyOn(gatewayService, 'connect').mockImplementation(() => {})
    const boot = useBootStore()

    expect(boot.phase).toBe('ready')
    void boot.start()
    expect(connect).toHaveBeenCalledOnce()
    expect(connect.mock.calls[0]).toHaveLength(0)
  })

  it('waits for the engine in the desktop shell', async () => {
    installBridge(vi.fn().mockResolvedValue({ url: 'ws://127.0.0.1:4321', token: 'tok' }))
    const connect = vi.spyOn(gatewayService, 'connect').mockImplementation(() => {})
    const boot = useBootStore()

    expect(boot.phase).toBe('booting')
    await boot.start()

    expect(connect).toHaveBeenCalledWith({ url: 'ws://127.0.0.1:4321', token: 'tok' })
    expect(boot.phase).toBe('ready')
  })

  it('shows the engine failure instead of a blank window', async () => {
    installBridge(vi.fn().mockRejectedValue(new Error('engine exited (1)')))
    const boot = useBootStore()

    await boot.start()

    expect(boot.phase).toBe('error')
    expect(boot.detail).toContain('engine exited (1)')
  })

  it('retry asks the shell to restart the engine, then reconnects', async () => {
    const call = vi
      .fn()
      .mockRejectedValueOnce(new Error('engine exited (1)'))
      .mockResolvedValueOnce(undefined) // restartEngine
      .mockResolvedValueOnce({ url: 'ws://127.0.0.1:4321', token: 'tok' })
    installBridge(call)
    vi.spyOn(gatewayService, 'connect').mockImplementation(() => {})
    vi.spyOn(gatewayService, 'close').mockImplementation(() => {})
    const boot = useBootStore()

    await boot.start()
    expect(boot.phase).toBe('error')

    await boot.retry()

    expect(call).toHaveBeenCalledWith('restartEngine')
    expect(boot.phase).toBe('ready')
    expect(boot.restarting).toBe(false)
  })
})
