import { useQuery } from '@tanstack/react-query'
import { Plus, UserMinus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import type { LeagueRow } from '@/api/types'
import { FillScroll, OriginalBadge, Section } from '@/components/common/detail'
import { HiddenByProjectBadge, OutOfPatchBadge } from '@/components/common/HideButton'
import { PickerDialog } from '@/components/common/PickerDialog'
import { LeagueImage } from '@/components/common/pictures'
import { LeagueAdboard } from '@/components/adboard/AdboardChoice'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { EntityIssues } from '@/components/common/form'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useStatus, useToken } from '@/state/queries'

/** Dialog: every league the team is not in yet, with a search; the team stays in its other leagues. */
function AddLeagueDialog({ open, onOpenChange, chosen, onPick }: { open: boolean; onOpenChange: (o: boolean) => void; chosen: number[]; onPick: (id: number) => void }) {
  const { t } = useI18n()
  const token = useToken()
  const [q, setQ] = useState('')
  const { data } = useQuery({
    queryKey: ['leagues', token, 'picker', q],
    queryFn: () => api.leagues({ q, size: 100, sort: 'name' }),
    enabled: open && !!token,
    placeholderData: (previous) => previous,
  })
  const items = (data?.items ?? [])
    .filter((l) => !chosen.includes(l.id))
    .map((l) => ({ key: l.id, icon: <LeagueImage id={l.id} size={64} available={!!l.has_logo} className="size-8" />, title: l.name, subtitle: l.country ?? '—' }))
  return (
    <PickerDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('team.addLeagueTitle')}
      description={t('team.addLeagueDescription')}
      placeholder={t('leagues.search')}
      query={q}
      onQuery={setQ}
      groups={[{ items }]}
      empty={t('team.noLeaguesFound')}
      onPick={onPick}
    />
  )
}

/** The leagues the team plays in, edited from the team's screen: a shortcut to the team list of each league (the league
 * screen keeps showing and editing the same lists). The change counts when the page is saved. */
export function TeamLeagues({
  ids,
  hidden,
  setLeagues,
  linkState,
}: {
  ids: number[]
  /** the leagues where the team is out of the patch */
  hidden: number[]
  setLeagues: (ids: number[], hidden: number[]) => void
  linkState?: unknown
}) {
  const { t } = useI18n()
  const token = useToken()
  const lang = useStatus().data?.names_language ?? 'eng_us'
  const [adding, setAdding] = useState(false)
  const rows = useQuery({
    queryKey: ['leagues', token, lang, 'ids', ids.join(',')],
    queryFn: () => api.leagues({ ids: ids.join(','), size: 100, sort: 'name' }),
    enabled: !!token && ids.length > 0,
    placeholderData: (previous) => previous,
  })
  const byId = new Map<number, LeagueRow>((rows.data?.items ?? []).map((l) => [l.id, l]))
  return (
    <Section
      title={t('col.leagues')}
      description={t('team.leaguesHint')}
      action={
        <Button size="sm" onClick={() => setAdding(true)}>
          <Plus /> {t('team.addLeague')}
        </Button>
      }
    >
      <FillScroll>
        <Table>
          <TableHeader className="sticky top-0 z-10 shadow-[0_1px_0_var(--border)] [&_th]:bg-card">
            <TableRow>
              <TableHead className="w-12" />
              <TableHead>{t('col.name')}</TableHead>
              <TableHead className="w-48 text-right">{t('col.country')}</TableHead>
              <TableHead className="w-28 text-center">{t('col.level')}</TableHead>
              <TableHead className="w-28 text-center">{t('col.teams')}</TableHead>
              <TableHead className="w-28 text-center">{t('col.adboards')}</TableHead>
              <TableHead className="w-28 text-center">{t('col.id')}</TableHead>
              <TableHead className="w-28 text-center">{t('roster.inPatch')}</TableHead>
              <TableHead className="w-32" />
              <TableHead className="w-16" />
            </TableRow>
          </TableHeader>
          <TableBody className={rows.isFetching ? 'opacity-70' : undefined}>
            {ids.length === 0 && (
              <TableRow>
                <TableCell colSpan={10} className="py-8 text-center text-muted-foreground">
                  {t('team.noLeagues')}
                </TableCell>
              </TableRow>
            )}
            {ids.map((lid) => {
              const l = byId.get(lid)
              return (
                <TableRow key={lid}>
                  <TableCell>
                    <LeagueImage id={lid} size={64} available={l ? !!l.has_logo : undefined} className="size-8" />
                  </TableCell>
                  <TableCell>
                    <Link to={`/leagues/${lid}`} state={linkState} className="font-medium underline-offset-4 hover:underline">
                      {l?.name ?? `#${lid}`}
                    </Link>{' '}
                    {l && !l.is_new && <OriginalBadge edited={l.edited} />}
                    {hidden.includes(lid) && <OutOfPatchBadge label={t('team.outOfPatchHere')} />}
                    {l?.hidden && (l.is_new ? <OutOfPatchBadge /> : <HiddenByProjectBadge label={t('leagues.hiddenByProject')} />)}
                    {l && !l.hidden && l.hidden_by_countries && <HiddenByProjectBadge label={t('leagues.countryHidden')} />}
                  </TableCell>
                  <TableCell className="text-right">{l?.country ?? '—'}</TableCell>
                  <TableCell className="text-center tabular-nums">{l?.level ?? '—'}</TableCell>
                  <TableCell className="text-center tabular-nums">{l?.team_count ?? '—'}</TableCell>
                  <TableCell>
                    <LeagueAdboard id={l?.adboard_id ?? null} />
                  </TableCell>
                  <TableCell className="text-center tabular-nums">{lid}</TableCell>
                  <TableCell className="text-center">
                    <Switch
                      checked={!hidden.includes(lid)}
                      title={hidden.includes(lid) ? t('team.showInLeague') : t('team.hideInLeague')}
                      onCheckedChange={(on) => setLeagues(ids, on ? hidden.filter((x) => x !== lid) : [...hidden, lid])}
                    />
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" title={t('team.removeLeague')} onClick={() => setLeagues(ids.filter((x) => x !== lid), hidden.filter((x) => x !== lid))}>
                      <UserMinus /> {t('common.remove')}
                    </Button>
                  </TableCell>
                  <TableCell>
                    <EntityIssues kind="league" id={lid} />
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </FillScroll>
      <AddLeagueDialog open={adding} onOpenChange={setAdding} chosen={ids} onPick={(lid) => setLeagues([...ids, lid], hidden)} />
    </Section>
  )
}
