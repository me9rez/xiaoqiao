export interface Artifact {
  id: string
  botId: string
  runId: string | null
  path: string
  mime: string | null
  size: number | null
  createdAt: string
}
