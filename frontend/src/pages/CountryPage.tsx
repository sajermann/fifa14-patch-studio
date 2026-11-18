import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ImageOff, Loader2, Plus, Trash2, Upload, X } from 'lucide-react'
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/api/client'
import { FillScroll, OriginalBadge, Section } from '@/components/common/detail'
import { ALL, EditActions, FieldsEditor, NamesGrid, useEntityForm } from '@/components/common/edit'
import { GameHiddenBadge, HiddenByProjectBadge, HideButton, OutOfPatchBadge, usePendingHide } from '@/components/common/HideButton'
import { PickerDialog, type PickerItem } from '@/components/common/PickerDialog'
import { CountryFlag, LeagueImage, readPicture } from '@/components/common/pictures'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom, useTabParam } from '@/lib/back'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useStatus, useToken } from '@/state/queries'

const TABS = ['data', 'leagues'] as const

/** The flag picture chosen (or removed) but not saved yet: Save sends it with the rest of the form. */
type PendingFlag = { data: string; url: string } | 'remove' | null

const sameList = (a: number[], b: number[]) => a.length === b.length && a.every((v, i) => v === b[i])

/** Dialog: every league not in the country (project and game), with a search; the league keeps its other countries
 * and also shows in this one (the same dialog as the Street Studio's Add team). */
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
  const items = (data?.items ?? []).filter((l) => !chosen.includes(l.id) && !l.game_hidden)
  const toItem = (l: (typeof items)[number]): PickerItem<number> => ({
    key: l.id,
    icon: <LeagueImage id={l.id} size={64} version={l.own_logo} available={!!l.has_logo} className="size-8" />,
    title: l.name,
    subtitle: l.country ?? t('country.noCountry'),
  })
  return (
    <PickerDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('country.addLeagueTitle')}
      description={t('country.addLeagueDescription')}
      placeholder={t('leagues.search')}
      query={q}
      onQuery={setQ}
      groups={[
        { label: t('leagues.newLeagues'), items: items.filter((l) => l.is_new).map(toItem) },
        { label: t('leagues.originalLeagues'), items: items.filter((l) => !l.is_new).map(toItem) },
      ]}
      empty={t('country.noLeaguesFound')}
      onPick={onPick}
    />
  )
}

export function CountryPage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const lang = useStatus().data?.names_language ?? 'eng_us'
  const queryKey = ['country', token, lang, id]
  const { data, isLoading } = useQuery({ queryKey, queryFn: () => api.country(id), enabled: !!token })
  const tabs = useTabParam(TABS[0])
  const back = useBack({ to: '/countries', label: t('nav.countries') })
  const from = useFrom(data?.name ?? t('nav.countries'))
  const [adding, setAdding] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [pendingFlag, setPendingFlag] = useState<PendingFlag>(null)
  // the league list being edited (null = the saved one); Save sends it with the rest of the form
  const [pendingLeagues, setPendingLeagues] = useState<number[] | null>(null)
  const hide = usePendingHide(data?.hidden)
  const pendingUrl = pendingFlag && pendingFlag !== 'remove' ? pendingFlag.url : null
  useEffect(() => () => void (pendingUrl && URL.revokeObjectURL(pendingUrl)), [pendingUrl])
  const clearPending = () => {
    setPendingFlag(null)
    setPendingLeagues(null)
    hide.clear()
  }
  const savedLeagues = data?.leagues.map((l) => l.id) ?? []
  const entity = useEntityForm({
    data,
    queryKey,
    invalidate: ['countries', 'leagues', 'league', 'options'],
    save: async (f) => {
      let saved = await api.saveCountry(id, f.names, f.fields)
      if (pendingFlag === 'remove') saved = await api.removeCountryFlag(id)
      else if (pendingFlag) saved = await api.uploadCountryFlag(id, pendingFlag.data)
      if (pendingLeagues) saved = await api.saveCountryLeagues(id, pendingLeagues)
      if (hide.pending !== null) saved = await api.setCountryHidden(id, hide.pending)
      clearPending()
      return saved
    },
    reset: () => {
      clearPending()
      return api.resetCountry(id)
    },
    extraDirty: pendingFlag !== null || pendingLeagues !== null || hide.pending !== null,
    onDiscard: clearPending,
    // a created country has no name of the game: its "All" name is required (an original one keeps the game's)
    invalid: (f) => !!data?.is_new && !f.names.full?.[ALL]?.trim(),
  })
  const leagueIds = pendingLeagues ?? savedLeagues
  const setLeagues = (ids: number[]) => setPendingLeagues(sameList(ids, savedLeagues) ? null : ids)
  const leagueRows = useQuery({
    queryKey: ['leagues', token, lang, 'ids', leagueIds.join(',')],
    queryFn: () => api.leagues({ ids: leagueIds.join(','), size: 100, sort: 'name' }),
    enabled: !!token && leagueIds.length > 0,
    placeholderData: (previous) => previous,
  })
  const rowsById = new Map((leagueRows.data?.items ?? []).map((r) => [r.id, r]))
  const fileInput = useRef<HTMLInputElement>(null)
  const chooseFlag = useMutation({
    mutationFn: async (file: File) => {
      const picture = await readPicture(file)
      return { data: picture, url: URL.createObjectURL(await api.flagPreview(picture, 256)) }
    },
    onSuccess: (chosen) => setPendingFlag(chosen),
    onError: (e: Error) => toast.error(e.message),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteCountry(id),
    onSuccess: () => {
      for (const k of ['countries', 'options', 'status']) void qc.invalidateQueries({ queryKey: [k] })
      toast.success(t('country.deleted'))
      navigate(back.to, { state: back.state })
    },
    onError: (e: Error) => {
      setDeleting(false)
      toast.error(e.message)
    },
  })
  if (isLoading || !data) return <LoadingBlock />
  const hasOwnFlag = pendingFlag === 'remove' ? false : !!pendingFlag || !!data.own_flag
  const flag = (size: number, className: string) =>
    pendingUrl ? (
      <img src={pendingUrl} alt="" className={cn('object-contain', className)} />
    ) : pendingFlag === 'remove' ? (
      <CountryFlag id={data.base_flag_id} size={size} gameOnly available={data.has_flag || data.is_new || data.base_flag_id !== data.id} className={className} />
    ) : (
      <CountryFlag id={data.flag_id} size={size} version={data.own_flag} available={data.has_flag || data.is_new || data.flag_id !== data.id || !!data.own_flag} className={className} />
    )
  return (
    <div className="space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 items-center gap-3">
          {flag(128, 'h-8 w-12 shrink-0')}
          <h1 className="min-w-0 text-2xl font-semibold break-words">{data.name}</h1>
          <span className="shrink-0 text-sm text-muted-foreground tabular-nums">ID {data.id}</span>
          <OriginalBadge edited={data.edited} isNew={data.is_new} />
          {data.game_hidden && <GameHiddenBadge country />}
          {hide.hidden && <OutOfPatchBadge alert label={data.is_new ? undefined : t('countries.hiddenByProject')} />}
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <EditActions edited={data.edited && !data.is_new} entity={entity} />
          {!data.game_hidden && (
            <HideButton
              variant="outline"
              hidden={hide.hidden}
              onToggle={hide.toggle}
              hideHint={t(data.is_new ? 'countries.hideHint' : 'countries.originalHideHint')}
              showHint={t(data.is_new ? 'countries.showHint' : 'countries.originalShowHint')}
            />
          )}
          {data.is_new && (
            <Button variant="outline" size="sm" onClick={() => setDeleting(true)}>
              <Trash2 /> {t('common.delete')}
            </Button>
          )}
        </div>
      </div>
      <Tabs {...tabs}>
        <TabsList>
          <TabsTrigger value="data">{t('team.tab.data')}</TabsTrigger>
          <TabsTrigger value="leagues">
            {t('col.leagues')} ({leagueIds.length})
          </TabsTrigger>
        </TabsList>
        <TabsContent value="data" className="mt-4 space-y-4">
          <FieldsEditor
            form={data}
            groups={['info']}
            fields={entity.form.fields}
            setField={entity.setField}
            columns=""
            title={() => t('country.flagTitle')}
            extra={{
              info: (
                <div className="flex flex-wrap items-center gap-4 border-b pb-4">
                  <div className="flex shrink-0 justify-center rounded-md bg-muted/40 p-3">{flag(256, 'h-24 w-36')}</div>
                  <div className="min-w-0 flex-1 basis-64 space-y-2">
                    <p className="text-xs text-muted-foreground">{hasOwnFlag ? t('country.flagOwn') : t('country.flagHint')}</p>
                    {pendingFlag && <p className="text-xs text-amber-600 dark:text-amber-400">{t(pendingFlag === 'remove' ? 'country.flagRemovePending' : 'country.flagPending')}</p>}
                    <div className="flex flex-wrap gap-2">
                      <input
                        ref={fileInput}
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/bmp,image/gif"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0]
                          if (file) chooseFlag.mutate(file)
                          e.target.value = ''
                        }}
                      />
                      <Button variant="outline" size="sm" disabled={chooseFlag.isPending} onClick={() => fileInput.current?.click()}>
                        {chooseFlag.isPending ? <Loader2 className="animate-spin" /> : <Upload />} {t('country.flagUpload')}
                      </Button>
                      {hasOwnFlag && (
                        <Button variant="ghost" size="sm" onClick={() => setPendingFlag(data.own_flag ? 'remove' : null)}>
                          <ImageOff /> {t('country.flagRemove')}
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              ),
            }}
          />
          <NamesGrid
            kind="country"
            columns={[...data.name_keys].reverse()}
            languages={data.languages}
            original={data.original_names}
            names={entity.form.names}
            setNames={entity.setNames}
            required={data.is_new ? ['full'] : []}
          />
        </TabsContent>
        <TabsContent value="leagues" className="mt-4">
          <Section
            title={t('col.leagues')}
            description={t('country.leaguesHint')}
            action={
              <Button size="sm" onClick={() => setAdding(true)}>
                <Plus /> {t('country.addLeague')}
              </Button>
            }
          >
            {pendingLeagues && <p className="mb-2 text-xs text-amber-600 dark:text-amber-400">{t('country.leaguesPending')}</p>}
            <FillScroll>
              <Table>
                <TableHeader className="sticky top-0 z-10 shadow-[0_1px_0_var(--border)] [&_th]:bg-card">
                  <TableRow>
                    <TableHead className="w-12" />
                    <TableHead>{t('col.name')}</TableHead>
                    <TableHead>{t('col.level')}</TableHead>
                    <TableHead>{t('col.teams')}</TableHead>
                    <TableHead>{t('col.id')}</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody className={leagueRows.isFetching ? 'opacity-70' : undefined}>
                  {leagueIds.map((lid) => {
                    const l = rowsById.get(lid)
                    return (
                      <TableRow key={lid} className={cn('cursor-pointer', !l?.is_new && 'text-muted-foreground')} onClick={() => navigate(`/leagues/${lid}`, from)}>
                        <TableCell>
                          <LeagueImage id={lid} size={64} version={l?.own_logo} available={!!l?.has_logo} className="size-8" />
                        </TableCell>
                        <TableCell>
                          <span className="font-medium text-foreground">{l?.name ?? `#${lid}`}</span> {l && <OriginalBadge edited={l.edited} isNew={l.is_new} />}
                          {l?.game_hidden && <GameHiddenBadge />}
                          {l?.hidden && (l.is_new ? <OutOfPatchBadge /> : <HiddenByProjectBadge label={t('leagues.hiddenByProject')} />)}
                        </TableCell>
                        <TableCell className="tabular-nums">{l?.level ?? '—'}</TableCell>
                        <TableCell className="tabular-nums">{l?.team_count ?? '—'}</TableCell>
                        <TableCell className="tabular-nums">{lid}</TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            title={t('country.removeLeague')}
                            aria-label={t('country.removeLeague')}
                            onClick={(e) => {
                              e.stopPropagation()
                              setLeagues(leagueIds.filter((x) => x !== lid))
                            }}
                          >
                            <X />
                          </Button>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                  {leagueIds.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                        {t('country.noLeagues')}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </FillScroll>
          </Section>
        </TabsContent>
      </Tabs>
      <AddLeagueDialog open={adding} onOpenChange={setAdding} chosen={leagueIds} onPick={(lid) => setLeagues([...leagueIds, lid])} />
      <AlertDialog open={deleting} onOpenChange={(o) => !remove.isPending && setDeleting(o)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('country.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('country.deleteText')}</AlertDialogDescription>
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
