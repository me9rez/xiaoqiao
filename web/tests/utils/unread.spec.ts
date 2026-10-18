import { beforeEach, describe, expect, it } from 'vitest'
import { forgetSessionReads, isSessionUnread, markSessionRead, sessionReadAt } from '@/utils/unread'

function session(updatedAt: string) {
  return { id: 's_1', updatedAt, endedAt: updatedAt }
}

describe('session unread marker', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('a session never opened is not unread', () => {
    expect(isSessionUnread(session('2026-10-18T10:00:00.000Z'))).toBe(false)
  })

  it('counts as unread when it changed after the last visit', () => {
    markSessionRead('s_1', new Date('2026-10-18T09:00:00.000Z'))

    expect(isSessionUnread(session('2026-10-18T10:00:00.000Z'))).toBe(true)
  })

  it('is read again once the visit is newer than the change', () => {
    markSessionRead('s_1', new Date('2026-10-18T11:00:00.000Z'))

    expect(isSessionUnread(session('2026-10-18T10:00:00.000Z'))).toBe(false)
  })

  it('stores one marker per session', () => {
    markSessionRead('a', new Date('2026-10-18T09:00:00.000Z'))
    markSessionRead('b', new Date('2026-10-18T09:30:00.000Z'))

    expect(sessionReadAt('a')).toBe('2026-10-18T09:00:00.000Z')
    expect(sessionReadAt('b')).toBe('2026-10-18T09:30:00.000Z')
    expect(sessionReadAt('missing')).toBeNull()
  })

  it('ignores an unparseable timestamp', () => {
    markSessionRead('s_1', new Date('2026-10-18T09:00:00.000Z'))

    expect(isSessionUnread({ id: 's_1', updatedAt: 'not a date', endedAt: '' })).toBe(false)
  })

  it('survives corrupt storage', () => {
    localStorage.setItem('xiaoqiao:session-read-at', '{not json')

    expect(sessionReadAt('s_1')).toBeNull()
  })

  it('forgetSessionReads keeps only the listed sessions', () => {
    markSessionRead('a', new Date('2026-10-18T09:00:00.000Z'))
    markSessionRead('b', new Date('2026-10-18T09:30:00.000Z'))

    forgetSessionReads(['b'])

    expect(sessionReadAt('a')).toBeNull()
    expect(sessionReadAt('b')).toBe('2026-10-18T09:30:00.000Z')
  })
})
