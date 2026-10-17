export interface Bot {
  id: string
  name: string
  slug: string
  emoji: string
  persona: string
  model: string
  tools: string[]
  workspace: string
  createdAt: string
  updatedAt: string
}

export interface BotDraft {
  name: string
  emoji?: string
  persona?: string
  model?: string
  workspace?: string
  tools?: string[]
}

export interface ToolInfo {
  name: string
  description: string
}
