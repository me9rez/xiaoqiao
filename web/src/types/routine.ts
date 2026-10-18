export type ScheduleKind = 'daily' | 'interval' | 'once'

export interface RoutineSchedule {
  kind: ScheduleKind
  at?: string
  minutes?: number
  tz?: string
}

export interface Routine {
  id: string
  botId: string
  name: string
  schedule: RoutineSchedule
  prompt: string
  targetGroupId: string | null
  targetChannelId: string | null
  enabled: boolean
  nextRunAt: string | null
  lastRunAt: string | null
  createdAt: string
}

export interface RoutineStep {
  tool: string
  argsSummary: string
}

export interface RoutineDraft {
  botId: string
  name: string
  schedule: RoutineSchedule
  prompt: string
  targetGroupId?: string | null
  enabled?: boolean
  /** Steps carried over from a run ("teach once"); context, not a replay. */
  steps?: RoutineStep[]
}

/** Shape returned by `draftRoutineFromRun`. */
export interface RoutineDraftSuggestion extends RoutineDraft {
  runId: string
  hasSteps: boolean
}
