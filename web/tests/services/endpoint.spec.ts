import { afterEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_WS_URL, isDesktop, resolveGatewayEndpoint } from '@/services/endpoint'

type TinyWindow = { tiny?: { api?: { call?: unknown } } }

function installBridge(call: unknown) {
  ;(globalThis as unknown as TinyWindow).tiny = { api: { call } }
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

  it('falls back when the engine never came up', async () => {
    installBridge(vi.fn().mockRejectedValue(new Error('engine failed')))

    await expect(resolveGatewayEndpoint()).resolves.toEqual({ url: DEFAULT_WS_URL })
  })

  it('ignores a bridge without a callable api', async () => {
    ;(globalThis as unknown as TinyWindow).tiny = { api: {} }

    expect(isDesktop()).toBe(false)
    await expect(resolveGatewayEndpoint()).resolves.toEqual({ url: DEFAULT_WS_URL })
  })
})
