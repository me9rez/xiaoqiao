/**
 * "Put this text into the composer" bus.
 *
 * The composer keeps its draft locally, so anything that wants to prefill it
 * (today: dragging files onto the window) publishes here instead of reaching
 * into the component.
 */

type Listener = (text: string) => void

const listeners = new Set<Listener>()

/** Append text to the active composer. Empty input is ignored. */
export function insertIntoComposer(text: string): void {
  const value = text.trim()
  if (!value) return
  for (const listener of listeners) listener(value)
}

export function onComposerInsert(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
