import { useQuery } from '@tanstack/react-query'
import { CornerUpLeft, CornerUpRight, Crown, Dices, Goal, Loader2, type LucideIcon, MoveUpRight, Plus, Target, UserMinus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '@/api/client'
import type { FieldValue, PlayerRow, SquadRow, TeamDetail } from '@/api/types'
import { FillScroll, OriginalBadge, OverallBadge, Section } from '@/components/common/detail'
import { OutOfPatchBadge } from '@/components/common/HideButton'
import { PickerDialog, type PickerItem } from '@/components/common/PickerDialog'
import { Photo } from '@/components/common/pictures'
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
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n, type MessageKey } from '@/i18n'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useOptions, useToken } from '@/state/queries'
import { BENCH, RESERVE } from './pending'

interface PlayerInfo {
  name: string
  overall: number | null
  position: number | null
  position_name: string | null
  has_photo: boolean
  is_new: boolean
  edited: boolean
}

const infoOf = (p: PlayerInfo): PlayerInfo => ({
  name: p.name,
  overall: p.overall,
  position: p.position,
  position_name: p.position_name,
  has_photo: p.has_photo,
  is_new: p.is_new,
  edited: p.edited,
})

const SCROLL_RESERVE = 330 // height kept under the table for the captain and takers card
const GOALKEEPERS = 3 // goalkeepers a generated squad ends up with (the existing ones count)

// captain and set-piece takers: one column of the table and one select of the card below (a database column each)
const ROLES: { column: string; label: MessageKey; icon: LucideIcon }[] = [
  { column: 'captainid', label: 'takers.captainRole', icon: Crown },
  { column: 'penaltytakerid', label: 'takers.penalty', icon: Target },
  { column: 'freekicktakerid', label: 'takers.freeKick', icon: Goal },
  { column: 'longkicktakerid', label: 'takers.longFreeKick', icon: MoveUpRight },
  { column: 'leftcornerkicktakerid', label: 'takers.leftCorner', icon: CornerUpLeft },
  { column: 'rightcornerkicktakerid', label: 'takers.rightCorner', icon: CornerUpRight },
]

/** Dialog: search every player of the game and add one to the squad (a player can be in several teams). */
function AddPlayerDialog({ open, onOpenChange, chosen, onPick }: { open: boolean; onOpenChange: (o: boolean) => void; chosen: number[]; onPick: (p: PlayerRow) => void }) {
  const { t } = useI18n()
  const token = useToken()
  const [q, setQ] = useState('')
  const { data } = useQuery({
    queryKey: ['players', token, 'picker', q],
    queryFn: () => api.players({ q, size: 50, sort: 'overall' }),
    enabled: open && !!token,
    placeholderData: (previous) => previous,
  })
  const items = (data?.items ?? []).filter((p) => !chosen.includes(p.id))
  const toItem = (p: PlayerRow): PickerItem<number> => ({
    key: p.id,
    icon: <Photo id={p.id} size={64} available={p.has_photo} className="size-8 rounded-full bg-muted object-cover" />,
    title: p.name,
    subtitle: [p.position_name, p.overall, p.team].filter((v) => v !== null && v !== undefined && v !== '').join(' · '),
  })
  return (
    <PickerDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('squad.addTitle')}
      description={t('squad.addDescription')}
      placeholder={t('players.search')}
      query={q}
      onQuery={setQ}
      groups={[{ items: items.map(toItem) }]}
      empty={t('field.pick.empty')}
      onPick={(id) => {
        const p = items.find((x) => x.id === id)
        if (p) onPick(p)
      }}
    />
  )
}

/** The squad, laid out like the FS4 roster: formation (one of the game's 33), one row per player (name with picture
 * and badges, number, position in the lineup = a starter's slot, the bench (28) or out of the squad (29), the captain
 * and takers he is, in the patch or not, remove) and, below, the card that picks the captain and each taker.
 * More than `max_squad` stay out of the patch. */
export function TeamSquad({
  team,
  rows,
  setRows,
  formation,
  setFormation,
  fields,
  setField,
  linkState,
}: {
  team: TeamDetail
  rows: SquadRow[]
  setRows: (rows: SquadRow[]) => void
  formation: number | null
  setFormation: (id: number) => void
  /** the captain and takers as edited (database column -> player id) */
  fields: Record<string, FieldValue>
  setField: (name: string, value: FieldValue) => void
  /** router state of the links to the players (the Back button of their page returns here) */
  linkState?: unknown
}) {
  const { t } = useI18n()
  const positions = useOptions().data?.positions ?? []
  const [adding, setAdding] = useState(false)
  const [added, setAdded] = useState<Record<number, PlayerInfo>>({})
  const info = useMemo(() => {
    const out: Record<number, PlayerInfo> = { ...added }
    for (const p of team.roster) out[p.id] = infoOf(p)
    return out
  }, [team.roster, added])
  const current = team.formations.find((f) => f.id === formation) ?? team.formations[0]
  const slots = current?.positions ?? []
  const posName = (code: number) => positions.find((p) => p.id === code)?.name ?? String(code)
  const starters = rows.filter((r) => r.slot < BENCH)
  const kept = rows.filter((r) => !r.hidden) // a player hidden in this team stays out of the patch
  const inPatch = Math.min(kept.length, team.max_squad)
  const order = (r: SquadRow) => (r.slot < BENCH ? slots.indexOf(r.slot) : r.slot * 100)
  const shown = [...rows].sort((a, b) => order(a) - order(b))
  const numbers = rows.map((r) => r.jersey).filter((n) => n !== null)
  const repeated = new Set(numbers.filter((n, i) => numbers.indexOf(n) !== i))
  // who the takers can be: players already in the saved squad and still in it (the game takes only those)
  const savedIds = new Set(team.roster.map((p) => p.id))
  const takerChoices = kept.filter((r) => savedIds.has(r.player))
  // a captain or taker who is not in this squad (a new team starts with the ones of the model team) counts as nobody
  const roleValue = (column: string) => {
    const edited = fields[column]
    const value = typeof edited === 'number' ? edited : (team.values[column] as number | null | undefined)
    return takerChoices.some((r) => r.player === value) ? value : undefined
  }
  const setSlot = (player: number, slot: number) =>
    setRows(rows.map((r) => (r.player === player ? { ...r, slot } : slot < BENCH && r.slot === slot ? { ...r, slot: BENCH } : r)))
  const changeFormation = (id: number) => {
    const next = team.formations.find((f) => f.id === id)
    if (!next) return
    // each starter keeps his place in the lineup (the i-th slot of the old formation becomes the i-th of the new)
    setRows(rows.map((r) => (r.slot < BENCH && slots.includes(r.slot) ? { ...r, slot: next.positions[slots.indexOf(r.slot)] } : r)))
    setFormation(id)
  }
  const freeNumber = () => {
    for (let n = 1; n <= 99; n++) if (!numbers.includes(n)) return n
    return null
  }
  // where a player added now goes: a free position of the formation that suits him (his own, else the nearest one; a
  // goalkeeper only in goal), else the bench while it has places, else out of the squad
  const placeFor = (position: number | null, taken: SquadRow[]) => {
    const open = slots.filter((code) => !taken.some((r) => r.slot === code))
    const pos = position ?? 25
    const free = open.includes(pos)
      ? pos
      : pos === 0
        ? undefined
        : open.filter((code) => code !== 0).sort((a, b) => Math.abs(a - pos) - Math.abs(b - pos))[0]
    return free ?? (taken.filter((r) => r.slot === BENCH).length < 12 ? BENCH : RESERVE)
  }
  const [confirmingGenerate, setConfirmingGenerate] = useState(false)
  const [generating, setGenerating] = useState(false)
  const missing = Math.max(team.max_squad - kept.length, 0)
  // a squad needs goalkeepers: the generated players include as many as it takes to have GOALKEEPERS in the patch
  const haveKeepers = kept.filter((r) => info[r.player]?.position === 0).length
  const newKeepers = Math.min(Math.max(GOALKEEPERS - haveKeepers, 0), missing)
  // new random players for the free places: created in the project, put in the squad being edited (Save keeps them)
  const generatePlayers = async () => {
    setGenerating(true)
    try {
      const made = await api.generatePlayers(team.id, missing, newKeepers)
      const used = new Set(numbers)
      const free = Array.from({ length: 99 }, (_, i) => i + 1).filter((n) => !used.has(n))
      const next = [...rows]
      const infos: Record<number, PlayerInfo> = {}
      for (const p of made) {
        const at = Math.floor(Math.random() * free.length)
        const jersey = free.length ? free.splice(at, 1)[0] : null // a random free number, like the Street Studio
        next.push({ player: p.id, jersey, slot: placeFor(p.position, next) })
        infos[p.id] = infoOf({ name: p.name, overall: p.overall, position: p.position, position_name: p.position_name, has_photo: p.has_photo, is_new: true, edited: false })
      }
      setAdded((a) => ({ ...a, ...infos }))
      setRows(next)
      toast.success(made.length === 1 ? t('roster.playerGenerated') : t('roster.playersGenerated', { count: made.length }))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('roster.generateFailed'))
    } finally {
      setGenerating(false)
    }
  }
  return (
    <div className="space-y-4">
      <Section
        title={
          <>
            {t('squad.title')}{' '}
            <span className="font-normal text-muted-foreground">({t('squad.count', { count: inPatch, max: team.max_squad, total: rows.length })})</span>
          </>
        }
        description={t('squad.hint', { max: team.max_squad })}
        action={
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
              <Plus /> {t('squad.add')}
            </Button>
            {team.is_new && (
              <Button variant="outline" size="sm" onClick={() => setConfirmingGenerate(true)} disabled={generating || missing === 0}>
                {generating ? <Loader2 className="animate-spin" /> : <Dices />} {t('roster.generatePlayers')}
              </Button>
            )}
          </div>
        }
      >
        <div className="mb-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <label className="flex items-center gap-2">
            {t('squad.formation')}
            <Select value={current ? String(current.id) : ''} onValueChange={(v) => changeFormation(Number(v))}>
              <SelectTrigger className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {team.formations.map((f) => (
                  <SelectItem key={f.id} value={String(f.id)}>
                    {f.name} <span className="text-muted-foreground">({f.positions.slice(1).map(posName).join(' ')})</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <span className={cn('tabular-nums', starters.length !== 11 && 'text-amber-600 dark:text-amber-400')}>{t('squad.starters', { count: starters.length })}</span>
          <span className="tabular-nums">{t('squad.bench', { count: rows.filter((r) => r.slot === BENCH).length })}</span>
        </div>
        {starters.length < 11 && rows.length >= 11 && <p className="mb-2 text-xs text-amber-600 dark:text-amber-400">{t('squad.fillHint')}</p>}
        {kept.length < 11 && <p className="mb-2 text-xs text-amber-600 dark:text-amber-400">{t('squad.tooFew')}</p>}
        <FillScroll reserve={SCROLL_RESERVE}>
        <Table>
          <TableHeader className="sticky top-0 z-10 bg-card shadow-[0_1px_0_var(--border)]">
            <TableRow>
              <TableHead>{t('col.name')}</TableHead>
              <TableHead className="w-20">{t('col.overall')}</TableHead>
              <TableHead className="w-24">{t('col.number')}</TableHead>
              <TableHead className="w-44">{t('col.position')}</TableHead>
              {ROLES.map(({ column, label, icon: Icon }) => (
                <TableHead key={column} className="w-8 px-1 text-center" title={t(label)}>
                  <Icon className="mx-auto size-4" aria-label={t(label)} />
                </TableHead>
              ))}
              <TableHead className="w-20">{t('roster.inPatch')}</TableHead>
              <TableHead className="w-28" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((r) => {
              const p = info[r.player]
              const overLimit = !r.hidden && kept.indexOf(r) >= team.max_squad
              return (
                <TableRow key={r.player}>
                  <TableCell>
                    <span className="flex items-center gap-2">
                      <Photo id={r.player} size={64} available={p?.has_photo ?? true} className="size-8 shrink-0 rounded-full bg-muted object-cover" />
                      <Link to={`/players/${r.player}`} state={linkState} className={cn('font-medium underline-offset-4 hover:underline', (r.hidden || overLimit) && 'text-muted-foreground')}>
                        {p?.name ?? `#${r.player}`}
                      </Link>
                      {/* the game's players say original / updated; the ones the user made have no badge */}
                      {!p?.is_new && <OriginalBadge edited={p?.edited} />}
                      {r.hidden ? <OutOfPatchBadge label={t('playerTeams.hidden')} /> : overLimit && <OutOfPatchBadge label={t('squad.overLimit')} />}
                    </span>
                  </TableCell>
                  <TableCell>
                    <OverallBadge value={p?.overall ?? null} />
                  </TableCell>
                  <TableCell>
                    <Input
                      type="number"
                      min={1}
                      max={99}
                      className={cn('h-8 tabular-nums', r.jersey !== null && repeated.has(r.jersey) && 'border-destructive')}
                      value={r.jersey ?? ''}
                      onChange={(e) => setRows(rows.map((x) => (x.player === r.player ? { ...x, jersey: e.target.value === '' ? null : Math.min(99, Math.max(1, Number(e.target.value))) } : x)))}
                    />
                  </TableCell>
                  <TableCell>
                    <Select value={String(r.slot)} onValueChange={(v) => setSlot(r.player, Number(v))}>
                      <SelectTrigger size="sm" className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {slots.map((code) => (
                          <SelectItem key={code} value={String(code)}>
                            {posName(code)}
                          </SelectItem>
                        ))}
                        {r.slot < BENCH && !slots.includes(r.slot) && <SelectItem value={String(r.slot)}>{posName(r.slot)}</SelectItem>}
                        <SelectItem value={String(BENCH)}>{t('squad.benchRole')}</SelectItem>
                        <SelectItem value={String(RESERVE)}>{t('squad.reserveRole')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  {ROLES.map(({ column, label, icon: Icon }) => (
                    <TableCell key={column} className="px-1 text-center">
                      {roleValue(column) === r.player && <Icon className="mx-auto size-4 text-primary" aria-label={t(label)} />}
                    </TableCell>
                  ))}
                  <TableCell>
                    <Switch
                      checked={!r.hidden}
                      title={r.hidden ? t('squad.showHint') : t('squad.hideHint')}
                      onCheckedChange={(v) => setRows(rows.map((x) => (x.player === r.player ? { ...x, hidden: !v } : x)))}
                    />
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" title={t('squad.remove')} onClick={() => setRows(rows.filter((x) => x.player !== r.player))}>
                      <UserMinus /> {t('common.remove')}
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5 + ROLES.length} className="py-8 text-center text-muted-foreground">
                  {t('squad.empty')}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        </FillScroll>
        <AddPlayerDialog
          open={adding}
          onOpenChange={setAdding}
          chosen={rows.map((r) => r.player)}
          onPick={(p) => {
            setAdded((a) => ({ ...a, [p.id]: infoOf({ ...p, is_new: !!(p as { is_new?: boolean }).is_new, edited: !!(p as { edited?: boolean }).edited }) }))
            // a free position of the formation that suits him: his own, else the nearest one (a goalkeeper only in goal)
            setRows([...rows, { player: p.id, jersey: freeNumber(), slot: placeFor(p.position, rows) }])
          }}
        />
        <AlertDialog open={confirmingGenerate} onOpenChange={setConfirmingGenerate}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('roster.generateTitle')}</AlertDialogTitle>
              <AlertDialogDescription>
                {missing === 1
                  ? t('roster.generateDescriptionOne', { max: team.max_squad })
                  : t('roster.generateDescription', { count: missing, max: team.max_squad })}{' '}
                {newKeepers > 0 && t('roster.generateKeepers', { count: newKeepers })}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={() => void generatePlayers()}>{t('roster.generatePlayers')}</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </Section>
      <Section title={t('takers.title')} description={t('takers.description')}>
        <div className="grid gap-4 sm:grid-cols-2">
          {ROLES.map(({ column, label, icon: Icon }) => {
            const value = roleValue(column)
            return (
              <div key={column} className="grid gap-1.5 text-sm">
                <span className="flex items-center gap-1.5 font-medium">
                  <Icon className="size-4" /> {t(label)}
                </span>
                <Select value={value != null ? String(value) : ''} onValueChange={(v) => setField(column, Number(v))}>
                  <SelectTrigger className={cn('w-full', fields[column] !== undefined && fields[column] !== team.values[column] && 'border-primary')}>
                    <SelectValue placeholder={t('takers.auto')} />
                  </SelectTrigger>
                  <SelectContent>
                    {takerChoices.map((r) => (
                      <SelectItem key={r.player} value={String(r.player)}>
                        {info[r.player]?.name ?? `#${r.player}`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )
          })}
        </div>
      </Section>
    </div>
  )
}
