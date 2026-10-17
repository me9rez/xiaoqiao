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
  budget: UsageBudget
}
