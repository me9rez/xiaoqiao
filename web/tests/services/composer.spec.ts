import { describe, expect, it, vi } from 'vitest'
import { insertIntoComposer, onComposerInsert } from '@/services/composer'

describe('composer bus', () => {
  it('delivers inserted text to every subscriber', () => {
    const first = vi.fn()
    const second = vi.fn()
    const offFirst = onComposerInsert(first)
    const offSecond = onComposerInsert(second)

    insertIntoComposer('D:\\a.txt')

    expect(first).toHaveBeenCalledWith('D:\\a.txt')
    expect(second).toHaveBeenCalledWith('D:\\a.txt')
    offFirst()
    offSecond()
  })

  it('stops delivering after unsubscribe', () => {
    const listener = vi.fn()
    const off = onComposerInsert(listener)
    off()

    insertIntoComposer('D:\\b.txt')

    expect(listener).not.toHaveBeenCalled()
  })

  it('ignores blank input', () => {
    const listener = vi.fn()
    const off = onComposerInsert(listener)

    insertIntoComposer('   ')

    expect(listener).not.toHaveBeenCalled()
    off()
  })
})
