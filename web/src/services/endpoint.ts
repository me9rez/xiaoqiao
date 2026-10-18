/**
 * Gateway endpoint resolution.
 *
 * Two hosts share this bundle:
 * - the browser, opened against `xiaoqiao --web` (fixed loopback port), and
 * - the desktop shell, where the tinyjs backend spawns the engine on an
 *   OS-assigned port and hands out a one-time handshake token.
 *
 * In the desktop case the bridge call only resolves once the engine has
 * printed its ready line, so callers get "endpoint available" and
 * "engine reachable" as a single await.
 */

export const DEFAULT_WS_URL = 'ws://127.0.0.1:8765'

export interface GatewayEndpoint {
  url: string
  /** Handshake token; only the desktop shell requires one. */
  token?: string
}

/** Lifecycle of the local engine, as pushed by the desktop shell. */
export interface EngineStatus {
  state: 'starting' | 'ready' | 'stopped'
  endpoint: string | null
  pid: number | null
  restarts: number
  lastExit: { code: number | null; at: number } | null
  log: string[]
}

type BridgeCall = <T>(method: string, params?: Record<string, unknown>) => Promise<T>
type BridgeOn = (event: string, handler: (payload: unknown) => void) => () => void

interface Bridge {
  call: BridgeCall | null
  on: BridgeOn | null
}

function bridge(): Bridge {
  const tiny = (globalThis as unknown as { tiny?: { api?: { call?: unknown; on?: unknown } } }).tiny
  const api = tiny?.api
  const call = api?.call
  const on = api?.on
  return {
    call: api && typeof call === 'function' ? (call as BridgeCall).bind(api) : null,
    on: api && typeof on === 'function' ? (on as BridgeOn).bind(api) : null,
  }
}

/** Return the desktop bridge's `api.call`, bound to its owner, or null in a browser. */
export function bridgeCall(): BridgeCall | null {
  return bridge().call
}

export function isDesktop(): boolean {
  return bridge().call !== null
}

/**
 * Subscribe to engine lifecycle pushes from the shell.
 *
 * Returns an unsubscribe function; a browser (no bridge) gets a no-op.
 */
export function onEngineStatus(handler: (status: EngineStatus) => void): () => void {
  const { on } = bridge()
  if (!on) return () => {}
  return on('engine-status', (payload) => handler(payload as EngineStatus))
}

function describe(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}

/**
 * Resolve the gateway endpoint for the current host.
 *
 * Browser: the fixed loopback URL, immediately.
 * Desktop: ask the shell, which answers after the engine is listening. Throws
 * when the engine never came up, so the UI can show the reason instead of
 * silently retrying a URL that will never answer.
 */
export async function resolveGatewayEndpoint(): Promise<GatewayEndpoint> {
  const call = bridgeCall()
  if (!call) return { url: DEFAULT_WS_URL }

  let info: { url?: string; token?: string } | null = null
  try {
    info = await call<{ url?: string; token?: string }>('gateway')
  } catch (error) {
    throw new Error(`本地引擎没有就绪：${describe(error)}`)
  }
  if (!info?.url) throw new Error('本地引擎没有返回连接地址')
  return { url: info.url, token: info.token }
}
