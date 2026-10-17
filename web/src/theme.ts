/**
 * Theme runtime: color scheme + font scale.
 *
 * The boot script in `index.html` applies the same values before first paint
 * to avoid a flash; keep the storage keys in sync with that script.
 */

export type ColorScheme = 'light' | 'dark' | 'system'
export type FontScale = 'small' | 'medium' | 'large' | 'xlarge'

const KEY_PREFIX = 'xiaoqiao:'
const LEGACY_PREFIX = 'coding-agent:'

export const COLOR_SCHEME_KEY = `${KEY_PREFIX}color-scheme`
export const FONT_SCALE_KEY = `${KEY_PREFIX}font-scale`

const darkQuery = () => window.matchMedia('(prefers-color-scheme: dark)')

/** Read a preference, migrating the pre-rename `coding-agent:*` key on first use. */
function readStored(key: string): string | null {
  try {
    const value = localStorage.getItem(key)
    if (value !== null) return value
    const legacyKey = LEGACY_PREFIX + key.slice(KEY_PREFIX.length)
    const legacy = localStorage.getItem(legacyKey)
    if (legacy !== null) {
      localStorage.setItem(key, legacy)
      localStorage.removeItem(legacyKey)
      return legacy
    }
  } catch {
    // localStorage may be unavailable; fall through to the default.
  }
  return null
}

function writeStored(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
    localStorage.removeItem(LEGACY_PREFIX + key.slice(KEY_PREFIX.length))
  } catch {
    // localStorage may be unavailable; still apply for this session.
  }
}

function read<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  const value = readStored(key)
  return allowed.includes(value as T) ? (value as T) : fallback
}

export function getColorScheme(): ColorScheme {
  return read<ColorScheme>(COLOR_SCHEME_KEY, ['light', 'dark', 'system'], 'system')
}

export function getFontScale(): FontScale {
  return read<FontScale>(FONT_SCALE_KEY, ['small', 'medium', 'large', 'xlarge'], 'medium')
}

function resolve(scheme: ColorScheme): 'light' | 'dark' {
  if (scheme === 'system') {
    return darkQuery().matches ? 'dark' : 'light'
  }
  return scheme
}

/** Write the resolved scheme so CSS only needs a light and a dark block. */
export function applyColorScheme(scheme: ColorScheme = getColorScheme()): void {
  const root = document.documentElement
  root.dataset.colorPreference = scheme
  root.dataset.colorScheme = resolve(scheme)
}

export function applyFontScale(scale: FontScale = getFontScale()): void {
  document.documentElement.dataset.fontScale = scale
}

export function setColorScheme(scheme: ColorScheme): void {
  writeStored(COLOR_SCHEME_KEY, scheme)
  applyColorScheme(scheme)
}

export function setFontScale(scale: FontScale): void {
  writeStored(FONT_SCALE_KEY, scale)
  applyFontScale(scale)
}

/** Follow the OS theme while the preference is "system". */
export function initTheme(): void {
  applyColorScheme()
  applyFontScale()

  const media = darkQuery()
  const onChange = () => {
    if (getColorScheme() === 'system') {
      applyColorScheme('system')
    }
  }
  media.addEventListener('change', onChange)
}
