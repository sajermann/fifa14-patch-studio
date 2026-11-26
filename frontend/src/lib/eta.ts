import { useRef } from 'react'

/** Seconds left of a counted step, from how fast it went since it started (null until there is enough to tell:
 * a few seconds and a few items). `key` names the step: a new one starts counting again. */
export function useEta(key: string | null | undefined, done: number, total: number, now: number): number | null {
  const start = useRef<{ key: string; at: number; done: number } | null>(null)
  if (!key || !total) {
    start.current = null
    return null
  }
  if (start.current?.key !== key || done < start.current.done) start.current = { key, at: now, done }
  const { at, done: from } = start.current
  const seconds = now - at
  const items = done - from
  if (seconds < 3 || items < 2 || done >= total) return null
  return ((total - done) * seconds) / items
}
