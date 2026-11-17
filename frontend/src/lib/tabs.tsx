import { useSearchParams } from 'react-router-dom'

/** The open tab of a detail page lives in the URL (?tab=…). */
export function useTab(tabs: readonly string[]) {
  const [params, setParams] = useSearchParams()
  const current = params.get('tab')
  const tab = current && tabs.includes(current) ? current : tabs[0]
  const setTab = (next: string) =>
    setParams(
      (p) => {
        const q = new URLSearchParams(p)
        if (next === tabs[0]) q.delete('tab')
        else q.set('tab', next)
        return q
      },
      { replace: true },
    )
  return [tab, setTab] as const
}
