import type { SessionData } from '@/types/session'

/**
 * Per-session "unread" marker.
 *
 * Unread is a property of *you*, not of the session: the backend cannot know whether
 * the window showing a session is in front of you. So the last time a session was
 * opened is kept locally, and a session counts as unread when its `updatedAt` is
 * newer than that timestamp. A server-side version would need a per-user read marker
 * (we are single-user and local, so this keeps one source of truth).
 */

const STORAGE_KEY = 'xiaoqiao:session-read-at'

function loadMap(): Record<string, string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : {}
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const result: Record<string, string> = {}
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value === 'string') result[key] = value
    }
    return result
  } catch {
    return {}
  }
}

function saveMap(map: Record<string, string>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
  } catch {
    // Storage full or disabled — an unread badge is not worth failing over.
  }
}

/** Remember that this session has been looked at, as of now. */
export function markSessionRead(sessionId: string, at: Date = new Date()): void {
  if (!sessionId) return
  const map = loadMap()
  map[sessionId] = at.toISOString()
  saveMap(map)
}

export function sessionReadAt(sessionId: string): string | null {
  return loadMap()[sessionId] ?? null
}

/**
 * True when the session changed after it was last opened. Sessions that never
 * finished a turn (no assistant activity) are not "unread" — there is nothing to
 * read yet.
 */
export function isSessionUnread(session: Pick<SessionData, 'id' | 'updatedAt' | 'endedAt'>): boolean {
  const readAt = sessionReadAt(session.id)
  if (!readAt) return false
  const updated = Date.parse(session.updatedAt || session.endedAt || '')
  if (Number.isNaN(updated)) return false
  return updated > Date.parse(readAt)
}

/** Sessions opened for the first time start out read, so old history does not glow. */
export function forgetSessionReads(keep: string[]): void {
  const map = loadMap()
  const next: Record<string, string> = {}
  for (const id of keep) {
    const value = map[id]
    if (value) next[id] = value
  }
  saveMap(next)
}
