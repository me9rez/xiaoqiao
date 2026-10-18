export interface UsageTotals {
  inputTokens: number
  outputTokens: number
  totalTokens: number
  costUsd: number
  runs: number
}

export interface UsageByModel {
  model: string
  tokens: number
  costUsd: number
  runs: number
}

export interface UsageBudget {
  dailyTokens: number
  dailyUsd: number
}

export interface UsageSummary {
  today: UsageTotals
  window: UsageTotals
  byModel: UsageByModel[]
  byBot: UsageByBot[]
  byDay: UsageByDay[]
  budget: UsageBudget
}

export interface UsageByBot {
  botId: string
  tokens: number
  costUsd: number
  runs: number
}

export interface UsageByDay {
  date: string
  botId: string
  tokens: number
}
