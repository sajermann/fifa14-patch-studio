import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Trash2 } from 'lucide-react'
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/api/client'
import { CreateDialog } from '@/components/common/create'
import { OriginalBadge, Section } from '@/components/common/detail'
import { EditActions, FieldsEditor, NamesEditor, useEntityForm } from '@/components/common/edit'
import { CountryFlag, LeagueImage } from '@/components/common/pictures'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom, useTabParam } from '@/lib/back'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useStatus, useToken } from '@/state/queries'

const TABS = ['leagues', 'names', 'data'] as const

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
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const entity = useEntityForm({
    data,
    queryKey,
    invalidate: ['countries', 'leagues', 'options'],
    save: (f) => api.saveCountry(id, f.names, f.fields),
    reset: () => api.resetCountry(id),
  })
  const createLeague = useMutation({
    mutationFn: (name: string) => api.createLeague({ full: { '*': name } }, { countryid: id }),
    onSuccess: (league) => {
      for (const k of ['country', 'countries', 'leagues', 'options', 'status']) void qc.invalidateQueries({ queryKey: [k] })
      setCreating(false)
      toast.success(t('league.created'))
      navigate(`/leagues/${league.id}`, from)
    },
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
  return (
    <div className="space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 items-center gap-3">
          <CountryFlag id={data.flag_id} size={128} available={data.has_flag || data.is_new || data.flag_id !== data.id} className="h-10 w-14" />
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold break-words">{data.name}</h1>
            <p className="text-sm text-muted-foreground">ID {data.id}</p>
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
      <Tabs {...tabs}>
        <TabsList>
          <TabsTrigger value="leagues">
            {t('col.leagues')} ({data.leagues.length})
          </TabsTrigger>
          <TabsTrigger value="names">{t('team.tab.names')}</TabsTrigger>
          <TabsTrigger value="data">{t('team.tab.data')}</TabsTrigger>
        </TabsList>
        <TabsContent value="leagues" className="mt-4">
          <Section
            title={t('col.leagues')}
            description={t('country.leaguesHint')}
            action={
              <Button size="sm" onClick={() => setCreating(true)}>
                <Plus /> {t('league.new')}
              </Button>
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12" />
                  <TableHead>{t('col.name')}</TableHead>
                  <TableHead>{t('col.level')}</TableHead>
                  <TableHead>{t('col.teams')}</TableHead>
                  <TableHead>{t('col.id')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.leagues.map((l) => (
                  <TableRow key={l.id} className={cn('cursor-pointer', !l.is_new && 'text-muted-foreground')} onClick={() => navigate(`/leagues/${l.id}`, from)}>
                    <TableCell>
                      <LeagueImage id={l.id} size={64} available={!!l.has_logo} className="size-8" />
                    </TableCell>
                    <TableCell>
                      <span className="font-medium text-foreground">{l.name}</span> <OriginalBadge edited={l.edited} isNew={l.is_new} />
                    </TableCell>
                    <TableCell className="tabular-nums">{l.level ?? '—'}</TableCell>
                    <TableCell className="tabular-nums">{l.team_count}</TableCell>
                    <TableCell className="tabular-nums">{l.id}</TableCell>
                  </TableRow>
                ))}
                {data.leagues.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                      {t('country.noLeagues')}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Section>
        </TabsContent>
        <TabsContent value="names" className="mt-4">
          <NamesEditor kind="country" nameKeys={data.name_keys} languages={data.languages} original={data.original_names} names={entity.form.names} setNames={entity.setNames} />
        </TabsContent>
        <TabsContent value="data" className="mt-4">
          <FieldsEditor form={data} groups={['info']} fields={entity.form.fields} setField={entity.setField} />
        </TabsContent>
      </Tabs>
      <CreateDialog
        open={creating}
        onOpenChange={setCreating}
        title={t('league.new')}
        description={t('league.newHint', { country: data.name })}
        label={t('leagueName.full')}
        maxLength={60}
        pending={createLeague.isPending}
        onCreate={(name) => createLeague.mutate(name)}
      />
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
