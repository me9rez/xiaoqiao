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

export interface RoutineDraft {
  botId: string
  name: string
  schedule: RoutineSchedule
  prompt: string
  targetGroupId?: string | null
  enabled?: boolean
}
