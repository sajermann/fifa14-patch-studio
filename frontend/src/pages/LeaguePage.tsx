import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, RotateCcw, Trash2, X } from 'lucide-react'
import { useState } from 'react'
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
import { TeamPicker } from '@/components/common/create'
import { toast } from '@/lib/notify'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/api/client'
import { OriginalBadge, OverallBadge, RawTable, Section } from '@/components/common/detail'
import { EditActions, FieldsEditor, NamesEditor, useEntityForm } from '@/components/common/edit'
import { BackButton, useBack, useFrom, useTabParam } from '@/lib/back'
import { cn } from '@/lib/utils'
import { Crest, LeagueImage } from '@/components/common/pictures'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { useI18n } from '@/i18n'
import { useStatus, useToken } from '@/state/queries'

const TABS = ['names', 'data', 'teams', 'raw'] as const

export function LeaguePage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const navigate = useNavigate()
  const lang = useStatus().data?.names_language ?? 'eng_us'
  const queryKey = ['league', token, lang, id]
  const { data, isLoading } = useQuery({ queryKey, queryFn: () => api.league(id), enabled: !!token })
  const tabs = useTabParam(TABS[0])
  const back = useBack({ to: '/leagues', label: t('nav.leagues') })
  const from = useFrom(data?.name ?? t('nav.leagues'))
  const entity = useEntityForm({
    data,
    queryKey,
    invalidate: ['leagues', 'teams', 'team', 'options', 'country', 'countries'],
    save: (f) => api.saveLeague(id, f.names, f.fields),
    reset: () => api.resetLeague(id),
  })
  const qc = useQueryClient()
  const [picking, setPicking] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const afterTeams = (saved: Awaited<ReturnType<typeof api.league>>) => {
    qc.setQueryData(queryKey, saved)
    for (const k of ['leagues', 'teams', 'team', 'country', 'countries', 'status']) void qc.invalidateQueries({ queryKey: [k] })
  }
  const teamsChange = useMutation({
    mutationFn: (ids: number[]) => api.saveLeagueTeams(id, ids),
    onSuccess: afterTeams,
    onError: (e: Error) => toast.error(e.message),
  })
  const teamsReset = useMutation({
    mutationFn: () => api.resetLeagueTeams(id),
    onSuccess: (saved) => {
      afterTeams(saved)
      toast.success(t('league.teamsRestored'))
    },
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
  const busy = teamsChange.isPending || teamsReset.isPending
  return (
    <div className="space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 items-center gap-3">
          <LeagueImage id={data.id} size={96} available={data.has_logo} className="size-12" />
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold break-words">{data.name}</h1>
            <p className="text-sm text-muted-foreground">
              {[data.country, data.level !== null ? t('leagues.level', { level: data.level }) : null, `ID ${data.id}`].filter(Boolean).join(' · ')}
            </p>
          </div>
          <OriginalBadge edited={data.edited} isNew={data.is_new} />
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <EditActions edited={data.edited && !data.is_new} entity={entity} />
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
          <TabsTrigger value="names">{t('team.tab.names')}</TabsTrigger>
          <TabsTrigger value="data">{t('team.tab.data')}</TabsTrigger>
          <TabsTrigger value="teams">
            {t('col.teams')} ({data.team_ids.length})
          </TabsTrigger>
          <TabsTrigger value="raw">{t('tab.raw')}</TabsTrigger>
        </TabsList>
        <TabsContent value="names" className="mt-4">
          <NamesEditor kind="league" nameKeys={data.name_keys} languages={data.languages} original={data.original_names} names={entity.form.names} setNames={entity.setNames} />
        </TabsContent>
        <TabsContent value="data" className="mt-4">
          <FieldsEditor form={data} groups={['info']} fields={entity.form.fields} setField={entity.setField} />
        </TabsContent>
        <TabsContent value="teams" className="mt-4">
          <Section
            title={t('col.teams')}
            description={t('league.teamsHint')}
            action={
              <div className="flex flex-wrap gap-2">
                {data.teams_changed && !data.is_new && (
                  <Button variant="outline" size="sm" disabled={busy} onClick={() => teamsReset.mutate()}>
                    <RotateCcw /> {t('league.teamsRestore')}
                  </Button>
                )}
                <Button size="sm" disabled={busy} onClick={() => setPicking(true)}>
                  {busy ? <Loader2 className="animate-spin" /> : <Plus />} {t('league.addTeams')}
                </Button>
              </div>
            }
          >
          {data.team_ids.length > data.teams.length && (
            <p className="mb-2 text-xs text-muted-foreground">{t('league.teamsShown', { shown: data.teams.length, total: data.team_ids.length })}</p>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12" />
                <TableHead>{t('col.name')}</TableHead>
                <TableHead>{t('col.overall')}</TableHead>
                <TableHead>{t('col.players')}</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.teams.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                    {t('league.noTeams')}
                  </TableCell>
                </TableRow>
              )}
              {data.teams.map((tm) => (
                <TableRow key={tm.id} className={cn('cursor-pointer', !tm.edited && 'text-muted-foreground')} onClick={() => navigate(`/teams/${tm.id}`, from)}>
                  <TableCell>
                    <Crest id={tm.id} size={64} available={tm.has_crest} className="size-8" />
                  </TableCell>
                  <TableCell>
                    <span className="font-medium text-foreground">{tm.name}</span> <OriginalBadge edited={tm.edited} />
                  </TableCell>
                  <TableCell>
                    <OverallBadge value={tm.overall} />
                  </TableCell>
                  <TableCell className="tabular-nums">{tm.player_count}</TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      disabled={busy}
                      title={t('league.removeTeam')}
                      aria-label={t('league.removeTeam')}
                      onClick={(e) => {
                        e.stopPropagation()
                        teamsChange.mutate(data.team_ids.filter((x) => x !== tm.id))
                      }}
                    >
                      <X />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          </Section>
        </TabsContent>
        <TabsContent value="raw" className="mt-4">
          <Section title={t('tab.raw')}>
            <RawTable raw={data.raw} />
          </Section>
        </TabsContent>
      </Tabs>
      <TeamPicker open={picking} onOpenChange={setPicking} chosen={data.team_ids} onPick={(tid) => teamsChange.mutate([...data.team_ids, tid])} />
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
