/** A size in bytes as the screens show it: KB under 1 MB, MB under 1 GB, else GB. */
export function fileSize(bytes: number, lang: string): string {
  const units: [string, number][] = [
    ['GB', 1024 ** 3],
    ['MB', 1024 ** 2],
    ['KB', 1024],
  ]
  const [unit, base] = units.find(([, b]) => bytes >= b) ?? ['KB', 1024]
  const value = bytes / base
  return `${value.toLocaleString(lang, { maximumFractionDigits: value < 10 ? 1 : 0 })} ${unit}`
}
