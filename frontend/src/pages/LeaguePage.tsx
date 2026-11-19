import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ImageOff, Loader2, Plus, RotateCcw, Trash2, Upload, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { toast } from '@/lib/notify'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/api/client'
import { FillScroll, OriginalBadge, OverallBadge, RawTable, Section } from '@/components/common/detail'
import { ALL, EditActions, FieldsEditor, NamesGrid, useEntityForm } from '@/components/common/edit'
import { GameHiddenBadge, HiddenByProjectBadge, HideButton, OutOfPatchBadge, usePendingHide } from '@/components/common/HideButton'
import { PickerDialog } from '@/components/common/PickerDialog'
import { BackButton, useBack, useFrom, useTabParam } from '@/lib/back'
import { cn } from '@/lib/utils'
import { Crest, LeagueImage, readPicture } from '@/components/common/pictures'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { useI18n } from '@/i18n'
import { useStatus, useToken } from '@/state/queries'

const TABS = ['data', 'teams', 'raw'] as const
/** The league's teams shown on the page (a league can have more: the rest is counted). */
const SHOWN_TEAMS = 100

/** The logo picture chosen (or removed) but not saved yet: Save sends it with the rest of the form. */
type PendingLogo = { data: string; url: string } | 'remove' | null

/** Dialog: every team not in the league, with a search; the team stays in its other leagues and also plays in
 * this one (the Street Studio's Add team). */
function AddTeamDialog({ open, onOpenChange, chosen, onPick }: { open: boolean; onOpenChange: (o: boolean) => void; chosen: number[]; onPick: (id: number) => void }) {
  const { t } = useI18n()
  const token = useToken()
  const [q, setQ] = useState('')
  const { data } = useQuery({
    queryKey: ['teams', token, 'picker', q],
    queryFn: () => api.teams({ q, size: 100, sort: 'name' }),
    enabled: open && !!token,
    placeholderData: (previous) => previous,
  })
  const items = (data?.items ?? [])
    .filter((tm) => !chosen.includes(tm.id))
    .map((tm) => ({ key: tm.id, icon: <Crest id={tm.id} size={64} available={tm.has_crest} className="size-8" />, title: tm.name, subtitle: tm.league ?? '—' }))
  return (
    <PickerDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('league.addTeamTitle')}
      description={t('league.addTeamDescription')}
      placeholder={t('teams.search')}
      query={q}
      onQuery={setQ}
      groups={[{ label: t('teams.originalTeams'), items }]}
      empty={t('league.noTeamsFound')}
      onPick={onPick}
    />
  )
}

const sameSet = (a: number[], b: number[]) => a.length === b.length && [...a].sort((x, y) => x - y).every((v, i) => v === [...b].sort((x, y) => x - y)[i])
const sameList = (a: number[], b: number[]) => a.length === b.length && a.every((v, i) => v === b[i])

export function LeaguePage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const lang = useStatus().data?.names_language ?? 'eng_us'
  const queryKey = ['league', token, lang, id]
  const { data, isLoading } = useQuery({ queryKey, queryFn: () => api.league(id), enabled: !!token })
  const tabs = useTabParam(TABS[0])
  const back = useBack({ to: '/leagues', label: { key: 'nav.leagues' } })
  const from = useFrom(data?.name ?? { key: 'nav.leagues' })
  const [picking, setPicking] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [pendingLogo, setPendingLogo] = useState<PendingLogo>(null)
  // the team list being edited (null = the saved one); Save sends it with the rest of the form
  const [pendingTeams, setPendingTeams] = useState<number[] | null>(null)
  const pendingUrl = pendingLogo && pendingLogo !== 'remove' ? pendingLogo.url : null
  useEffect(() => () => void (pendingUrl && URL.revokeObjectURL(pendingUrl)), [pendingUrl])
  const hide = usePendingHide(data?.hidden)
  const clearPending = () => {
    setPendingLogo(null)
    setPendingTeams(null)
    hide.clear()
  }
  const entity = useEntityForm({
    data,
    queryKey,
    invalidate: ['leagues', 'teams', 'team', 'options', 'country', 'countries'],
    save: async (f) => {
      let saved = await api.saveLeague(id, f.names, f.fields)
      if (pendingLogo === 'remove') saved = await api.removeLeagueLogo(id)
      else if (pendingLogo) saved = await api.uploadLeagueLogo(id, pendingLogo.data)
      if (pendingTeams) {
        // the game's teams again: the league goes back to following the game
        saved = !saved.is_new && sameSet(pendingTeams, saved.game_team_ids) ? await api.resetLeagueTeams(id) : await api.saveLeagueTeams(id, pendingTeams)
      }
      if (hide.pending !== null) saved = await api.setLeagueHidden(id, hide.pending)
      clearPending()
      return saved
    },
    reset: () => {
      clearPending()
      return api.resetLeague(id)
    },
    extraDirty: pendingLogo !== null || pendingTeams !== null || hide.pending !== null,
    onDiscard: clearPending,
    // a created league has no name of the game: its "All" name is required (an original one keeps the game's)
    invalid: (f) => !!data?.is_new && !f.names.full?.[ALL]?.trim(),
  })
  const teamIds = pendingTeams ?? data?.team_ids ?? []
  const shownIds = teamIds.slice(0, SHOWN_TEAMS)
  const teamRows = useQuery({
    queryKey: ['teams', token, lang, 'ids', shownIds.join(',')],
    queryFn: () => api.teams({ ids: shownIds.join(','), size: SHOWN_TEAMS, sort: 'name' }),
    enabled: !!token && shownIds.length > 0,
    placeholderData: (previous) => previous,
  })
  const rowsById = new Map((teamRows.data?.items ?? []).map((r) => [r.id, r]))
  const setTeams = (ids: number[]) => setPendingTeams(data && sameList(ids, data.team_ids) ? null : ids)
  const fileInput = useRef<HTMLInputElement>(null)
  const chooseLogo = useMutation({
    mutationFn: async (file: File) => {
      const picture = await readPicture(file)
      return { data: picture, url: URL.createObjectURL(await api.leagueLogoPreview(picture, 256)) }
    },
    onSuccess: (chosen) => setPendingLogo(chosen),
    onError: (e: Error) => toast.error(e.message),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteLeague(id),
    onSuccess: () => {
      for (const k of ['leagues', 'country', 'countries', 'teams', 'options', 'status']) void qc.invalidateQueries({ queryKey: [k] })
      toast.success(t('league.deleted'))
      navigate(back.to, { state: back.state })
    },
    onError: (e: Error) => {
      setDeleting(false)
      toast.error(e.message)
    },
  })
  if (isLoading || !data) return <LoadingBlock />
  const hasOwnLogo = pendingLogo === 'remove' ? false : !!pendingLogo || !!data.own_logo
  const logo = (size: number, className: string) =>
    pendingUrl ? (
      <img src={pendingUrl} alt="" className={cn('object-contain', className)} />
    ) : pendingLogo === 'remove' ? (
      <LeagueImage id={data.id} size={size} gameOnly available={data.game_has_logo} className={className} />
    ) : (
      <LeagueImage id={data.id} size={size} version={data.own_logo} available={data.has_logo} className={className} />
    )
  const gameTeams = !data.is_new && !sameSet(teamIds, data.game_team_ids)
  return (
    <div className="space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          {logo(96, 'size-10 shrink-0')}
          <h1 className="min-w-0 text-2xl font-semibold break-words">{data.name}</h1>
          <span className="shrink-0 text-sm text-muted-foreground tabular-nums">
            {[data.country, data.level !== null ? t('leagues.level', { level: data.level }) : null, `ID ${data.id}`].filter(Boolean).join(' · ')}
          </span>
          <OriginalBadge edited={data.edited} isNew={data.is_new} />
          {data.game_hidden && <GameHiddenBadge />}
          {hide.hidden && <OutOfPatchBadge alert label={data.is_new ? undefined : t('leagues.hiddenByProject')} />}
          {!hide.hidden && data.hidden_by_countries && <HiddenByProjectBadge label={t('leagues.countryHidden')} />}
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <EditActions edited={data.edited && !data.is_new} entity={entity} />
          {!data.game_hidden && (
            <HideButton
              variant="outline"
              hidden={hide.hidden}
              onToggle={hide.toggle}
              hideHint={t(data.is_new ? 'leagues.hideHint' : 'leagues.originalHideHint')}
              showHint={t(data.is_new ? 'leagues.showHint' : 'leagues.originalShowHint')}
            />
          )}
          {data.is_new && (
            <Button variant="outline" size="sm" onClick={() => setDeleting(true)}>
              <Trash2 /> {t('common.delete')}
            </Button>
          )}
        </div>
      </div>
      <p className="text-sm text-muted-foreground">{t('league.freeHint')}</p>
      <Tabs {...tabs}>
        <TabsList>
          <TabsTrigger value="data">{t('team.tab.data')}</TabsTrigger>
          <TabsTrigger value="teams">
            {t('col.teams')} ({teamIds.length})
          </TabsTrigger>
          <TabsTrigger value="raw">{t('tab.raw')}</TabsTrigger>
        </TabsList>
        <TabsContent value="data" className="mt-4 space-y-4">
          <FieldsEditor
            form={data}
            groups={['info']}
            fields={entity.form.fields}
            setField={entity.setField}
            columns=""
            title={() => t('league.dataTitle')}
            extra={{
              info: (
                <div className="flex flex-wrap items-center gap-4 border-b pb-4">
                  <div className="flex size-30 shrink-0 items-center justify-center rounded-md bg-muted/40 p-3">{logo(256, 'size-24')}</div>
                  <div className="min-w-0 flex-1 basis-64 space-y-2">
                    <p className="text-xs text-muted-foreground">{hasOwnLogo ? t('league.logoOwn') : t(data.is_new ? 'league.logoHintNew' : 'league.logoHint')}</p>
                    {pendingLogo && <p className="text-xs text-amber-600 dark:text-amber-400">{t(pendingLogo === 'remove' ? 'league.logoRemovePending' : 'league.logoPending')}</p>}
                    <div className="flex flex-wrap gap-2">
                      <input
                        ref={fileInput}
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/bmp,image/gif"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0]
                          if (file) chooseLogo.mutate(file)
                          e.target.value = ''
                        }}
                      />
                      <Button variant="outline" size="sm" disabled={chooseLogo.isPending} onClick={() => fileInput.current?.click()}>
                        {chooseLogo.isPending ? <Loader2 className="animate-spin" /> : <Upload />} {t('league.logoUpload')}
                      </Button>
                      {hasOwnLogo && (
                        <Button variant="ghost" size="sm" onClick={() => setPendingLogo(data.own_logo ? 'remove' : null)}>
                          <ImageOff /> {t('league.logoRemove')}
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              ),
            }}
          />
          <NamesGrid
            kind="league"
            columns={['abbr', 'abbr15', 'full', 'trophy_abbr15', 'trophy'].filter((k) => data.name_keys.includes(k))}
            languages={data.languages}
            original={data.original_names}
            names={entity.form.names}
            setNames={entity.setNames}
            required={data.is_new ? ['full'] : []}
          />
        </TabsContent>
        <TabsContent value="teams" className="mt-4">
          <Section
            title={t('col.teams')}
            description={t('league.teamsHint')}
            action={
              <div className="flex flex-wrap gap-2">
                {gameTeams && (
                  <Button variant="outline" size="sm" onClick={() => setTeams([...data.game_team_ids])}>
                    <RotateCcw /> {t('league.teamsRestore')}
                  </Button>
                )}
                <Button size="sm" onClick={() => setPicking(true)}>
                  <Plus /> {t('league.addTeam')}
                </Button>
              </div>
            }
          >
            {pendingTeams && <p className="mb-2 text-xs text-amber-600 dark:text-amber-400">{t('league.teamsPending')}</p>}
            {teamIds.length > shownIds.length && <p className="mb-2 text-xs text-muted-foreground">{t('league.teamsShown', { shown: shownIds.length, total: teamIds.length })}</p>}
            <FillScroll>
              <Table>
                <TableHeader className="sticky top-0 z-10 shadow-[0_1px_0_var(--border)] [&_th]:bg-card">
                  <TableRow>
                    <TableHead className="w-12" />
                    <TableHead>{t('col.name')}</TableHead>
                    <TableHead>{t('col.overall')}</TableHead>
                    <TableHead>{t('col.players')}</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody className={teamRows.isFetching ? 'opacity-70' : undefined}>
                  {teamIds.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                        {t('league.noTeams')}
                      </TableCell>
                    </TableRow>
                  )}
                  {shownIds.map((tid) => {
                    const tm = rowsById.get(tid)
                    return (
                      <TableRow key={tid} className={cn('cursor-pointer', !tm?.edited && 'text-muted-foreground')} onClick={() => navigate(`/teams/${tid}`, from)}>
                        <TableCell>
                          <Crest id={tid} size={64} available={tm?.has_crest} className="size-8" />
                        </TableCell>
                        <TableCell>
                          <span className="font-medium text-foreground">{tm?.name ?? `#${tid}`}</span> {tm && <OriginalBadge edited={tm.edited} />}
                          {tm?.hidden && <HiddenByProjectBadge label={t('teams.hiddenByProject')} />}
                        </TableCell>
                        <TableCell>
                          <OverallBadge value={tm?.overall ?? null} />
                        </TableCell>
                        <TableCell className="tabular-nums">{tm?.player_count ?? '—'}</TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            title={t('league.removeTeam')}
                            aria-label={t('league.removeTeam')}
                            onClick={(e) => {
                              e.stopPropagation()
                              setTeams(teamIds.filter((x) => x !== tid))
                            }}
                          >
                            <X />
                          </Button>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </FillScroll>
          </Section>
        </TabsContent>
        <TabsContent value="raw" className="mt-4">
          <Section title={t('tab.raw')}>
            <RawTable raw={data.raw} />
          </Section>
        </TabsContent>
      </Tabs>
      <AddTeamDialog open={picking} onOpenChange={setPicking} chosen={teamIds} onPick={(tid) => setTeams([...teamIds, tid])} />
      <AlertDialog open={deleting} onOpenChange={(o) => !remove.isPending && setDeleting(o)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('league.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('league.deleteText')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" disabled={remove.isPending} onClick={(e) => (e.preventDefault(), remove.mutate())}>
              {remove.isPending ? <Loader2 className="animate-spin" /> : <Trash2 />} {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
