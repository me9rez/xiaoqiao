/**
 * Server-side "what is every bot doing" snapshot (RPC `getActivity` + the
 * `activity` broadcast). Same shape as `WsGatewayServer._activity_snapshot()`.
 */

export type BotActivityState = 'idle' | 'working' | 'needs_you' | 'error'

export interface RunSummary {
  runId: string
  sessionId?: string | null
  groupId?: string | null
  title?: string
  status?: string
  endedAt?: string | null
}

export interface BotActivity {
  botId: string
  state: BotActivityState
  runId?: string
  sessionId?: string | null
  groupId?: string | null
  title?: string
  currentTool?: string
  startedAt?: string
  lastFinished?: RunSummary
}

export interface ActivitySnapshot {
  bots: BotActivity[]
  pendingApprovals: number
  generatedAt?: string
}

export interface ActivityEvent extends ActivitySnapshot {
  type: 'activity'
}
