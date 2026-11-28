import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Loader2, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '@/api/client'
import { EntryDates } from '@/components/common/dates'
import { OriginalBadge, Section } from '@/components/common/detail'
import { EditActions, useEntityForm } from '@/components/common/edit'
import { HideButton, OutOfPatchBadge, usePendingHide } from '@/components/common/HideButton'
import { FormationPitch, SLOTS } from '@/components/formation/FormationPitch'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
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
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n, type MessageKey } from '@/i18n'
import { BackButton, useBack, useFrom } from '@/lib/back'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useOptions, useToken } from '@/state/queries'

// the game's "work rate" of a slot (attackingrole_<i> / defensiverole_<i>, tests FD2/FD3): 0 medium, 1 low, 2 high,
// 3 default (the game's own formations: 3 everywhere)
const ROLES: [number, MessageKey][] = [
  [3, 'formations.role3'],
  [1, 'formations.role1'],
  [0, 'formations.role0'],
  [2, 'formations.role2'],
]
const ATTACK_ARROWS = ['—', '↑', '↗', '→', '↘', '↓']
const DEFENSE_ARROWS = ['—', '↑', '↖', '←', '↙', '↓']

function SmallSelect({
  value,
  options,
  onChange,
  disabled,
}: {
  value: number
  options: [number, string][]
  onChange: (v: number) => void
  disabled?: boolean
}) {
  return (
    <Select value={String(value)} onValueChange={(v) => onChange(Number(v))} disabled={disabled}>
      <SelectTrigger size="sm" className="w-full min-w-24">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map(([v, label]) => (
          <SelectItem key={v} value={String(v)}>
            {label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** One formation: one of the game's 33 (read only, with Copy) or the user's (name, the drawing on a pitch like the
 * game's - drag the players -, and per slot its position, work rates and run arrows; hide, delete), with the teams
 * that have it. Saved as the other screens (Save / Discard). */
export function FormationPage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const positions = (useOptions().data?.positions ?? []).filter((p) => p.id >= 0 && p.id <= 27)
  const queryKey = ['formation', token, id]
  const { data, isLoading, error } = useQuery({
    queryKey,
    queryFn: () => api.formation(id),
    enabled: !!token,
  })
  const back = useBack({ to: '/formations', label: { key: 'nav.formations' } })
  const from = useFrom(data ? data.name : { key: 'nav.formations' })
  const hide = usePendingHide(data?.hidden)
  const [selected, setSelected] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)
  const isNew = !!data?.is_new
  const entity = useEntityForm({
    data,
    queryKey,
    invalidate: ['formations', 'team', 'issues'],
    save: async (f) => {
      let saved = await api.saveFormation(id, {
        name: typeof f.fields.name === 'string' ? f.fields.name : (data?.name ?? ''),
        columns: (f.fields.columns as Record<string, number> | undefined) ?? data?.columns,
      })
      if (hide.pending !== null) saved = await api.setFormationHidden(id, hide.pending)
      hide.clear()
      return saved
    },
    reset: async () => {
      hide.clear()
      return api.formation(id)
    },
    extraDirty: hide.pending !== null,
    onDiscard: hide.clear,
    // a name, and 11 different positions
    invalid: (f) => {
      const cols = (f.fields.columns as Record<string, number> | undefined) ?? data?.columns ?? {}
      const used = new Set(Array.from({ length: SLOTS }, (_, i) => cols[`position${i}`]))
      return !(typeof f.fields.name === 'string' ? f.fields.name : (data?.name ?? '')).trim() || used.size !== SLOTS
    },
  })
  const remove = useMutation({
    mutationFn: () => api.deleteFormation(id),
    onSuccess: () => {
      for (const k of ['formations', 'team', 'status', 'issues']) void qc.invalidateQueries({ queryKey: [k] })
      toast.success(t('formations.deleted'))
      navigate(back.to, { state: back.state })
    },
    onError: (e: Error) => {
      setDeleting(false)
      toast.error(e.message)
    },
  })
  const copy = useMutation({
    mutationFn: () =>
      api.createFormation({
        name: t('formations.copyName', { name: data?.name ?? '' }).slice(0, 24),
        copy_of: id,
      }),
    onSuccess: (f) => {
      void qc.invalidateQueries({ queryKey: ['formations'] })
      toast.success(t('formations.copied'))
      navigate(`/formations/${f.id}`, { state: from.state })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  if (isLoading) return <LoadingBlock />
  if (!data)
    return (
      <div className="space-y-2">
        <BackButton back={back} />
        <p className="text-muted-foreground">{error?.message ?? t('list.empty')}</p>
      </div>
    )
  const name = typeof entity.form.fields.name === 'string' ? entity.form.fields.name : data.name
  const columns = (entity.form.fields.columns as Record<string, number> | undefined) ?? data.columns
  const setColumns = (change: Record<string, number>) => entity.setField('columns', { ...columns, ...change })
  const codes = Array.from({ length: SLOTS }, (_, i) => columns[`position${i}`])
  const posName = (code: number) => positions.find((p) => p.id === code)?.name ?? String(code)
  const repeated = new Set(codes.filter((c, i) => codes.indexOf(c) !== i))
  const roleOptions: [number, string][] = ROLES.map(([v, key]) => [v, t(key)])
  const arrows = (list: string[]): [number, string][] => list.map((a, v) => [v, v ? a : t('formations.runNone')])
  return (
    <div className="space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="min-w-0 text-2xl font-semibold break-words">{name.trim() || data.name}</h1>
            <span className="shrink-0 text-sm text-muted-foreground tabular-nums">ID {data.id}</span>
            {!isNew && <OriginalBadge />}
            {hide.hidden && <OutOfPatchBadge alert />}
          </div>
          {isNew && <EntryDates entry={data} />}
        </div>
        <div className="flex flex-wrap gap-2">
          {isNew && <EditActions edited={false} entity={entity} />}
          <Button variant="outline" size="sm" title={t('formations.copyHint')} disabled={copy.isPending || entity.dirty} onClick={() => copy.mutate()}>
            {copy.isPending ? <Loader2 className="animate-spin" /> : <Copy />} {t('formations.copy')}
          </Button>
          {isNew && (
            <>
              <HideButton
                variant="outline"
                hidden={hide.hidden}
                onToggle={hide.toggle}
                hideHint={t('formations.hideHint')}
                showHint={t('formations.showHint')}
              />
              <Button variant="outline" size="sm" onClick={() => setDeleting(true)}>
                <Trash2 /> {t('common.delete')}
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <div className="space-y-4">
          {isNew ? (
            <Section title={t('formations.name')} description={t('formations.nameHint')}>
              <Input value={name} maxLength={24} onChange={(e) => entity.setField('name', e.target.value)} />
            </Section>
          ) : (
            <Section title={t('formations.gameTitle')} description={t('formations.gameHint')}>
              {null}
            </Section>
          )}
          <Section title={t('formations.drawing')} description={t(isNew ? 'formations.drawingHint' : 'formations.drawingGameHint')}>
            <FormationPitch
              columns={columns}
              labels={codes.map(posName)}
              selected={selected}
              onSelect={setSelected}
              onMove={
                isNew
                  ? (slot, x, y) =>
                      setColumns({
                        [`offset${slot}x`]: x,
                        [`offset${slot}y`]: y,
                      })
                  : undefined
              }
            />
            <p className="pt-2 text-xs text-muted-foreground">{t('formations.arrowsHint')}</p>
          </Section>
          <Section title={t('formations.usedBy')} description={t('formations.usedByHint')}>
            {data.teams.length ? (
              <ul className="space-y-1 text-sm">
                {data.teams.map((tm) => (
                  <li key={tm.id}>
                    <Link to={`/teams/${tm.id}?tab=roster`} state={from.state} className="underline-offset-4 hover:underline">
                      {tm.name}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">{t('formations.notUsed')}</p>
            )}
          </Section>
        </div>
        <Section title={t('formations.slots')} description={t('formations.slotsHint')}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">#</TableHead>
                <TableHead>{t('formations.colPosition')}</TableHead>
                <TableHead>{t('formations.colAttackRole')}</TableHead>
                <TableHead>{t('formations.colDefenseRole')}</TableHead>
                <TableHead>{t('formations.colAttackRun')}</TableHead>
                <TableHead>{t('formations.colDefenseRun')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {codes.map((code, i) => (
                <TableRow key={i} className={cn(selected === i && 'bg-accent')} onClick={() => setSelected(i)}>
                  <TableCell className="tabular-nums text-muted-foreground">{i + 1}</TableCell>
                  <TableCell>
                    {i === 0 || !isNew ? (
                      <span className={cn(repeated.has(code) && 'text-destructive')}>{posName(code)}</span>
                    ) : (
                      <SmallSelect
                        value={code}
                        options={positions.filter((p) => p.id > 0).map((p) => [p.id, p.name])}
                        onChange={(v) => setColumns({ [`position${i}`]: v })}
                      />
                    )}
                  </TableCell>
                  {i === 0 ? (
                    // the game takes no work rate or run for the goalkeeper
                    <TableCell colSpan={4} className="text-muted-foreground">
                      —
                    </TableCell>
                  ) : (
                    <>
                      {(['attackingrole_', 'defensiverole_'] as const).map((c) => (
                        <TableCell key={c}>
                          <SmallSelect
                            value={columns[`${c}${i}`] ?? 3}
                            options={roleOptions}
                            disabled={!isNew}
                            onChange={(v) => setColumns({ [`${c}${i}`]: v })}
                          />
                        </TableCell>
                      ))}
                      <TableCell>
                        <SmallSelect
                          value={columns[`attackingdirection_${i}`] ?? 0}
                          options={arrows(ATTACK_ARROWS)}
                          disabled={!isNew}
                          onChange={(v) => setColumns({ [`attackingdirection_${i}`]: v })}
                        />
                      </TableCell>
                      <TableCell>
                        <SmallSelect
                          value={columns[`defensivedirection_${i}`] ?? 0}
                          options={arrows(DEFENSE_ARROWS)}
                          disabled={!isNew}
                          onChange={(v) => setColumns({ [`defensivedirection_${i}`]: v })}
                        />
                      </TableCell>
                    </>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {repeated.size > 0 && <p className="pt-2 text-sm text-destructive">{t('formations.repeated')}</p>}
        </Section>
      </div>

      <AlertDialog open={deleting} onOpenChange={(o) => !remove.isPending && setDeleting(o)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('formations.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('formations.deleteText')}</AlertDialogDescription>
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
