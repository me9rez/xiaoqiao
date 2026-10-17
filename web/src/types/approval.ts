export type ApprovalStatus = 'pending' | 'approved' | 'denied' | 'expired'

export interface Approval {
  id: string
  runId: string
  callId: string
  botId: string
  groupId: string | null
  tool: string
  arguments: Record<string, unknown>
  status: ApprovalStatus
  createdAt: string
  expiresAt: string
  resolvedAt: string | null
  resolvedBy: string | null
}
