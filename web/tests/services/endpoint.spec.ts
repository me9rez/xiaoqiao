import { afterEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_WS_URL, isDesktop, onEngineStatus, resolveGatewayEndpoint } from '@/services/endpoint'

type TinyWindow = { tiny?: { api?: { call?: unknown; on?: unknown } } }

function installBridge(call: unknown, on?: unknown) {
  ;(globalThis as unknown as TinyWindow).tiny = { api: { call, on } }
}

describe('resolveGatewayEndpoint', () => {
  afterEach(() => {
    delete (globalThis as unknown as TinyWindow).tiny
  })

  it('falls back to the loopback URL in a browser', async () => {
    expect(isDesktop()).toBe(false)
    await expect(resolveGatewayEndpoint()).resolves.toEqual({ url: DEFAULT_WS_URL })
  })

  it('uses the endpoint handed out by the desktop shell', async () => {
    const call = vi.fn().mockResolvedValue({ url: 'ws://127.0.0.1:54321', token: 'tok' })
    installBridge(call)

    expect(isDesktop()).toBe(true)
    await expect(resolveGatewayEndpoint()).resolves.toEqual({
      url: 'ws://127.0.0.1:54321',
      token: 'tok',
    })
    expect(call).toHaveBeenCalledWith('gateway')
  })

  it('surfaces the reason when the engine never came up', async () => {
    installBridge(vi.fn().mockRejectedValue(new Error('engine exited (1)')))

    await expect(resolveGatewayEndpoint()).rejects.toThrow(/engine exited \(1\)/)
  })

  it('rejects when the shell answers without a URL', async () => {
    installBridge(vi.fn().mockResolvedValue({}))

    await expect(resolveGatewayEndpoint()).rejects.toThrow(/没有返回连接地址/)
  })

  it('ignores a bridge without a callable api', async () => {
    ;(globalThis as unknown as TinyWindow).tiny = { api: {} }

    expect(isDesktop()).toBe(false)
    await expect(resolveGatewayEndpoint()).resolves.toEqual({ url: DEFAULT_WS_URL })
  })
})

describe('onEngineStatus', () => {
  afterEach(() => {
    delete (globalThis as unknown as TinyWindow).tiny
  })

  it('is a no-op without a bridge', () => {
    expect(() => onEngineStatus(() => {})()).not.toThrow()
  })

  it('subscribes through the bridge and returns its unsubscribe', () => {
    const unsubscribe = vi.fn()
    const on = vi.fn().mockReturnValue(unsubscribe)
    installBridge(vi.fn(), on)

    const stop = onEngineStatus(() => {})
    expect(on).toHaveBeenCalledWith('engine-status', expect.any(Function))
    stop()
    expect(unsubscribe).toHaveBeenCalled()
  })
})
