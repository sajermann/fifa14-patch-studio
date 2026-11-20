import { Plus, UserMinus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { PlayerTeamBody } from '@/api/client'
import type { PlayerDetail } from '@/api/types'
import { Badge, Section } from '@/components/common/detail'
import { EntityIssues } from '@/components/common/form'
import { HiddenByProjectBadge, OutOfPatchBadge } from '@/components/common/HideButton'
import { Crest } from '@/components/common/pictures'
import { TeamPickerDialog } from '@/components/team/NewTeamDialog'
import { BENCH, RESERVE } from '@/components/team/pending'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { cn } from '@/lib/utils'
import { useOptions } from '@/state/queries'

/** The teams of a player as the screen keeps them (saved with Save). */
export const savedTeams = (player: PlayerDetail): PlayerTeamBody[] =>
  player.teams.map((tm) => ({ team: tm.id, jersey: tm.jersey, hidden: tm.hidden, slot: tm.position ?? undefined }))

export const sameTeams = (a: PlayerTeamBody[], b: PlayerTeamBody[]) =>
  a.length === b.length && a.every((r, i) => r.team === b[i].team && r.jersey === b[i].jersey && r.hidden === b[i].hidden && r.slot === b[i].slot)

/** The player's teams (a player can be in several), laid out like the squad table: the team (round crest and name) on
 * the left; number, position in the lineup (a starter's place, the bench or out of the squad), in the patch or not
 * and remove on the right. Joining and leaving teams too. */
export function PlayerTeams({ player, rows, setRows }: { player: PlayerDetail; rows: PlayerTeamBody[]; setRows: (rows: PlayerTeamBody[]) => void }) {
  const { t } = useI18n()
  const from = useFrom(player.name)
  const positions = useOptions().data?.positions ?? []
  const [adding, setAdding] = useState(false)
  const [names, setNames] = useState<Record<number, string>>({})
  const known = Object.fromEntries(player.teams.map((tm) => [tm.id, tm]))
  const update = (team: number, patch: Partial<PlayerTeamBody>) => setRows(rows.map((r) => (r.team === team ? { ...r, ...patch } : r)))
  const posName = (code: number) => positions.find((p) => p.id === code)?.name ?? String(code)
  return (
    <Section
      title={t('playerTeams.title')}
      description={t('playerTeams.description')}
      action={
        <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
          <Plus /> {t('playerTeams.add')}
        </Button>
      }
    >
      {rows.length === 0 ? (
        <p className="py-4 text-sm text-muted-foreground">{t('playerTeams.none')}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('col.team')}</TableHead>
              <TableHead className="w-28 text-center">{t('col.number')}</TableHead>
              <TableHead className="w-52 text-center">{t('col.position')}</TableHead>
              <TableHead className="w-28 text-center">{t('roster.inPatch')}</TableHead>
              <TableHead className="w-32" />
              <TableHead className="w-16" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => {
              const tm = known[r.team]
              const slots = tm?.slots ?? []
              return (
                <TableRow key={r.team}>
                  <TableCell>
                    <span className="flex items-center gap-2">
                      <Crest id={r.team} size={64} className="size-8 shrink-0 rounded-full bg-muted object-cover" />
                      <Link to={`/teams/${r.team}`} state={from.state} className={cn('font-medium underline-offset-4 hover:underline', r.hidden && 'text-muted-foreground')}>
                        {tm?.name ?? names[r.team] ?? `#${r.team}`}
                      </Link>
                      {tm?.national_of != null && <Badge>{t('playerTeams.national')}</Badge>}
                      {tm?.team_hidden && (tm.is_new ? <OutOfPatchBadge /> : <HiddenByProjectBadge label={t('teams.hiddenByProject')} />)}
                      {r.hidden && <OutOfPatchBadge label={t('playerTeams.hidden')} />}
                    </span>
                    {tm && tm.squad_size > player.max_squad && (
                      <p className="text-xs text-amber-600 dark:text-amber-400">{t('playerTeams.full', { count: tm.squad_size, max: player.max_squad })}</p>
                    )}
                  </TableCell>
                  <TableCell>
                    <Input
                      type="number"
                      min={1}
                      max={99}
                      className="h-8 w-20 text-center tabular-nums"
                      value={r.jersey ?? ''}
                      onChange={(e) => update(r.team, { jersey: e.target.value === '' ? null : Math.min(99, Math.max(1, Number(e.target.value))) })}
                    />
                  </TableCell>
                  <TableCell className="text-center">
                    <Select value={r.slot === undefined ? '' : String(r.slot)} onValueChange={(v) => update(r.team, { slot: Number(v) })}>
                      <SelectTrigger size="sm" className="w-44">
                        <SelectValue placeholder={t('playerTeams.autoSlot')} />
                      </SelectTrigger>
                      <SelectContent>
                        {slots.map((code) => (
                          <SelectItem key={code} value={String(code)}>
                            {posName(code)}
                          </SelectItem>
                        ))}
                        {r.slot !== undefined && r.slot < BENCH && !slots.includes(r.slot) && <SelectItem value={String(r.slot)}>{posName(r.slot)}</SelectItem>}
                        <SelectItem value={String(BENCH)}>{t('squad.benchRole')}</SelectItem>
                        <SelectItem value={String(RESERVE)}>{t('squad.reserveRole')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell className="text-center">
                    <Switch
                      checked={!r.hidden}
                      title={r.hidden ? t('playerTeams.showHint') : t('playerTeams.hideHint')}
                      onCheckedChange={(on) => update(r.team, { hidden: !on })}
                    />
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" title={t('playerTeams.remove')} onClick={() => setRows(rows.filter((x) => x.team !== r.team))}>
                      <UserMinus /> {t('common.remove')}
                    </Button>
                  </TableCell>
                  <TableCell>
                    <EntityIssues kind="team" id={r.team} />
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
      <TeamPickerDialog
        open={adding}
        onOpenChange={setAdding}
        title={t('playerTeams.addTitle')}
        description={t('playerTeams.addDescription')}
        exclude={rows.map((r) => r.team)}
        onPick={(team) => {
          setNames((n) => ({ ...n, [team.id]: team.name }))
          setRows([...rows, { team: team.id, jersey: null, hidden: false }])
        }}
      />
    </Section>
  )
}
