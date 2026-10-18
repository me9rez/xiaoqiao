import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GatewayService } from '@/services/gateway'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  readyState: number = MockWebSocket.CONNECTING
  onopen: ((ev?: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onerror: ((ev?: Event) => void) | null = null
  sent: string[] = []
  url: string

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code: 1000 } as CloseEvent)
  }

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  receive(data: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }
}

async function flush() {
  for (let i = 0; i < 5; i += 1) await Promise.resolve()
}

describe('GatewayService desktop handshake', () => {
  beforeEach(() => {
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    MockWebSocket.instances = []
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('connects to the endpoint it is given', () => {
    const service = new GatewayService()
    service.connect({ url: 'ws://127.0.0.1:54321', token: 'tok' })

    expect(MockWebSocket.instances[0]!.url).toBe('ws://127.0.0.1:54321')
  })

  it('sends the token before reporting open', async () => {
    const service = new GatewayService()
    let opened = 0
    service.on('open', () => {
      opened += 1
    })

    service.connect({ url: 'ws://127.0.0.1:54321', token: 'tok' })
    const ws = MockWebSocket.instances[0]!
    ws.open()

    // Nothing is "open" for callers until the handshake is acknowledged.
    expect(opened).toBe(0)
    const auth = JSON.parse(ws.sent[0]!)
    expect(auth.method).toBe('auth')
    expect(auth.params).toEqual({ token: 'tok' })

    ws.receive({ type: 'rpc_response', id: auth.id, result: { ok: true } })
    await flush()

    expect(opened).toBe(1)
  })

  it('queues calls made during the handshake', async () => {
    const service = new GatewayService()
    service.connect({ url: 'ws://127.0.0.1:54321', token: 'tok' })
    const ws = MockWebSocket.instances[0]!
    ws.open()

    service.sendPrompt('hello', 'abc')
    expect(ws.sent.map((raw) => JSON.parse(raw).method)).toEqual(['auth'])

    const auth = JSON.parse(ws.sent[0]!)
    ws.receive({ type: 'rpc_response', id: auth.id, result: { ok: true } })
    await flush()

    expect(ws.sent.map((raw) => JSON.parse(raw).method)).toEqual(['auth', 'prompt'])
  })

  it('reports auth_failed and stops reconnecting', async () => {
    const service = new GatewayService()
    let failed = 0
    service.on('auth_failed', () => {
      failed += 1
    })

    service.connect({ url: 'ws://127.0.0.1:54321', token: 'wrong' })
    const ws = MockWebSocket.instances[0]!
    ws.open()
    const auth = JSON.parse(ws.sent[0]!)
    ws.receive({ type: 'rpc_response', id: auth.id, error: { message: 'unauthorized' } })
    await flush()

    expect(failed).toBe(1)
    expect(MockWebSocket.instances).toHaveLength(1)
  })
})
