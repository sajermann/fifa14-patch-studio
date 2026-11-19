import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { NewTeamDialog, type NewTeam } from '@/components/team/NewTeamDialog'
import { useFrom } from '@/lib/back'
import { toast } from '@/lib/notify'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/api/client'
import { OriginalBadge, OverallBadge } from '@/components/common/detail'
import { HiddenByProjectBadge, OutOfPatchBadge } from '@/components/common/HideButton'
import { cn } from '@/lib/utils'
import { ColorDot, Crest } from '@/components/common/pictures'
import { useI18n } from '@/i18n'
import { FilterBar, FilterSelect, LIST_PAGE, Pager, ScrollTable, SearchInput, SortHead, useListState } from '@/lib/list'
import { useList, useOptions } from '@/state/queries'

const FILTERS = ['q', 'league', 'edited'] as const

export function TeamsPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const from = useFrom({ key: 'nav.teams' })
  const list = useListState(FILTERS)
  const { data, isFetching } = useList('teams', list.request, api.teams)
  const options = useOptions().data
  const qc = useQueryClient()
  const [creating, setCreating] = useState(false)
  const create = useMutation({
    mutationFn: (n: NewTeam) =>
      api.createTeam({
        names: { full: { '*': n.name } },
        fields: n.copyOf === null ? { teamcolor1: n.colors[0], teamcolor2: n.colors[1] } : {},
        template: n.copyOf ?? undefined,
        copy: n.copyOf !== null,
        copy_squad: n.copySquad,
      }),
    onSuccess: (team) => {
      for (const k of ['teams', 'options', 'status']) void qc.invalidateQueries({ queryKey: [k] })
      setCreating(false)
      toast.success(t('team.created'))
      navigate(`/teams/${team.id}`, from)
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const sortState = {
    sort: list.sort,
    dir: list.dir,
    update: list.update,
    current: data?.sort ?? '',
    currentDir: data?.dir ?? '',
  }
  return (
    <div className={LIST_PAGE}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{t('teams.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('teams.subtitle')}</p>
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus /> {t('team.new')}
        </Button>
      </div>
      <NewTeamDialog open={creating} onOpenChange={setCreating} pending={create.isPending} onCreate={(n) => create.mutate(n)} />
      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={list.values.q} onChange={(v) => list.update({ q: v })} placeholder={t('teams.search')} />
        <FilterSelect
          value={list.values.league}
          onChange={(v) => list.update({ league: v })}
          allLabel={t('filter.allLeagues')}
          className="w-56"
          options={(options?.leagues ?? []).map((l) => ({
            value: String(l.id),
            label: l.name,
          }))}
        />
        <FilterSelect
          value={list.values.edited}
          onChange={(v) => list.update({ edited: v })}
          allLabel={t('filter.editedAny')}
          className="w-44"
          options={[
            { value: 'yes', label: t('filter.editedYes') },
            { value: 'no', label: t('filter.editedNo') },
          ]}
        />
      </FilterBar>
      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12" />
            <SortHead field="name" label={t('col.name')} state={sortState} />
            <SortHead field="league" label={t('col.league')} state={sortState} />
            <SortHead field="overall" label={t('col.overall')} state={sortState} />
            <SortHead field="player_count" label={t('col.players')} state={sortState} />
            <TableHead>{t('col.colors')}</TableHead>
            <SortHead field="id" label={t('col.id')} state={sortState} />
          </TableRow>
        </TableHeader>
        <TableBody className={isFetching ? 'opacity-70' : undefined}>
          {data?.items.map((tm) => (
            <TableRow key={tm.id} className={cn('cursor-pointer', !tm.edited && !tm.is_new && 'text-muted-foreground')} onClick={() => navigate(`/teams/${tm.id}`, from)}>
              <TableCell>
                <Crest id={tm.id} size={64} available={tm.has_crest} version={tm.own_crest} className="size-8" />
              </TableCell>
              <TableCell data-grow>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-foreground">{tm.name}</span>
                  {tm.abbr3 && <span className="text-xs text-muted-foreground">{tm.abbr3}</span>}
                  {!tm.is_new && <OriginalBadge edited={tm.edited} />}
                  {tm.hidden && (tm.is_new ? <OutOfPatchBadge /> : <HiddenByProjectBadge label={t('teams.hiddenByProject')} />)}
                </div>
                {tm.abbr15 && tm.abbr15 !== tm.name && <div className="text-xs text-muted-foreground">{tm.abbr15}</div>}
              </TableCell>
              <TableCell>{tm.national_of !== null ? t('teams.nationalTeam') : (tm.league ?? '—')}</TableCell>
              <TableCell>
                <OverallBadge value={tm.overall} />
              </TableCell>
              <TableCell className="tabular-nums">{tm.player_count}</TableCell>
              <TableCell>
                <ColorDot rgb={tm.color} />
              </TableCell>
              <TableCell className="text-muted-foreground tabular-nums">{tm.id}</TableCell>
            </TableRow>
          ))}
          {data && data.items.length === 0 && (
            <TableRow>
              <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                {t('list.empty')}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </ScrollTable>
      {data && (
        <Pager
          page={data.page}
          pages={data.pages}
          total={data.total}
          size={data.size}
          onPage={(page, size) => list.update({ page, ...(size ? { size } : {}) }, false)}
        />
      )}
    </div>
  )
}
