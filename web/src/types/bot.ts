export interface Bot {
  id: string
  name: string
  slug: string
  emoji: string
  persona: string
  model: string
  tools: string[]
  workspace: string
  /** Short job title ("总管", "程序员"), shown in the sidebar and the detail drawer. */
  role: string
  /** One-line introduction rendered under the bot's name. */
  description: string
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
  role?: string
  description?: string
}

export interface ToolInfo {
  name: string
  description: string
}
