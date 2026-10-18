/**
 * Shared class strings for the settings forms.
 *
 * Values come from `docs/design.md` §8.3 (Input) and §8.1 (Button); keeping them
 * here means the model editor, the provider card and the page cannot drift apart.
 */

export const INPUT_CLASS = [
  'w-full h-9 px-3 rounded-[var(--radius-md)] text-[13px] leading-5',
  'border-[0.5px] border-[var(--color-line-strong)] bg-[var(--color-surface-overlay)]',
  'text-[var(--color-text)] shadow-[var(--shadow-xs)] outline-none transition',
  'placeholder:text-[var(--color-text-faint)]',
  'focus:border-[var(--color-accent)] focus:shadow-[var(--p-focus-ring)]',
  'disabled:opacity-50',
].join(' ')

export const SELECT_CLASS = `${INPUT_CLASS} appearance-none cursor-pointer pr-8`

export const TEXTAREA_CLASS = `${INPUT_CLASS} h-auto min-h-16 py-2 resize-y`

export const BTN_SECONDARY_CLASS = [
  'inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-[var(--radius-md)]',
  'text-[13px] font-medium',
  'border-[0.5px] border-[var(--color-line-strong)] bg-[var(--color-surface-raised)] text-[var(--color-text)]',
  'transition hover:bg-[var(--color-hover)] active:scale-[0.98]',
  'focus-visible:shadow-[var(--p-focus-ring)]',
  'disabled:opacity-50 disabled:cursor-not-allowed',
].join(' ')

export const BTN_PRIMARY_CLASS = [
  'inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-[var(--radius-md)]',
  'text-[13px] font-medium border-[0.5px] border-transparent',
  'bg-[var(--color-accent)] text-[var(--color-send-icon)]',
  'transition hover:bg-[var(--color-accent-hover)] active:scale-[0.98]',
  'focus-visible:shadow-[var(--p-focus-ring)]',
  'disabled:opacity-50 disabled:cursor-not-allowed',
].join(' ')

export const BTN_GHOST_CLASS = [
  'inline-flex items-center justify-center gap-1.5 h-8 px-2.5 rounded-[var(--radius-sm)]',
  'text-[13px] text-[var(--color-text-muted)] transition',
  'hover:bg-[var(--color-hover)] hover:text-[var(--color-text)]',
  'focus-visible:shadow-[var(--p-focus-ring)]',
  'disabled:opacity-50',
].join(' ')

export const BTN_DANGER_CLASS = [
  'inline-flex items-center justify-center gap-1.5 h-8 px-2.5 rounded-[var(--radius-sm)]',
  'text-[13px] border-[0.5px] border-[var(--color-danger-bd)]',
  'bg-[var(--color-danger-soft)] text-[var(--color-danger)] transition',
  'hover:bg-[var(--color-danger)] hover:text-white',
  'focus-visible:shadow-[var(--p-focus-ring)]',
].join(' ')

export const CARD_CLASS = [
  'rounded-[var(--radius-lg)] border-[0.5px] border-[var(--color-line)]',
  'bg-[var(--color-surface-raised)] shadow-[var(--shadow-xs)]',
].join(' ')

export const CODE_CLASS = 'font-mono text-[11px] text-[var(--color-text-faint)]'

/** Status pill: background + border + text, never colour alone (§3.4). */
export function badgeClass(tone: 'ok' | 'warn' | 'danger' | 'neutral'): string {
  const tones: Record<string, string> = {
    ok: 'bg-[var(--color-success-soft)] border-[var(--color-success-bd)] text-[var(--color-success)]',
    warn: 'bg-[var(--color-warning-soft)] border-[var(--color-warning-bd)] text-[var(--color-warning)]',
    danger: 'bg-[var(--color-danger-soft)] border-[var(--color-danger-bd)] text-[var(--color-danger)]',
    neutral: 'bg-[var(--color-surface)] border-[var(--color-line)] text-[var(--color-text-muted)]',
  }
  return `inline-flex items-center gap-1 h-[22px] px-2 rounded-[var(--radius-full)] border-[0.5px] text-[12px] leading-none ${tones[tone]}`
}
