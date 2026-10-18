export interface GroupSettings {
  autoReply?: boolean
  maxHops?: number
  maxBotsPerTurn?: number
}

export interface Group {
  id: string
  name: string
  defaultBotId: string | null
  /** The group's manager; same value as `defaultBotId`, named the way the product talks about it. */
  adminBotId: string | null
  botIds: string[]
  settings: GroupSettings
  archived: boolean
  createdAt: string
  updatedAt: string
}

export interface GroupMessage {
  id: string
  groupId: string
  seq: number
  authorType: 'user' | 'bot' | 'system'
  authorId: string
  text: string
  mentions: string[]
  replyTo: string | null
  runId: string | null
  createdAt: string
}

export interface GroupDraft {
  name: string
  botIds: string[]
  defaultBotId?: string | null
  adminBotId?: string | null
  settings?: GroupSettings
}
