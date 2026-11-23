import { useQuery } from '@tanstack/react-query'
import { Landmark, Plus, Undo2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/api/client'
import { EntryDates } from '@/components/common/dates'
import { OriginalBadge, Section } from '@/components/common/detail'
import { EditActions, FieldsEditor, NamesGrid, RefPickerDialog, useEntityForm } from '@/components/common/edit'
import { Crest, StadiumImage } from '@/components/common/pictures'
import { Stadium3D, StadiumDatabase, StadiumDetails } from '@/components/common/stadium'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom, useTabParam } from '@/lib/back'
import { useOptions, useStatus, useToken } from '@/state/queries'

const TABS = ['overview', 'data', 'raw'] as const
const GROUPS = ['info', 'conditions', 'pitch', 'goal', 'stands']

/** One stadium of the game: what the extractor shows (3D, data, pictures, files) and its edit form, like the league
 * screen. The teams added on the Overview tab move to this stadium when the form is saved. */
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
  const [open3d, setOpen3d] = useState(false)
  const [picking, setPicking] = useState(false)
  // teams moved to this stadium but not saved yet: Save moves them with the rest of the form
  const [moving, setMoving] = useState<number[]>([])
  const entity = useEntityForm({
    data,
    queryKey,
    invalidate: ['stadiums', 'teams', 'team', 'options'],
    save: async (f) => {
      let saved = await api.saveStadium(id, f.names, f.fields)
      if (moving.length) {
        for (const tid of moving) await api.setTeamStadium(tid, id)
        saved = await api.stadium(id)
      }
      setMoving([])
      return saved
    },
    reset: () => {
      setMoving([])
      return api.resetStadium(id)
    },
    extraDirty: moving.length > 0,
    onDiscard: () => setMoving([]),
  })
  if (isLoading || !data) return <LoadingBlock />
  const teamIds = [...data.teams.map((tm) => tm.id), ...moving]
  // the page never scrolls (as the extractor's): its boxes take the height left and scroll inside
  return (
    <div className="flex h-full min-h-[32rem] flex-col gap-4">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          {data.pictures.length ? (
            <StadiumImage id={data.id} variant={data.pictures[0]} size={256} className="h-24 w-[150px] shrink-0 rounded-lg object-cover" />
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
              <OriginalBadge edited={data.edited} />
            </div>
            <EntryDates entry={data} />
          </div>
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <EditActions edited={data.edited} entity={entity} />
        </div>
      </div>
      <Tabs {...tabs} className="flex min-h-0 flex-1 flex-col">
        <TabsList>
          <TabsTrigger value="overview">{t('tab.overview')}</TabsTrigger>
          <TabsTrigger value="data">{t('team.tab.data')}</TabsTrigger>
          <TabsTrigger value="raw">{t('tab.raw')}</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="flex min-h-0 flex-1 flex-col gap-4">
          <Stadium3D stadium={data} open={open3d} setOpen={setOpen3d} className={open3d ? 'min-h-0 flex-1' : 'shrink-0'} />
          <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <StadiumDetails stadium={data} title={t('section.details')} scroll className="h-full" />
            <Section
              scroll
              className="h-full"
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
                    <TableHead className="w-10" />
                    <TableHead>{t('col.name')}</TableHead>
                    <TableHead>{t('col.league')}</TableHead>
                    <TableHead>{t('col.customName')}</TableHead>
                    <TableHead className="w-32" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {teamIds.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                        {t('stadiums.noTeams')}
                      </TableCell>
                    </TableRow>
                  )}
                  {data.teams.map((tm) => (
                    <TableRow key={tm.id}>
                      <TableCell>
                        <Crest id={tm.id} size={64} available={tm.has_crest || tm.is_new} className="size-7" />
                      </TableCell>
                      <TableCell>
                        <Link to={`/teams/${tm.id}?tab=stadium`} state={from.state} className="font-medium underline-offset-4 hover:underline">
                          {tm.name}
                        </Link>{' '}
                        {!tm.is_new && <OriginalBadge edited={tm.edited} />}
                      </TableCell>
                      <TableCell>{tm.league ?? '—'}</TableCell>
                      <TableCell>{tm.stadium_custom_name ?? '—'}</TableCell>
                      <TableCell />
                    </TableRow>
                  ))}
                  {moving.map((tid) => (
                    <TableRow key={tid}>
                      <TableCell>
                        <Crest id={tid} size={64} className="size-7" />
                      </TableCell>
                      <TableCell>
                        <span className="font-medium">{teamNames.get(tid) ?? `#${tid}`}</span>{' '}
                        <span className="text-xs text-amber-600 dark:text-amber-400">{t('stadium.teamPending')}</span>
                      </TableCell>
                      <TableCell>—</TableCell>
                      <TableCell>—</TableCell>
                      <TableCell>
                        <Button variant="ghost" size="sm" onClick={() => setMoving(moving.filter((x) => x !== tid))}>
                          <Undo2 /> {t('common.discard')}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
          </div>
        </TabsContent>
        <TabsContent value="data" className="min-h-0 flex-1 space-y-4 overflow-auto">
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
    </div>
  )
}
