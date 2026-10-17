export interface MemoryFact {
  id: string
  botId: string
  key: string
  value: string
  source: string
  confidence: number
  updatedAt: string
}

export interface MemoryNote {
  id: string
  botId: string
  sessionId: string | null
  text: string
  createdAt: string
}
