import { useQuery } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import type { PlayerRow, SquadRow, TeamDetail } from '@/api/types'
import { OverallBadge, Section } from '@/components/common/detail'
import { PickerDialog, type PickerItem } from '@/components/common/PickerDialog'
import { Photo } from '@/components/common/pictures'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useOptions, useToken } from '@/state/queries'
import { BENCH, RESERVE } from './pending'

interface PlayerInfo {
  name: string
  overall: number | null
  position_name: string | null
  has_photo: boolean
}

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
    icon: <Photo id={p.id} size={64} available={p.has_photo} className="size-8" />,
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

/** The squad: formation (one of the game's 33), one starter per position of it, the bench (28) and the players out
 * of the squad (29); jersey numbers; players added or taken out. More than `max_squad` stay out of the patch. */
export function TeamSquad({
  team,
  rows,
  setRows,
  formation,
  setFormation,
}: {
  team: TeamDetail
  rows: SquadRow[]
  setRows: (rows: SquadRow[]) => void
  formation: number | null
  setFormation: (id: number) => void
}) {
  const { t } = useI18n()
  const positions = useOptions().data?.positions ?? []
  const [adding, setAdding] = useState(false)
  const [added, setAdded] = useState<Record<number, PlayerInfo>>({})
  const info = useMemo(() => {
    const out: Record<number, PlayerInfo> = { ...added }
    for (const p of team.roster) out[p.id] = { name: p.name, overall: p.overall, position_name: p.position_name, has_photo: p.has_photo }
    return out
  }, [team.roster, added])
  const current = team.formations.find((f) => f.id === formation) ?? team.formations[0]
  const slots = current?.positions ?? []
  const posName = (code: number) => positions.find((p) => p.id === code)?.name ?? String(code)
  const starters = rows.filter((r) => r.slot < BENCH)
  const inPatch = Math.min(rows.length, team.max_squad)
  const order = (r: SquadRow) => (r.slot < BENCH ? slots.indexOf(r.slot) : r.slot * 100)
  const shown = [...rows].sort((a, b) => order(a) - order(b))
  const numbers = rows.map((r) => r.jersey).filter((n) => n !== null)
  const repeated = new Set(numbers.filter((n, i) => numbers.indexOf(n) !== i))
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
  return (
    <Section
      title={t('squad.title')}
      description={t('squad.hint', { max: team.max_squad })}
      action={
        <Button size="sm" onClick={() => setAdding(true)}>
          <Plus /> {t('squad.add')}
        </Button>
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
        <span className={cn('tabular-nums', rows.length > team.max_squad && 'text-amber-600 dark:text-amber-400')}>
          {t('squad.inPatch', { count: inPatch, max: team.max_squad, total: rows.length })}
        </span>
      </div>
      {starters.length < 11 && rows.length >= 11 && <p className="mb-2 text-xs text-amber-600 dark:text-amber-400">{t('squad.fillHint')}</p>}
      {rows.length < 11 && <p className="mb-2 text-xs text-amber-600 dark:text-amber-400">{t('squad.tooFew')}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10" />
            <TableHead className="w-20">{t('col.number')}</TableHead>
            <TableHead>{t('col.name')}</TableHead>
            <TableHead className="w-44">{t('col.role')}</TableHead>
            <TableHead>{t('col.position')}</TableHead>
            <TableHead>{t('col.overall')}</TableHead>
            <TableHead className="w-12" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {shown.map((r) => {
            const p = info[r.player]
            const outOfPatch = rows.indexOf(r) >= team.max_squad
            return (
              <TableRow key={r.player} className={cn(r.slot === RESERVE && 'text-muted-foreground', outOfPatch && 'opacity-60')}>
                <TableCell>
                  <Photo id={r.player} size={64} available={p?.has_photo ?? true} className="size-8" />
                </TableCell>
                <TableCell>
                  <Input
                    type="number"
                    min={1}
                    max={99}
                    className={cn('h-8 w-16 tabular-nums', r.jersey !== null && repeated.has(r.jersey) && 'border-destructive')}
                    value={r.jersey ?? ''}
                    onChange={(e) => setRows(rows.map((x) => (x.player === r.player ? { ...x, jersey: e.target.value === '' ? null : Math.min(99, Math.max(1, Number(e.target.value))) } : x)))}
                  />
                </TableCell>
                <TableCell>
                  <Link to={`/players/${r.player}`} className="font-medium hover:underline">
                    {p?.name ?? `#${r.player}`}
                  </Link>
                </TableCell>
                <TableCell>
                  <Select value={String(r.slot)} onValueChange={(v) => setSlot(r.player, Number(v))}>
                    <SelectTrigger className="h-8 w-40">
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
                <TableCell>{p?.position_name ?? '—'}</TableCell>
                <TableCell>
                  <OverallBadge value={p?.overall ?? null} />
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="icon-sm" title={t('squad.remove')} aria-label={t('squad.remove')} onClick={() => setRows(rows.filter((x) => x.player !== r.player))}>
                    <X />
                  </Button>
                </TableCell>
              </TableRow>
            )
          })}
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                {t('squad.empty')}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <AddPlayerDialog
        open={adding}
        onOpenChange={setAdding}
        chosen={rows.map((r) => r.player)}
        onPick={(p) => {
          setAdded((a) => ({ ...a, [p.id]: { name: p.name, overall: p.overall, position_name: p.position_name, has_photo: p.has_photo } }))
          // a free position of the formation that suits him: his own, else the nearest one (a goalkeeper only in goal)
          const open = slots.filter((code) => !rows.some((r) => r.slot === code))
          const pos = p.position ?? 25
          const free = open.includes(pos)
            ? pos
            : pos === 0
              ? undefined
              : open.filter((code) => code !== 0).sort((a, b) => Math.abs(a - pos) - Math.abs(b - pos))[0]
          setRows([...rows, { player: p.id, jersey: freeNumber(), slot: free ?? (rows.filter((r) => r.slot === BENCH).length < 12 ? BENCH : RESERVE) }])
        }}
      />
    </Section>
  )
}
