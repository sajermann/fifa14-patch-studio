import { cn } from '@/lib/utils'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { EntityIssues } from '@/components/common/form'
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
import { EntryDates } from '@/components/common/dates'
import type { KitPart, SquadRow, TeamDetail } from '@/api/types'
import { Facts, OriginalBadge, OverallBadge, RawTable, Section } from '@/components/common/detail'
import { EditActions, FieldsEditor, NamesGrid, useEntityForm } from '@/components/common/edit'
import { HideButton, OutOfPatchBadge, usePendingHide } from '@/components/common/HideButton'
import { Crest } from '@/components/common/pictures'
import { AdboardChoice, type PendingAdboard } from '@/components/adboard/AdboardChoice'
import { EquipmentChoice } from '@/components/equipment/EquipmentChoice'
import { TeamCrest } from '@/components/team/TeamCrest'
import { TeamKits } from '@/components/team/TeamKits'
import { TeamLeagues } from '@/components/team/TeamLeagues'
import { TeamSquad } from '@/components/team/TeamSquad'
import { TeamStadiums, type PendingStadium } from '@/components/team/TeamStadiums'
import { RESERVE, type PendingKit, type PendingPicture } from '@/components/team/pending'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom, useTabParam } from '@/lib/back'
import { toast } from '@/lib/notify'
import { useToken } from '@/state/queries'

const TABS = ['data', 'crest', 'kits', 'leagues', 'roster', 'stadium', 'other', 'raw'] as const

const sameIds = (a: number[], b: number[]) => a.length === b.length && a.every((v, i) => v === b[i])
const sameSet = (a: number[], b: number[]) => a.length === b.length && a.every((v) => b.includes(v))
type PendingLeagues = { ids: number[]; hidden: number[] } | null

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
  // the leagues the team plays in, being edited (null = the saved ones); Save sends them with the rest
  const [pendingLeagues, setPendingLeagues] = useState<PendingLeagues>(null)
  const [pendingStadium, setPendingStadium] = useState<PendingStadium>(null)
  const [pendingAdboard, setPendingAdboard] = useState<PendingAdboard>(null)
  const crestUrl = pendingCrest && pendingCrest !== 'remove' ? pendingCrest.url : null
  useEffect(() => () => void (crestUrl && URL.revokeObjectURL(crestUrl)), [crestUrl])
  const clearPending = () => {
    setPendingCrest(null)
    setPendingKits({})
    setPendingSquad(null)
    setPendingLeagues(null)
    setPendingStadium(null)
    setPendingAdboard(null)
    hide.clear()
  }
  const entity = useEntityForm({
    data: team,
    queryKey,
    invalidate: ['teams', 'league', 'leagues', 'options', 'stadiums', 'stadium'],
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
      if (pendingLeagues) saved = await api.saveTeamLeagues(id, pendingLeagues.ids, pendingLeagues.hidden)
      if (pendingStadium !== null) saved = await api.setTeamStadium(id, pendingStadium === 'game' ? null : pendingStadium)
      if (pendingAdboard !== null) saved = await api.setTeamAdboard(id, pendingAdboard === 'none' ? null : pendingAdboard)
      if (hide.pending !== null) saved = await api.setTeamHidden(id, hide.pending)
      clearPending()
      return saved
    },
    reset: () => {
      clearPending()
      return api.resetTeam(id)
    },
    extraDirty: pendingCrest !== null || Object.keys(pendingKits).length > 0 || pendingSquad !== null || pendingLeagues !== null || pendingStadium !== null || pendingAdboard !== null || hide.pending !== null,
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
  const savedLeagues = team.leagues.map((l) => l.id)
  const savedHidden = team.leagues.filter((l) => l.hidden).map((l) => l.id)
  const leagueIds = pendingLeagues?.ids ?? savedLeagues
  const hiddenLeagues = pendingLeagues?.hidden ?? savedHidden
  const setLeagues = (ids: number[], hidden: number[]) => setPendingLeagues(sameIds(ids, savedLeagues) && sameSet(hidden, savedHidden) ? null : { ids, hidden })
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
            <img src={crestUrl} alt="" className="size-24 shrink-0 rounded-lg bg-muted/40 object-contain" />
          ) : (
            // the same rounded square as the player's photo: the user's own picture gets the box the game's crests have
            <Crest
              id={team.id}
              size={256}
              available={team.has_crest || team.is_new}
              version={team.own_crest}
              className={cn('size-24 shrink-0 rounded-lg', team.own_crest && 'bg-muted/40')}
            />
          )}
          {/* the name with its details and badges on one line, the dates under it */}
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
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
              {!team.is_new && <OriginalBadge edited={team.edited} />}
              {hide.hidden && <OutOfPatchBadge alert label={team.is_new ? undefined : t('teams.hiddenByProject')} />}
            </div>
            <EntryDates entry={team} />
          </div>
        </div>
        <div className="flex flex-col items-end justify-between">
          <div className="flex flex-wrap gap-2">
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
          <EntityIssues kind="team" id={id} />
        </div>
      </div>
      {team.is_new && team.leagues.length === 0 && <p className="text-sm text-amber-600 dark:text-amber-400">{t('team.noLeague')}</p>}

      <Tabs {...tabs}>
        <TabsList>
          <TabsTrigger value="data">{t('team.tab.data')}</TabsTrigger>
          <TabsTrigger value="crest">{t('team.tab.crest')}</TabsTrigger>
          <TabsTrigger value="kits">
            {t('team.tab.kits')} ({team.kits.filter((k) => k.config || k.default).length})
          </TabsTrigger>
          <TabsTrigger value="leagues">
            {t('col.leagues')} ({leagueIds.length})
          </TabsTrigger>
          <TabsTrigger value="roster">
            {t('team.tab.roster')} ({squad.length})
          </TabsTrigger>
          <TabsTrigger value="stadium">{t('tab.stadium')}</TabsTrigger>
          <TabsTrigger value="other">{t('tab.other')}</TabsTrigger>
          <TabsTrigger value="raw">{t('tab.raw')}</TabsTrigger>
        </TabsList>
        <TabsContent value="data" className="space-y-4">
          {/* ratings and club in a column, the tactics beside them; the names below (the colors are on the crest tab) */}
          <div className="grid items-start gap-4 lg:grid-cols-2">
            <div className="space-y-4">
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
              <FieldsEditor form={team} groups={['club']} fields={entity.form.fields} setField={entity.setField} roster={team.roster} columns="md:grid-cols-1" bars />
            </div>
            <FieldsEditor form={team} groups={['tactics']} fields={entity.form.fields} setField={entity.setField} roster={team.roster} columns="md:grid-cols-1" bars />
          </div>
          <NamesGrid
            kind="team"
            columns={team.name_keys}
            languages={team.languages}
            original={team.original_names}
            names={entity.form.names}
            setNames={entity.setNames}
            required={team.is_new ? ['full'] : []}
          />
        </TabsContent>
        <TabsContent value="crest">
          <TeamCrest team={team} pending={pendingCrest} setPending={setPendingCrest} fields={entity.form.fields} setField={entity.setField} />
        </TabsContent>
        <TabsContent value="kits">
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
        <TabsContent value="leagues">
          <TeamLeagues ids={leagueIds} hidden={hiddenLeagues} setLeagues={setLeagues} linkState={from.state} />
        </TabsContent>
        <TabsContent value="roster" className="space-y-4">
          <TeamSquad
            team={team}
            rows={squad}
            setRows={setSquad}
            formation={formation}
            setFormation={(f) => entity.setField('formation', f)}
            fields={entity.form.fields}
            setField={entity.setField}
            linkState={from.state}
          />
        </TabsContent>
        <TabsContent value="stadium">
          <TeamStadiums
            stadiums={team.stadiums}
            customName={team.stadium_custom_name}
            changed={team.stadium_changed}
            gameStadium={team.game_stadium_id}
            pending={pendingStadium}
            onPending={setPendingStadium}
          />
        </TabsContent>
        {/* what else the team takes into its matches: its advertising board and its ball */}
        <TabsContent value="other">
          <div className="grid items-start gap-4 lg:grid-cols-2">
            <AdboardChoice kind="team" saved={team.adboard_id} pending={pendingAdboard} onPending={setPendingAdboard} />
            <EquipmentChoice kind="ball" owner={team.name} values={team.values} fields={entity.form.fields} setField={entity.setField} />
          </div>
        </TabsContent>
        <TabsContent value="raw">
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
