import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/api/client'
import type { KitPart, SquadRow, TeamDetail } from '@/api/types'
import { Facts, OriginalBadge, OverallBadge, RawTable, Section } from '@/components/common/detail'
import { EditActions, FieldsEditor, NamesEditor, useEntityForm } from '@/components/common/edit'
import { HideButton, OutOfPatchBadge, usePendingHide } from '@/components/common/HideButton'
import { Crest } from '@/components/common/pictures'
import { TeamCrest } from '@/components/team/TeamCrest'
import { TeamKits } from '@/components/team/TeamKits'
import { TeamSquad } from '@/components/team/TeamSquad'
import { RESERVE, type PendingKit, type PendingPicture } from '@/components/team/pending'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom, useTabParam } from '@/lib/back'
import { toast } from '@/lib/notify'
import { useToken } from '@/state/queries'

const TABS = ['names', 'data', 'crest', 'kits', 'roster', 'raw'] as const

const savedSquad = (team: TeamDetail | undefined): SquadRow[] =>
  (team?.roster ?? []).map((p) => ({ player: p.id, jersey: p.jersey, slot: p.link_position ?? RESERVE, hidden: p.hidden }))

const sameSquad = (a: SquadRow[], b: SquadRow[]) =>
  a.length === b.length && a.every((r, i) => r.player === b[i].player && r.jersey === b[i].jersey && r.slot === b[i].slot && !!r.hidden === !!b[i].hidden)

export function TeamPage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const queryKey = ['team', token, id]
  const { data: team, isLoading } = useQuery({ queryKey, queryFn: () => api.team(id), enabled: !!token })
  const tabs = useTabParam(TABS[0])
  const from = useFrom(team?.name ?? { key: 'nav.teams' })
  const back = useBack({ to: '/teams', label: { key: 'nav.teams' } })
  const hide = usePendingHide(team?.hidden)
  const [deleting, setDeleting] = useState(false)
  // not saved yet: Save sends them with the names and fields
  const [pendingCrest, setPendingCrest] = useState<PendingPicture>(null)
  const [pendingKits, setPendingKits] = useState<Record<number, PendingKit>>({})
  const [pendingSquad, setPendingSquad] = useState<SquadRow[] | null>(null)
  const crestUrl = pendingCrest && pendingCrest !== 'remove' ? pendingCrest.url : null
  useEffect(() => () => void (crestUrl && URL.revokeObjectURL(crestUrl)), [crestUrl])
  const clearPending = () => {
    setPendingCrest(null)
    setPendingKits({})
    setPendingSquad(null)
    hide.clear()
  }
  const entity = useEntityForm({
    data: team,
    queryKey,
    invalidate: ['teams', 'league', 'leagues', 'options'],
    save: async (f) => {
      let saved = await api.saveTeam(id, f.names, f.fields)
      if (pendingCrest === 'remove') saved = await api.removeTeamCrest(id)
      else if (pendingCrest) saved = await api.uploadTeamCrest(id, pendingCrest.data)
      for (const [kind, kit] of Object.entries(pendingKits)) {
        const pictures: Partial<Record<KitPart, string | null>> = {}
        for (const [part, p] of Object.entries(kit.pictures)) if (p) pictures[part as KitPart] = p === 'remove' ? null : p.data
        saved = await api.saveTeamKit(id, Number(kind), kit.config, pictures)
      }
      if (pendingSquad) saved = await api.saveTeamRoster(id, pendingSquad)
      if (hide.pending !== null) saved = await api.setTeamHidden(id, hide.pending)
      clearPending()
      return saved
    },
    reset: () => {
      clearPending()
      return api.resetTeam(id)
    },
    extraDirty: pendingCrest !== null || Object.keys(pendingKits).length > 0 || pendingSquad !== null || hide.pending !== null,
    onDiscard: clearPending,
    // a created team has no name of the game: its "All" name is required
    invalid: (f) => !!team?.is_new && !f.names.full?.['*']?.trim(),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteTeam(id),
    onSuccess: () => {
      for (const k of ['teams', 'options', 'status', 'leagues', 'league']) void qc.invalidateQueries({ queryKey: [k] })
      toast.success(t('team.deleted'))
      navigate(back.to, { state: back.state })
    },
    onError: (e: Error) => {
      setDeleting(false)
      toast.error(e.message)
    },
  })
  if (isLoading || !team) return <LoadingBlock />
  const squad = pendingSquad ?? savedSquad(team)
  const setSquad = (rows: SquadRow[]) => setPendingSquad(sameSquad(rows, savedSquad(team)) ? null : rows)
  const formationValue = entity.form.fields.formation ?? team.values.formation
  const formation = typeof formationValue === 'number' ? formationValue : null
  return (
    <div className="space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        {/* one line like the league and country headers: crest, name, leagues · ID, badges */}
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          {crestUrl ? (
            <img src={crestUrl} alt="" className="size-10 shrink-0 object-contain" />
          ) : (
            <Crest id={team.id} size={96} available={team.has_crest || team.is_new} version={team.own_crest} className="size-10 shrink-0" />
          )}
          <h1 className="min-w-0 text-2xl font-semibold break-words">{team.name}</h1>
          <span className="shrink-0 text-sm text-muted-foreground tabular-nums">
            {team.leagues.map((l, i) => (
              <span key={l.id}>
                {i > 0 && ' · '}
                <Link to={`/leagues/${l.id}`} state={from.state} className="hover:underline">
                  {l.name}
                </Link>
              </span>
            ))}
            {team.leagues.length > 0 && ' · '}ID {team.id}
          </span>
          <OriginalBadge edited={team.edited} isNew={team.is_new} />
          {hide.hidden && <OutOfPatchBadge alert label={team.is_new ? undefined : t('teams.hiddenByProject')} />}
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <EditActions edited={team.edited && !team.is_new} entity={entity} />
          <HideButton
            variant="outline"
            hidden={hide.hidden}
            onToggle={hide.toggle}
            hideHint={t(team.is_new ? 'teams.hideHint' : 'teams.originalHideHint')}
            showHint={t(team.is_new ? 'teams.showHint' : 'teams.originalShowHint')}
          />
          {team.is_new && (
            <Button variant="outline" size="sm" onClick={() => setDeleting(true)}>
              <Trash2 /> {t('common.delete')}
            </Button>
          )}
        </div>
      </div>
      {team.is_new && team.leagues.length === 0 && <p className="text-sm text-amber-600 dark:text-amber-400">{t('team.noLeague')}</p>}

      <Tabs {...tabs}>
        <TabsList>
          <TabsTrigger value="names">{t('team.tab.names')}</TabsTrigger>
          <TabsTrigger value="data">{t('team.tab.data')}</TabsTrigger>
          <TabsTrigger value="crest">{t('team.tab.crest')}</TabsTrigger>
          <TabsTrigger value="kits">{t('team.tab.kits')}</TabsTrigger>
          <TabsTrigger value="roster">
            {t('team.tab.roster')} ({squad.length})
          </TabsTrigger>
          <TabsTrigger value="raw">{t('tab.raw')}</TabsTrigger>
        </TabsList>
        <TabsContent value="names" className="mt-4">
          <NamesEditor kind="team" nameKeys={team.name_keys} languages={team.languages} original={team.original_names} names={entity.form.names} setNames={entity.setNames} />
        </TabsContent>
        <TabsContent value="data" className="mt-4 space-y-4">
          <Section title={t('team.ratings')} description={t('team.ratingsHint')}>
            <Facts
              items={[
                [t('col.overall'), <OverallBadge key="o" value={team.overall} />],
                [t('team.attack'), team.attack],
                [t('team.midfield'), team.midfield],
                [t('team.defense'), team.defense],
              ]}
            />
          </Section>
          <FieldsEditor form={team} groups={['colors', 'club', 'takers', 'tactics']} fields={entity.form.fields} setField={entity.setField} roster={team.roster} />
        </TabsContent>
        <TabsContent value="crest" className="mt-4">
          <TeamCrest team={team} pending={pendingCrest} setPending={setPendingCrest} />
        </TabsContent>
        <TabsContent value="kits" className="mt-4">
          <TeamKits
            team={team}
            pendingCrest={pendingCrest}
            pending={pendingKits}
            setPending={(kind, p) =>
              setPendingKits((all) => {
                const next = { ...all }
                if (p) next[kind] = p
                else delete next[kind]
                return next
              })
            }
          />
        </TabsContent>
        <TabsContent value="roster" className="mt-4 space-y-4">
          {pendingSquad && <p className="text-xs text-amber-600 dark:text-amber-400">{t('squad.pending')}</p>}
          <TeamSquad team={team} rows={squad} setRows={setSquad} formation={formation} setFormation={(f) => entity.setField('formation', f)} />
        </TabsContent>
        <TabsContent value="raw" className="mt-4">
          <Section title={t('tab.raw')}>
            <RawTable raw={team.raw} />
          </Section>
        </TabsContent>
      </Tabs>
      <AlertDialog open={deleting} onOpenChange={(o) => !remove.isPending && setDeleting(o)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('team.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('team.deleteText')}</AlertDialogDescription>
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
