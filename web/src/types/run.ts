export type RunStatus = 'queued' | 'running' | 'waiting_approval' | 'done' | 'failed' | 'cancelled'

export interface RunRecord {
  id: string
  botId: string
  sessionId: string | null
  groupId: string | null
  trigger: string
  status: RunStatus
  hop: number
  error: string | null
  createdAt: string
  startedAt: string | null
  endedAt: string | null
}

export interface RunFilters {
  botId?: string
  groupId?: string
  status?: RunStatus
  limit?: number
}
