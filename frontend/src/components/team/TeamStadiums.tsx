import { useQuery } from '@tanstack/react-query'
import { ArrowLeftRight, Landmark, LoaderCircle, Repeat } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api/client'
import type { StadiumInfo } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Section } from '@/components/common/detail'
import { PickerDialog } from '@/components/common/PickerDialog'
import { StadiumImage } from '@/components/common/pictures'
import { Stadium3D, StadiumDetails } from '@/components/common/stadium'
import { useI18n } from '@/i18n'
import { useOptions, useStatus, useToken } from '@/state/queries'

/** The stadium chosen on the team's screen but not saved yet: a stadium id, or 'game' = the game's again. */
export type PendingStadium = number | 'game' | null

/** Dialog: the game's stadiums, with a search, to pick the one the team plays in. */
function StadiumPickerDialog({ open, onOpenChange, current, onPick }: { open: boolean; onOpenChange: (o: boolean) => void; current: number | null; onPick: (id: number) => void }) {
  const { t } = useI18n()
  const token = useToken()
  const [q, setQ] = useState('')
  const { data } = useQuery({
    queryKey: ['stadiums', token, 'picker', q],
    queryFn: () => api.stadiums({ q, size: 100, sort: 'name' }),
    enabled: open && !!token,
    placeholderData: (previous) => previous,
  })
  const items = (data?.items ?? [])
    .filter((s) => s.id !== current)
    .map((s) => ({
      key: s.id,
      icon:
        s.picture !== null ? (
          <StadiumImage id={s.id} variant={s.picture} size={128} className="h-7 w-24 rounded object-cover" />
        ) : (
          <span className="inline-flex h-7 w-24 items-center justify-center rounded bg-muted text-muted-foreground/50">
            <Landmark className="size-4" />
          </span>
        ),
      title: s.name,
      subtitle: [s.country, s.home_team, `ID ${s.id}`].filter(Boolean).join(' · '),
    }))
  return (
    <PickerDialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o)
        if (!o) setQ('')
      }}
      title={t('team.stadiumPickTitle')}
      description={t('team.stadiumPickDescription')}
      placeholder={t('stadiums.search')}
      query={q}
      onQuery={setQ}
      groups={[{ items }]}
      empty={t('list.empty')}
      actionLabel={t('field.pick.choose')}
      onPick={(sid) => {
        onPick(sid)
        onOpenChange(false)
        setQ('')
      }}
    />
  )
}

/** The team's stadium tab: the stadium it plays in (one per team, as in the game) with its pictures and the buttons to
 * change it (the choice is saved with the rest of the team's screen), and the 3D preview below, always on. A stadium
 * chosen but not saved yet is shown at once (data, pictures and 3D). */
export function TeamStadiums({
  stadiums,
  customName,
  changed,
  gameStadium,
  pending,
  onPending,
}: {
  stadiums: StadiumInfo[]
  customName: string | null
  /** The saved stadium is the user's choice (not the game's). */
  changed: boolean
  /** The game's stadium of the team ("back to the game's"). */
  gameStadium: number | null
  pending: PendingStadium
  onPending: (p: PendingStadium) => void
}) {
  const { t } = useI18n()
  const names = new Map((useOptions().data?.stadiums ?? []).map((s) => [s.id, s.name]))
  const [picking, setPicking] = useState(false)
  const token = useToken()
  const lang = useStatus().data?.names_language ?? 'eng_us'
  const saved = stadiums[0]
  const current = saved?.id ?? null
  // the stadium chosen but not saved yet (or the game's again): its screen data, the same query as the stadium page
  const pendingId = typeof pending === 'number' ? pending : pending === 'game' ? gameStadium : null
  const chosen = useQuery({ queryKey: ['stadium', token, lang, pendingId], queryFn: () => api.stadium(pendingId!), enabled: !!token && pendingId !== null })
  const stadium = pendingId === null ? saved : chosen.data
  const actions = (
    <div className="flex flex-wrap gap-2">
      {(changed || typeof pending === 'number') && pending !== 'game' && (
        <Button variant="ghost" size="sm" onClick={() => onPending(changed ? 'game' : null)}>
          <Repeat /> {t('playerBoots.useDefault')}
        </Button>
      )}
      <Button size="sm" title={t('team.stadiumHint')} onClick={() => setPicking(true)}>
        <ArrowLeftRight /> {t('team.stadiumChange')}
      </Button>
    </div>
  )
  const notice =
    pending !== null ? (
      <p className="mb-3 text-xs text-amber-600 dark:text-amber-400">
        {pending === 'game' ? t('team.stadiumPendingGame') : t('team.stadiumPending', { name: names.get(pending) ?? `#${pending}` })}
      </p>
    ) : null
  return (
    <div className="space-y-4">
      {stadium ? (
        <>
          <StadiumDetails stadium={stadium} customName={pendingId === null ? customName : null} grid action={actions} notice={notice} />
          <Stadium3D stadium={stadium} open className="h-[70vh]" />
        </>
      ) : pendingId !== null ? (
        <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
      ) : (
        <Section title={t('team.stadiumTitle')} action={actions}>
          {notice}
          <p className="text-sm text-muted-foreground">{t('teams.noStadium')}</p>
        </Section>
      )}
      <StadiumPickerDialog open={picking} onOpenChange={setPicking} current={typeof pending === 'number' ? pending : current} onPick={(sid) => onPending(sid === current && pending !== 'game' ? null : sid)} />
    </div>
  )
}
