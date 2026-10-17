import { beforeEach, describe, expect, it } from 'vitest'

import {
  COLOR_SCHEME_KEY,
  FONT_SCALE_KEY,
  getColorScheme,
  getFontScale,
  setColorScheme,
  setFontScale,
} from '../src/theme'

const LEGACY_COLOR_SCHEME_KEY = 'coding-agent:color-scheme'
const LEGACY_FONT_SCALE_KEY = 'coding-agent:font-scale'

describe('theme storage migration', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('migrates the legacy color-scheme key on read', () => {
    localStorage.setItem(LEGACY_COLOR_SCHEME_KEY, 'dark')

    expect(getColorScheme()).toBe('dark')
    expect(localStorage.getItem(COLOR_SCHEME_KEY)).toBe('dark')
    expect(localStorage.getItem(LEGACY_COLOR_SCHEME_KEY)).toBeNull()
  })

  it('migrates the legacy font-scale key on read', () => {
    localStorage.setItem(LEGACY_FONT_SCALE_KEY, 'large')

    expect(getFontScale()).toBe('large')
    expect(localStorage.getItem(FONT_SCALE_KEY)).toBe('large')
    expect(localStorage.getItem(LEGACY_FONT_SCALE_KEY)).toBeNull()
  })

  it('prefers the new key when both exist', () => {
    localStorage.setItem(LEGACY_COLOR_SCHEME_KEY, 'light')
    localStorage.setItem(COLOR_SCHEME_KEY, 'dark')

    expect(getColorScheme()).toBe('dark')
    expect(localStorage.getItem(LEGACY_COLOR_SCHEME_KEY)).toBe('light')
  })

  it('writes the new keys and drops legacy ones', () => {
    localStorage.setItem(LEGACY_COLOR_SCHEME_KEY, 'dark')
    localStorage.setItem(LEGACY_FONT_SCALE_KEY, 'small')

    setColorScheme('light')
    setFontScale('xlarge')

    expect(localStorage.getItem(COLOR_SCHEME_KEY)).toBe('light')
    expect(localStorage.getItem(FONT_SCALE_KEY)).toBe('xlarge')
    expect(localStorage.getItem(LEGACY_COLOR_SCHEME_KEY)).toBeNull()
    expect(localStorage.getItem(LEGACY_FONT_SCALE_KEY)).toBeNull()
  })
})
