export interface Channel {
  id: string
  botId: string
  kind: string
  config: Record<string, unknown>
  enabled: boolean
  createdAt: string
}

export interface ChannelDraft {
  botId: string
  kind: string
  config: Record<string, unknown>
  enabled?: boolean
}
