import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Landmark, Loader2, Plus, Trash2, Undo2, Wand2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
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
import { EntryDates } from '@/components/common/dates'
import { OriginalBadge, Section } from '@/components/common/detail'
import { EntityIssues } from '@/components/common/form'
import { HideButton, OutOfPatchBadge, usePendingHide } from '@/components/common/HideButton'
import { EditActions, FieldsEditor, NamesGrid, RefPickerDialog, useEntityForm } from '@/components/common/edit'
import { Crest, StadiumImage } from '@/components/common/pictures'
import { Stadium3D, StadiumDatabase, StadiumDetails } from '@/components/common/stadium'
import { StadiumFolderButton, StadiumPictureEdit, StadiumSceneNotice, type PendingPictures, type PendingScene } from '@/components/stadium/StadiumEdit'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom, useTabParam } from '@/lib/back'
import { toast } from '@/lib/notify'
import { useOptions, useStatus, useToken } from '@/state/queries'

const TABS = ['overview', 'data', 'raw'] as const
const GROUPS = ['info', 'conditions', 'pitch', 'goal', 'stands']
const MENU_PICTURES = [0, 1, 3, 4] // a created stadium shows all four, filled or not

/** One stadium (the game's or one the user created): what the extractor shows (3D, data, pictures, files) and its
 * edit form, like the league screen. The Overview tab is laid out as the team's stadium tab (data and pictures on top,
 * the 3D always open), with the teams that play there beside the 3D. The teams added on the Overview tab move to this stadium when the form is saved;
 * a created stadium also has its 3D scene and menu picture (saved with the form) and a Delete button. */
export function StadiumPage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const lang = useStatus().data?.names_language ?? 'eng_us'
  const queryKey = ['stadium', token, lang, id]
  const { data, isLoading } = useQuery({
    queryKey,
    queryFn: () => api.stadium(id),
    enabled: !!token,
  })
  const tabs = useTabParam(TABS[0])
  const back = useBack({ to: '/stadiums', label: { key: 'nav.stadiums' } })
  const from = useFrom(data?.name ?? { key: 'nav.stadiums' })
  const teamNames = new Map((useOptions().data?.teams ?? []).map((r) => [r.id, r.name]))
  const [picking, setPicking] = useState(false)
  // teams moved to this stadium but not saved yet: Save moves them with the rest of the form
  const [moving, setMoving] = useState<number[]>([])
  // a created stadium's 3D folder and the menu pictures (any stadium) chosen but not saved yet
  const [scene, setScene] = useState<PendingScene>(null)
  const [pictures, setPictures] = useState<PendingPictures>({})
  const [deleting, setDeleting] = useState(false)
  const hide = usePendingHide(data?.hidden)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const clearPending = () => {
    setMoving([])
    setScene(null)
    setPictures({})
    hide.clear()
  }
  const entity = useEntityForm({
    data,
    queryKey,
    invalidate: ['stadiums', 'teams', 'team', 'options'],
    save: async (f) => {
      let saved = await api.saveStadium(id, f.names, f.fields)
      if (scene === 'remove') saved = await api.removeStadiumScene(id)
      else if (scene) saved = await api.setStadiumScene(id, scene)
      for (const [v, p] of Object.entries(pictures)) {
        saved = p === 'remove' ? await api.removeStadiumPicture(id, Number(v)) : await api.setStadiumPicture(id, Number(v), p.data)
      }
      if (moving.length) {
        for (const tid of moving) await api.setTeamStadium(tid, id)
        saved = await api.stadium(id)
      }
      if (hide.pending !== null) saved = await api.setStadiumHidden(id, hide.pending)
      clearPending()
      return saved
    },
    reset: () => {
      clearPending()
      return api.resetStadium(id)
    },
    extraDirty: moving.length > 0 || scene !== null || Object.keys(pictures).length > 0 || hide.pending !== null,
    onDiscard: clearPending,
    invalid: (f) => !!data?.is_new && !Object.values(f.names.full ?? {}).some((v) => v?.trim()),
  })
  // from scratch: fill the blank fields with the values of the stadium its folder was made for (or the generic one);
  // a game stadium with a folder made for another stadium: take all of that stadium's values (they fit the 3D)
  const [filling, setFilling] = useState(false)
  const fill = async (all = false) => {
    setFilling(true)
    try {
      const found = await api.stadiumDefaults(id)
      let count = 0
      for (const [name, value] of Object.entries(found.values)) {
        const current = entity.form.fields[name] ?? data?.saved[name] ?? data?.values[name]
        if (all ? current !== value : current === null || current === undefined || current === '') {
          entity.setField(name, value)
          count++
        }
      }
      toast.success(t('stadium.filled', { count, name: found.name ?? `#${found.id}` }))
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setFilling(false)
    }
  }
  const remove = useMutation({
    mutationFn: () => api.deleteStadium(id),
    onSuccess: () => {
      for (const k of ['stadiums', 'stadium', 'teams', 'team', 'options', 'status']) void qc.invalidateQueries({ queryKey: [k] })
      toast.success(t('stadium.deleted'))
      navigate(back.to, { state: back.state })
    },
    onError: (e: Error) => {
      setDeleting(false)
      toast.error(e.message)
    },
  })
  if (isLoading || !data) return <LoadingBlock />
  const teamIds = [...data.teams.map((tm) => tm.id), ...moving]
  return (
    <div className="flex h-full min-h-[32rem] flex-col gap-4">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          {data.pictures.length ? (
            <StadiumImage id={data.id} variant={data.pictures[0]} size={256} version={data.updated_at} className="h-24 w-[150px] shrink-0 rounded-lg object-cover" />
          ) : (
            <span className="inline-flex h-24 w-[150px] shrink-0 items-center justify-center rounded-lg bg-muted/40 text-muted-foreground/50">
              <Landmark className="size-6" />
            </span>
          )}
          {/* the name with its details and badges on one line, the dates under it */}
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
              <h1 className="min-w-0 text-2xl font-semibold break-words">{data.name}</h1>
              <span className="shrink-0 text-sm text-muted-foreground tabular-nums">{[data.country, `ID ${data.id}`].filter(Boolean).join(' · ')}</span>
              {!data.is_new && <OriginalBadge edited={data.edited} />}
              {hide.hidden && <OutOfPatchBadge alert />}
            </div>
            <EntryDates entry={data} />
          </div>
        </div>
        <div className="flex flex-col items-end justify-between">
          <div className="flex flex-wrap gap-2">
            <EditActions edited={data.edited && !data.is_new} entity={entity} />
            {data.is_new && (
              <>
                <HideButton variant="outline" hidden={hide.hidden} onToggle={hide.toggle} hideHint={t('stadiums.hideHint')} showHint={t('stadiums.showHint')} />
                <Button variant="outline" size="sm" onClick={() => setDeleting(true)}>
                  <Trash2 /> {t('common.delete')}
                </Button>
              </>
            )}
          </div>
          <EntityIssues kind="stadium" id={id} />
        </div>
      </div>
      <Tabs {...tabs} className="flex min-h-0 flex-1 flex-col">
        <TabsList>
          <TabsTrigger value="overview">{t('tab.overview')}</TabsTrigger>
          <TabsTrigger value="data">{t('team.tab.data')}</TabsTrigger>
          <TabsTrigger value="raw">{t('tab.raw')}</TabsTrigger>
        </TabsList>
        {/* as the team's stadium tab: the data and pictures on top, then the teams beside the 3D (always open) */}
        <TabsContent value="overview" className="min-h-0 flex-1 space-y-4 overflow-auto">
          <StadiumDetails
            stadium={data.is_new ? { ...data, pictures: MENU_PICTURES } : data}
            title={t('section.details')}
            grid
            action={<StadiumFolderButton scene={scene} setScene={setScene} />}
            notice={
              <>
                <StadiumSceneNotice stadium={data} scene={scene} setScene={setScene} />
                <p className="mb-3 text-xs text-muted-foreground">{t('stadium.picturesHint')}</p>
              </>
            }
            picture={(v) => (
              <StadiumPictureEdit
                stadium={data}
                variant={v}
                pending={pictures[v]}
                setPending={(p) => {
                  const next = { ...pictures }
                  if (p === undefined) delete next[v]
                  else next[v] = p
                  setPictures(next)
                }}
              />
            )}
          />
          <div className="grid gap-4 lg:h-[70vh] lg:grid-cols-2">
            <Section
              scroll
              className="max-h-[70vh] lg:h-full lg:max-h-none"
              title={t('stadiums.teams', { count: teamIds.length })}
              action={
                <Button size="sm" title={t('stadium.teamsHint')} onClick={() => setPicking(true)}>
                  <Plus /> {t('stadium.addTeam')}
                </Button>
              }
            >
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-full">{t('col.name')}</TableHead>
                    <TableHead className="text-right">{t('col.customName')}</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {teamIds.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={3} className="py-8 text-center text-muted-foreground">
                        {t('stadiums.noTeams')}
                      </TableCell>
                    </TableRow>
                  )}
                  {data.teams.map((tm) => (
                    <TableRow key={tm.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Crest id={tm.id} size={64} available={tm.has_crest || tm.is_new} className="size-7 shrink-0" />
                          <Link to={`/teams/${tm.id}?tab=stadium`} state={from.state} className="font-medium underline-offset-4 hover:underline">
                            {tm.name}
                          </Link>
                          {!tm.is_new && <OriginalBadge edited={tm.edited} />}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">{tm.stadium_custom_name ?? '—'}</TableCell>
                      <TableCell />
                    </TableRow>
                  ))}
                  {moving.map((tid) => (
                    <TableRow key={tid}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Crest id={tid} size={64} className="size-7 shrink-0" />
                          <span className="font-medium">{teamNames.get(tid) ?? `#${tid}`}</span>
                          <span className="text-xs text-amber-600 dark:text-amber-400">{t('stadium.teamPending')}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">—</TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="sm" onClick={() => setMoving(moving.filter((x) => x !== tid))}>
                          <Undo2 /> {t('common.discard')}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
            <Stadium3D key={`${data.id}-${data.updated_at}`} stadium={data} open className="h-[70vh] lg:h-full" />
          </div>
        </TabsContent>
        <TabsContent value="data" className="min-h-0 flex-1 space-y-4 overflow-auto">
          {data.template === null && (
            // from scratch: every field starts blank; the stadium enters the patch once they are all filled
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed p-3">
              <p className="min-w-0 flex-1 basis-80 text-sm text-muted-foreground">{t('stadium.fillHint')}</p>
              <Button variant="outline" size="sm" disabled={filling} onClick={() => fill()}>
                {filling ? <Loader2 className="animate-spin" /> : <Wand2 />} {t('stadium.fill')}
              </Button>
            </div>
          )}
          {!data.is_new && data.own_scene && data.folder_stadium !== null && data.folder_stadium !== data.id && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed p-3">
              <p className="min-w-0 flex-1 basis-80 text-sm text-muted-foreground">
                {t('stadium.folderDataHint', { name: data.folder_stadium_name ?? `#${data.folder_stadium}` })}
              </p>
              <Button variant="outline" size="sm" disabled={filling} onClick={() => fill(true)}>
                {filling ? <Loader2 className="animate-spin" /> : <Wand2 />} {t('stadium.folderData', { name: data.folder_stadium_name ?? `#${data.folder_stadium}` })}
              </Button>
            </div>
          )}
          <NamesGrid
            kind="stadium"
            columns={data.name_keys}
            languages={data.languages}
            original={data.original_names}
            names={entity.form.names}
            setNames={entity.setNames}
          />
          <FieldsEditor form={data} groups={GROUPS} fields={entity.form.fields} setField={entity.setField} columns="xl:grid-cols-2" />
        </TabsContent>
        <TabsContent value="raw" className="min-h-0 flex-1 overflow-auto">
          <StadiumDatabase stadium={data} />
        </TabsContent>
      </Tabs>
      <RefPickerDialog
        kind="team"
        open={picking}
        onOpenChange={setPicking}
        exclude={teamIds}
        title={t('stadium.addTeam')}
        onPick={(tid) => {
          setMoving([...moving, tid])
          setPicking(false)
        }}
      />
      <AlertDialog open={deleting} onOpenChange={(o) => !remove.isPending && setDeleting(o)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('stadium.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('stadium.deleteText')}</AlertDialogDescription>
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
