import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { NewTeamDialog, type NewTeam } from '@/components/team/NewTeamDialog'
import { useFrom } from '@/lib/back'
import { toast } from '@/lib/notify'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/api/client'
import { OriginalBadge, OverallBadge } from '@/components/common/detail'
import { EntityIssues } from '@/components/common/form'
import { HiddenByProjectBadge, HideButton, OutOfPatchBadge, useHide } from '@/components/common/HideButton'
import { cn } from '@/lib/utils'
import { ColorDot, Crest } from '@/components/common/pictures'
import { BulkActions, RowCheckbox, SelectAllCheckbox, SelectAllDialog, useListSelection } from '@/components/common/selection'
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
  // the project's items (created, or edited ones of the game) can be picked and deleted in bulk, like in the Street Studio
  const own = (r: { is_new: boolean; edited?: boolean }) => r.is_new || !!r.edited
  const selection = useListSelection((data?.items ?? []).filter(own).map((r) => r.id), data?.own_ids ?? [])
  const options = useOptions().data
  const qc = useQueryClient()
  const hide = useHide('team', ['teams', 'team', 'leagues', 'league', 'players'])
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
        <BulkActions kind="team" selection={selection} invalidate={['teams', 'team', 'leagues', 'league', 'players']} />
      </FilterBar>
      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <SelectAllCheckbox selection={selection} />
            </TableHead>
            <TableHead className="w-12" />
            <SortHead field="name" label={t('col.name')} state={sortState} />
            <SortHead field="league" label={t('col.league')} state={sortState} className="text-right" />
            <SortHead field="overall" label={t('col.overall')} state={sortState} className="text-center" />
            <SortHead field="player_count" label={t('col.players')} state={sortState} className="text-center" />
            <SortHead field="kit_count" label={t('col.kits')} state={sortState} className="text-center" />
            <TableHead className="text-center">{t('col.colors')}</TableHead>
            <SortHead field="id" label={t('col.id')} state={sortState} className="text-center" />
            <TableHead className="w-28" />
            <TableHead className="w-16" />
          </TableRow>
        </TableHeader>
        <TableBody className={isFetching ? 'opacity-70' : undefined}>
          {data?.items.map((tm) => (
            <TableRow key={tm.id} className={cn(!tm.edited && !tm.is_new && 'text-muted-foreground')}>
              <TableCell>{own(tm) && <RowCheckbox selection={selection} value={tm.id} />}</TableCell>
              <TableCell>
                <Crest id={tm.id} size={64} available={tm.has_crest} version={tm.own_crest} className="size-8" />
              </TableCell>
              <TableCell data-grow>
                <div className="flex items-center gap-2">
                  <Link to={`/teams/${tm.id}`} state={from.state} className="font-medium text-foreground underline-offset-4 hover:underline">{tm.name}</Link>
                  {tm.abbr3 && <span className="text-xs text-muted-foreground">{tm.abbr3}</span>}
                  {!tm.is_new && <OriginalBadge edited={tm.edited} />}
                  {tm.hidden && (tm.is_new ? <OutOfPatchBadge /> : <HiddenByProjectBadge label={t('teams.hiddenByProject')} />)}
                </div>
                {tm.abbr15 && tm.abbr15 !== tm.name && <div className="text-xs text-muted-foreground">{tm.abbr15}</div>}
              </TableCell>
              <TableCell className="text-right">{tm.national_of !== null ? t('teams.nationalTeam') : (tm.league ?? '—')}</TableCell>
              <TableCell className="text-center">
                <OverallBadge value={tm.overall} />
              </TableCell>
              <TableCell className="text-center tabular-nums">{tm.player_count}</TableCell>
              <TableCell className="text-center tabular-nums">{tm.kit_count}</TableCell>
              <TableCell>
                <span className="flex items-center justify-center gap-1">
                  {tm.colors.map((c, i) => (
                    <ColorDot key={i} rgb={c} />
                  ))}
                </span>
              </TableCell>
              <TableCell className="text-center text-muted-foreground tabular-nums">{tm.id}</TableCell>
              <TableCell>
                <HideButton
                  hidden={tm.hidden}
                  disabled={hide.isPending && hide.variables?.id === tm.id}
                  onToggle={() => hide.mutate({ id: tm.id, hidden: !tm.hidden })}
                  hideHint={t(tm.is_new ? 'teams.hideHint' : 'teams.originalHideHint')}
                  showHint={t(tm.is_new ? 'teams.showHint' : 'teams.originalShowHint')}
                />
              </TableCell>
              <TableCell>
                <EntityIssues kind="team" id={tm.id} />
              </TableCell>
            </TableRow>
          ))}
          {data && data.items.length === 0 && (
            <TableRow>
              <TableCell colSpan={11} className="py-10 text-center text-muted-foreground">
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
      <SelectAllDialog selection={selection} />
    </div>
  )
}
