import type { AgentEvent, GatewayEvent, GatewayRequest } from '@/types/gateway'
import { isRpcResponseEvent } from '@/types/gateway'
import { generateId } from '@/utils/uid'

import { DEFAULT_WS_URL, type GatewayEndpoint } from './endpoint'

const MAX_RECONNECT_ATTEMPTS = 5
const INITIAL_RECONNECT_DELAY_MS = 1000
const RPC_TIMEOUT_MS = 5000

type EventCallback = (event: GatewayEvent) => void

interface PendingRpcCall {
  resolve: (value: unknown) => void
  reject: (reason: Error) => void
  timer: ReturnType<typeof setTimeout>
}

export class GatewayService {
  private ws: WebSocket | null = null
  private url: string
  private token: string | null = null
  private handshaking = false
  private listeners: Map<string, EventCallback[]> = new Map()
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private pendingRpcCalls = new Map<string, PendingRpcCall>()
  private messageQueue: string[] = []
  private closedIntentionally = false

  constructor(url?: string) {
    this.url = url ?? DEFAULT_WS_URL
  }

  /**
   * Open the connection.
   *
   * @param endpoint Optional resolved endpoint (desktop shells hand out an
   *   OS-assigned port plus a handshake token). Without one the constructor
   *   URL is used, which is the browser `--web` path.
   */
  connect(endpoint?: GatewayEndpoint): void {
    if (this.ws?.readyState === WebSocket.CONNECTING || this.ws?.readyState === WebSocket.OPEN) {
      return
    }

    if (endpoint?.url) this.url = endpoint.url
    this.token = endpoint?.token ?? null
    this.closedIntentionally = false
    const ws = new WebSocket(this.url)
    this.ws = ws

    ws.onopen = () => {
      this.reconnectAttempts = 0
      void this.finishHandshake()
    }

    ws.onmessage = (msg: MessageEvent) => {
      try {
        const event = JSON.parse(msg.data) as GatewayEvent
        this.emit(event.type, event)
        if (isRpcResponseEvent(event)) {
          this.handleRpcResponse(event)
        }
      } catch {
        // Non-JSON messages
      }
    }

    ws.onclose = (ev: CloseEvent) => {
      this.ws = null
      this.emit('close', { type: 'close', code: ev.code } as unknown as GatewayEvent)
      this.scheduleReconnect()
    }

    ws.onerror = () => {
      // WebSocket errors are also followed by onclose
    }
  }

  /**
   * Desktop shells require a token before any method is allowed, so resolve
   * the handshake first: `open` then means "the gateway will answer my calls".
   */
  private async finishHandshake(): Promise<void> {
    if (this.token) {
      // ``call`` sends its frame synchronously, so start it before flipping the
      // gate: everything the UI sends from now on waits for the acknowledgement.
      const authCall = this.call('auth', { token: this.token })
      this.handshaking = true
      try {
        await authCall
      } catch {
        this.handshaking = false
        this.closedIntentionally = true
        this.emit('auth_failed', { type: 'auth_failed' } as unknown as GatewayEvent)
        this.ws?.close()
        return
      }
      this.handshaking = false
    }
    this.flushMessageQueue()
    this.emit('open', { type: 'open' })
  }

  private flushMessageQueue(): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return
    while (this.messageQueue.length > 0) {
      const message = this.messageQueue.shift()
      if (message) {
        this.ws.send(message)
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.closedIntentionally) return
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) return

    const delay = INITIAL_RECONNECT_DELAY_MS * 2 ** this.reconnectAttempts
    this.reconnectAttempts += 1
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  private handleRpcResponse(event: Extract<AgentEvent, { type: 'rpc_response' }>): void {
    const pending = this.pendingRpcCalls.get(event.id)
    if (!pending) return
    this.pendingRpcCalls.delete(event.id)
    clearTimeout(pending.timer)
    if (event.error) {
      pending.reject(new Error(event.error.message))
    } else {
      pending.resolve(event.result)
    }
  }

  on(event: string, callback: EventCallback): () => void {
    const cbs = this.listeners.get(event) ?? []
    cbs.push(callback)
    this.listeners.set(event, cbs)
    return () => {
      const updated = this.listeners.get(event)?.filter((cb) => cb !== callback) ?? []
      this.listeners.set(event, updated)
    }
  }

  private emit(event: string, payload: GatewayEvent): void {
    this.listeners.get(event)?.forEach((cb) => cb(payload))
  }

  async call<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    return new Promise((resolve, reject) => {
      const id = generateId('rpc')
      const timer = setTimeout(() => {
        this.pendingRpcCalls.delete(id)
        reject(new Error(`RPC timeout: ${method}`))
      }, RPC_TIMEOUT_MS)
      this.pendingRpcCalls.set(id, { resolve: resolve as (value: unknown) => void, reject, timer })
      const request: GatewayRequest = { id, method, params }
      this.send(JSON.stringify(request))
    })
  }

  send(rawMessage: string): void {
    // During the desktop handshake the engine rejects anything but `auth`, so
    // hold outgoing frames until the token is acknowledged.
    if (this.handshaking) {
      this.messageQueue.push(rawMessage)
      return
    }
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(rawMessage)
    } else {
      this.messageQueue.push(rawMessage)
    }
  }

  sendPrompt(text: string, sessionId?: string, botId?: string): void {
    const params: Record<string, string> = { text }
    if (sessionId) params.sessionId = sessionId
    if (botId) params.botId = botId
    this.send(JSON.stringify({ method: 'prompt', params }))
  }

  sendGroupMessage(groupId: string, text: string): void {
    this.send(JSON.stringify({ method: 'prompt', params: { groupId, text } }))
  }

  sendApprovalResponse(callId: string, approved: boolean, remember = false): void {
    this.send(
      JSON.stringify({
        method: 'approval_response',
        params: { callId, approved, remember },
      }),
    )
  }

  cancel(sessionId?: string): void {
    this.send(JSON.stringify({ method: 'cancel', params: { sessionId } }))
  }

  close(): void {
    this.closedIntentionally = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    for (const pending of this.pendingRpcCalls.values()) {
      clearTimeout(pending.timer)
      pending.reject(new Error('Gateway closed'))
    }
    this.pendingRpcCalls.clear()
    this.messageQueue = []
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

export const gatewayService = new GatewayService()
