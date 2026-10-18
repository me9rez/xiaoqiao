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

type BridgeCall = <T>(method: string, params?: Record<string, unknown>) => Promise<T>

/** Return the desktop bridge's `api.call`, bound to its owner, or null in a browser. */
export function bridgeCall(): BridgeCall | null {
  const tiny = (globalThis as unknown as { tiny?: { api?: { call?: unknown } } }).tiny
  const api = tiny?.api
  const call = api?.call
  if (!api || typeof call !== 'function') return null
  return (call as BridgeCall).bind(api)
}

export function isDesktop(): boolean {
  return bridgeCall() !== null
}

/**
 * Resolve the gateway endpoint for the current host.
 *
 * Browser: the fixed loopback URL, immediately.
 * Desktop: ask the shell, which answers after the engine is listening.
 */
export async function resolveGatewayEndpoint(): Promise<GatewayEndpoint> {
  const call = bridgeCall()
  if (!call) return { url: DEFAULT_WS_URL }

  try {
    const info = await call<{ url?: string; token?: string }>('gateway')
    if (info?.url) return { url: info.url, token: info.token }
  } catch {
    // Engine failed to start; the shell surfaces the reason separately.
  }
  return { url: DEFAULT_WS_URL }
}
