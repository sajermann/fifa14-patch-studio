import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Loader2, ScanFace, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api, type PlayerTeamBody } from '@/api/client'
import { EntryDates } from '@/components/common/dates'
import type { PlayerDetail } from '@/api/types'
import { OriginalBadge, OverallBadge, RawTable, Section } from '@/components/common/detail'
import { computeOverall } from '@/lib/overall'
import { EditActions, FieldsEditor, useEntityForm, useFieldLabel } from '@/components/common/edit'
import { HideButton, OutOfPatchBadge, usePendingHide } from '@/components/common/HideButton'
import { Photo } from '@/components/common/pictures'
import { EntityIssues, Stepper } from '@/components/common/form'
import { EquipmentChoice } from '@/components/equipment/EquipmentChoice'
import { PlayerAccessories } from '@/components/player/PlayerAccessories'
import { PlayerLook } from '@/components/player/PlayerLook'
import { PlayerPhoto, type PendingPhoto } from '@/components/player/PlayerPhoto'
import { PlayerTeams, sameTeams, savedTeams } from '@/components/player/PlayerTeams'
import { PlayerTraits } from '@/components/player/PlayerTraits'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useTabParam } from '@/lib/back'
import { toast } from '@/lib/notify'
import { useStatus, useToken } from '@/state/queries'

const TABS = ['data', 'ratings', 'traits', 'look', 'accessories', 'raw'] as const
const NAME_FIELDS = ['name.first', 'name.last', 'name.common']

/** The codes of one group (accessories, animations): the game's values, chosen with the arrows (the Street Studio's
 * Stepper); "default" = the game's value. */
function CodeGroup({ player, group, fields, setField, title, description }: { player: PlayerDetail; group: string; fields: Record<string, unknown>; setField: (n: string, v: number | null) => void; title: string; description?: string }) {
  const token = useToken()
  const { label, option } = useFieldLabel()
  const options = useQuery({ queryKey: ['player-options', token], queryFn: api.playerOptions, enabled: !!token, staleTime: Infinity }).data
  const specs = player.fields.filter((f) => f.group === group)
  return (
    <Section title={title} description={description}>
      <div className="grid gap-x-8 gap-y-4 sm:grid-cols-2 xl:grid-cols-3">
        {specs.map((spec) => {
          const own = fields[spec.name]
          const original = player.values[spec.name]
          const named = (v: number) => option(spec.name, v)
          const hasNames = (options?.codes[spec.name] ?? []).some((v) => named(v) !== String(v))
          return (
            <div key={spec.name} className="grid gap-1.5">
              <p className="text-sm font-medium">{label(spec.name)}</p>
              <Stepper
                value={typeof own === 'number' ? own : undefined}
                options={options?.codes[spec.name] ?? []}
                inherited={typeof original === 'number' ? original : undefined}
                onChange={(v) => setField(spec.name, v ?? null)}
                label={hasNames ? named : undefined}
                wide={hasNames}
              />
            </div>
          )
        })}
      </div>
    </Section>
  )
}

export function PlayerPage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const lang = useStatus().data?.names_language ?? 'eng_us'
  const queryKey = ['player', token, lang, id]
  const { data, isLoading } = useQuery({ queryKey, queryFn: () => api.player(id), enabled: !!token })
  const options = useQuery({ queryKey: ['player-options', token], queryFn: api.playerOptions, enabled: !!token, staleTime: Infinity }).data
  const tabs = useTabParam(TABS[0])
  const back = useBack({ to: '/players', label: { key: 'nav.players' } })
  const hide = usePendingHide(data?.hidden)
  const [deleting, setDeleting] = useState(false)
  // not saved yet: Save sends them with the fields
  const [pendingPhoto, setPendingPhoto] = useState<PendingPhoto>(null)
  const [pendingTeams, setPendingTeams] = useState<PlayerTeamBody[] | null>(null)
  const photoUrl = pendingPhoto && pendingPhoto !== 'remove' && 'data' in pendingPhoto ? pendingPhoto.url : null
  useEffect(() => () => void (photoUrl && URL.revokeObjectURL(photoUrl)), [photoUrl])
  const clearPending = () => {
    setPendingPhoto(null)
    setPendingTeams(null)
    hide.clear()
  }
  const invalidate = ['players', 'team', 'teams', 'player-look']
  const entity = useEntityForm({
    data,
    queryKey,
    invalidate,
    save: async (f) => {
      let saved = await api.savePlayer(id, f.fields, pendingTeams ?? undefined)
      if (pendingPhoto === 'remove') saved = await api.removePlayerPhoto(id)
      else if (pendingPhoto && 'data' in pendingPhoto) saved = await api.uploadPlayerPhoto(id, pendingPhoto.data)
      else if (pendingPhoto) saved = await api.playerPhotoFromPack(id, pendingPhoto.pack, pendingPhoto.face)
      if (hide.pending !== null) saved = await api.setPlayerHidden(id, hide.pending)
      clearPending()
      return saved
    },
    reset: () => {
      clearPending()
      return api.resetPlayer(id)
    },
    extraDirty: pendingPhoto !== null || pendingTeams !== null || hide.pending !== null,
    onDiscard: clearPending,
    // a created player has no name of the game: one of his names is required
    invalid: (f) => !!data?.is_new && !NAME_FIELDS.some((k) => String(f.fields[k] ?? '').trim()),
  })
  const after = () => {
    for (const k of [...invalidate, 'status', 'options']) void qc.invalidateQueries({ queryKey: [k] })
  }
  const remove = useMutation({
    mutationFn: () => api.deletePlayer(id),
    onSuccess: () => {
      after()
      toast.success(t('player.deleted'))
      navigate(back.to, { state: back.state })
    },
    onError: (e: Error) => {
      setDeleting(false)
      toast.error(e.message)
    },
  })
  const copy = useMutation({
    mutationFn: () => api.createPlayer({ fields: { 'name.common': t('player.copyName', { name: data?.name ?? '' }).slice(0, 40) }, template: id }),
    onSuccess: (p) => {
      after()
      toast.success(t('player.created'))
      navigate(`/players/${p.id}`)
    },
    onError: (e: Error) => toast.error(e.message),
  })
  if (isLoading || !data) return <LoadingBlock />
  const teams = pendingTeams ?? savedTeams(data)
  const setTeams = (rows: PlayerTeamBody[]) => setPendingTeams(sameTeams(rows, savedTeams(data)) ? null : rows)
  const fields = entity.form.fields
  // the overall follows the bars as they move (the game works it out the same way)
  const liveOverall = computeOverall((col) => {
    const edited = fields[col]
    return typeof edited === 'number' ? edited : (data.values[col] as number | undefined)
  })
  // a real face: the one chosen here (a pack's or another player's), else the game's own one
  const face = fields.face as { source?: string } | null | undefined
  const realFace = face?.source ? face.source !== 'generic' : data.game_face
  const editor = (groups: string[], columns?: string, bars?: boolean) => <FieldsEditor form={data} groups={groups} fields={fields} setField={entity.setField} columns={columns} bars={bars} />
  return (
    <div className="space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          {photoUrl ? (
            <img src={photoUrl} alt="" className="size-24 shrink-0 rounded-lg bg-muted/40 object-contain" />
          ) : (
            <Photo id={data.id} size={256} available={data.has_photo} className="size-24 shrink-0 rounded-lg bg-muted/40" />
          )}
          {/* the name with its details and badges on one line, the dates under it */}
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
              <h1 className="min-w-0 text-2xl font-semibold break-words">{data.name}</h1>
              <span className="flex shrink-0 items-center gap-2 text-sm text-muted-foreground tabular-nums">
                {realFace && <ScanFace className="size-5 text-emerald-600 dark:text-emerald-400" aria-label={t('squad.hasFace')} />}
                <OverallBadge value={liveOverall ?? data.overall} />
                {t('player.idHint', { id: data.id })}
              </span>
              {!data.is_new && <OriginalBadge edited={data.edited} />}
              {hide.hidden && <OutOfPatchBadge alert />}
            </div>
            <EntryDates entry={data} />
          </div>
        </div>
        <div className="flex flex-col items-end justify-between">
          <div className="flex flex-wrap gap-2">
            <EditActions edited={data.edited && !data.is_new} entity={entity} />
            <Button variant="outline" size="sm" title={t('player.copyHint')} disabled={copy.isPending} onClick={() => copy.mutate()}>
              {copy.isPending ? <Loader2 className="animate-spin" /> : <Copy />} {t('player.copy')}
            </Button>
            {data.is_new && (
              <>
                <HideButton variant="outline" hidden={hide.hidden} onToggle={hide.toggle} hideHint={t('players.hideHint')} showHint={t('players.showHint')} />
                <Button variant="outline" size="sm" onClick={() => setDeleting(true)}>
                  <Trash2 /> {t('common.delete')}
                </Button>
              </>
            )}
          </div>
          <EntityIssues kind="player" id={id} />
        </div>
      </div>
      {data.is_new && !NAME_FIELDS.some((k) => String(fields[k] ?? '').trim()) && <p className="text-sm text-amber-600 dark:text-amber-400">{t('player.nameRequired')}</p>}
      <Tabs {...tabs}>
        <TabsList>
          <TabsTrigger value="data">{t('player.tab.data')}</TabsTrigger>
          <TabsTrigger value="ratings">{t('player.tab.ratings')}</TabsTrigger>
          <TabsTrigger value="traits">{t('player.tab.traits')}</TabsTrigger>
          <TabsTrigger value="look">{t('player.tab.look')}</TabsTrigger>
          <TabsTrigger value="accessories">{t('player.tab.accessories')}</TabsTrigger>
          <TabsTrigger value="raw">{t('tab.raw')}</TabsTrigger>
        </TabsList>
        <TabsContent value="data" className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
            {editor(['names', 'info'], 'md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2')}
            <PlayerPhoto player={data} pending={pendingPhoto} setPending={setPendingPhoto} />
          </div>
          <PlayerTeams player={data} rows={teams} setRows={setTeams} />
          {editor(['positions', 'style', 'career'], 'lg:grid-cols-3')}
        </TabsContent>
        <TabsContent value="ratings" className="space-y-4">
          <div className="flex items-center gap-2 text-sm">
            {t('col.overall')} <OverallBadge value={liveOverall ?? data.overall} />
            <span className="text-xs text-muted-foreground">{t('player.overallHint')}</span>
          </div>
          {editor(['pace', 'shooting', 'passing', 'dribbling', 'defending', 'physical', 'goalkeeping'], 'md:grid-cols-2 xl:grid-cols-4', true)}
        </TabsContent>
        <TabsContent value="traits">
          <PlayerTraits all={options?.traits ?? []} value={fields.traits} original={data.values.traits} onChange={(v) => entity.setField('traits', v)} />
        </TabsContent>
        <TabsContent value="look">
          <PlayerLook
            player={data}
            fields={fields}
            setField={entity.setField}
            options={options}
            teams={teams}
            pendingPhoto={pendingPhoto}
          />
        </TabsContent>
        <TabsContent value="accessories" className="space-y-4">
          <div className="grid items-start gap-4 lg:grid-cols-2">
            <EquipmentChoice kind="boot" owner={data.name} values={data.values} fields={fields} setField={entity.setField} />
            <EquipmentChoice
              kind="glove"
              owner={data.name}
              values={data.values}
              fields={fields}
              setField={entity.setField}
              preferredPosition={(typeof fields.preferredposition1 === 'number' ? fields.preferredposition1 : data.values.preferredposition1) as number | null}
            />
          </div>
          <PlayerAccessories player={data} fields={fields} setField={entity.setField} options={options?.accessories} />
          <CodeGroup player={data} group="animations" fields={fields} setField={entity.setField} title={t('fieldGroup.animations')} description={t('code.hint')} />
        </TabsContent>
        <TabsContent value="raw">
          <Section title={t('tab.raw')}>
            <RawTable raw={data.raw} />
          </Section>
        </TabsContent>
      </Tabs>
      <AlertDialog open={deleting} onOpenChange={(o) => !remove.isPending && setDeleting(o)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('player.deleteTitle', { name: data.name })}</AlertDialogTitle>
            <AlertDialogDescription>{t('player.deleteDescription')}</AlertDialogDescription>
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
