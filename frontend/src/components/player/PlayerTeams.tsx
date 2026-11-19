import { Plus, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { PlayerTeamBody } from '@/api/client'
import type { PlayerDetail } from '@/api/types'
import { Badge, Section } from '@/components/common/detail'
import { HideButton } from '@/components/common/HideButton'
import { Crest } from '@/components/common/pictures'
import { TeamPickerDialog } from '@/components/team/NewTeamDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { cn } from '@/lib/utils'

/** The teams of a player as the screen keeps them (saved with Save). */
export const savedTeams = (player: PlayerDetail): PlayerTeamBody[] => player.teams.map((tm) => ({ team: tm.id, jersey: tm.jersey, hidden: tm.hidden }))

export const sameTeams = (a: PlayerTeamBody[], b: PlayerTeamBody[]) =>
  a.length === b.length && a.every((r, i) => r.team === b[i].team && r.jersey === b[i].jersey && r.hidden === b[i].hidden)

/** The player's teams (a player can be in several): number in each one, hidden in one team only (out of the patch
 * there, kept in its squad), joining and leaving teams. The position in the lineup is set on the team's screen. */
export function PlayerTeams({ player, rows, setRows }: { player: PlayerDetail; rows: PlayerTeamBody[]; setRows: (rows: PlayerTeamBody[]) => void }) {
  const { t } = useI18n()
  const from = useFrom(player.name)
  const [adding, setAdding] = useState(false)
  const [names, setNames] = useState<Record<number, string>>({})
  const known = Object.fromEntries(player.teams.map((tm) => [tm.id, tm]))
  const update = (team: number, patch: Partial<PlayerTeamBody>) => setRows(rows.map((r) => (r.team === team ? { ...r, ...patch } : r)))
  return (
    <Section
      title={t('playerTeams.title')}
      description={t('playerTeams.description')}
      action={
        <Button size="sm" onClick={() => setAdding(true)}>
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
              <TableHead className="w-10" />
              <TableHead>{t('col.team')}</TableHead>
              <TableHead className="w-24">{t('col.number')}</TableHead>
              <TableHead>{t('col.position')}</TableHead>
              <TableHead className="w-28" />
              <TableHead className="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => {
              const tm = known[r.team]
              return (
                <TableRow key={r.team} className={cn(r.hidden && 'text-muted-foreground')}>
                  <TableCell>
                    <Crest id={r.team} size={64} className="size-7" />
                  </TableCell>
                  <TableCell>
                    <Link to={`/teams/${r.team}`} state={from.state} className="font-medium hover:underline">
                      {tm?.name ?? names[r.team] ?? `#${r.team}`}
                    </Link>
                    {tm?.national_of != null && <Badge className="ml-2">{t('playerTeams.national')}</Badge>}
                    {r.hidden && <Badge tone="warn" className="ml-2">{t('playerTeams.hidden')}</Badge>}
                    {tm && tm.squad_size > player.max_squad && (
                      <p className="text-xs text-amber-600 dark:text-amber-400">{t('playerTeams.full', { count: tm.squad_size, max: player.max_squad })}</p>
                    )}
                  </TableCell>
                  <TableCell>
                    <Input
                      type="number"
                      min={1}
                      max={99}
                      className="h-8 w-16 tabular-nums"
                      value={r.jersey ?? ''}
                      onChange={(e) => update(r.team, { jersey: e.target.value === '' ? null : Math.min(99, Math.max(1, Number(e.target.value))) })}
                    />
                  </TableCell>
                  <TableCell>{tm?.position_name ?? '—'}</TableCell>
                  <TableCell>
                    <HideButton hidden={r.hidden} onToggle={() => update(r.team, { hidden: !r.hidden })} hideHint={t('playerTeams.hideHint')} showHint={t('playerTeams.showHint')} />
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon-sm" title={t('playerTeams.remove')} aria-label={t('playerTeams.remove')} onClick={() => setRows(rows.filter((x) => x.team !== r.team))}>
                      <X />
                    </Button>
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
