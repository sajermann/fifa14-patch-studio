import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { CreateDialog } from '@/components/common/create'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useFrom } from '@/lib/back'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/api/client'
import { DateCells, DateHeads } from '@/components/common/dates'
import { OriginalBadge } from '@/components/common/detail'
import { EntityIssues } from '@/components/common/form'
import { GameHiddenBadge, HiddenByProjectBadge, HideButton, OutOfPatchBadge, useHide } from '@/components/common/HideButton'
import { LeagueImage } from '@/components/common/pictures'
import { BulkActions, RowCheckbox, SelectAllCheckbox, SelectAllDialog, useListSelection } from '@/components/common/selection'
import { useI18n } from '@/i18n'
import { FilterBar, FilterSelect, LIST_PAGE, Pager, ScrollTable, SearchInput, SortHead, useListState } from '@/lib/list'
import { useList, useOptions } from '@/state/queries'

const FILTERS = ['q', 'country', 'level', 'origin', 'status'] as const

export function LeaguesPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const from = useFrom({ key: 'nav.leagues' })
  const list = useListState(FILTERS)
  const { data, isFetching } = useList('leagues', list.request, api.leagues)
  const options = useOptions().data
  const withLeagues = new Set(options?.league_countries ?? [])
  // the project's items (created, or edited ones of the game) can be picked and deleted in bulk, like in the Street Studio
  const own = (r: { is_new: boolean; edited?: boolean }) => r.is_new || !!r.edited
  const selection = useListSelection((data?.items ?? []).filter(own).map((r) => r.id), data?.own_ids ?? [])
  const hide = useHide('league', ['leagues', 'league', 'country'])
  const qc = useQueryClient()
  const [creating, setCreating] = useState(false)
  const create = useMutation({
    mutationFn: (name: string) => api.createLeague({ full: { '*': name } }, {}),
    onSuccess: (league) => {
      for (const k of ['leagues', 'options', 'status']) void qc.invalidateQueries({ queryKey: [k] })
      setCreating(false)
      toast.success(t('league.created'))
      navigate(`/leagues/${league.id}`, from)
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
          <h1 className="text-2xl font-semibold">{t('leagues.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('leagues.subtitle')}</p>
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus /> {t('league.new')}
        </Button>
      </div>
      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={list.values.q} onChange={(v) => list.update({ q: v })} placeholder={t('leagues.search')} />
        <FilterSelect
          value={list.values.country}
          onChange={(v) => list.update({ country: v })}
          allLabel={t('filter.allCountries')}
          options={(options?.nations ?? []).filter((n) => withLeagues.has(n.id)).map((n) => ({ value: String(n.id), label: n.name ?? `#${n.id}` }))}
        />
        <FilterSelect
          value={list.values.level}
          onChange={(v) => list.update({ level: v })}
          allLabel={t('filter.allLevels')}
          options={(options?.levels ?? []).map((l) => ({ value: String(l), label: t('filter.level', { level: l }) }))}
        />
        <FilterSelect
          value={list.values.origin}
          onChange={(v) => list.update({ origin: v })}
          allLabel={t('list.originAll')}
          options={[
            { value: 'project', label: t('list.originProject') },
            { value: 'original', label: t('list.originOriginal') },
          ]}
        />
        <FilterSelect
          value={list.values.status}
          onChange={(v) => list.update({ status: v })}
          allLabel={t('list.statusAll')}
          options={[
            { value: 'visible', label: t('list.statusInGame') },
            { value: 'hidden', label: t('list.statusHidden') },
          ]}
        />
        <BulkActions kind="league" selection={selection} invalidate={['leagues', 'league', 'country', 'countries', 'teams']} />
      </FilterBar>
      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <SelectAllCheckbox selection={selection} />
            </TableHead>
            <TableHead className="w-12" />
            <SortHead field="name" label={t('col.name')} state={sortState} />
            <SortHead field="country" label={t('col.country')} state={sortState} className="text-right" />
            <SortHead field="level" label={t('col.level')} state={sortState} className="text-center" />
            <SortHead field="team_count" label={t('col.teams')} state={sortState} className="text-center" />
            <SortHead field="id" label={t('col.id')} state={sortState} className="text-center" />
            <DateHeads />
            <TableHead className="w-28" />
            <TableHead className="w-16" />
          </TableRow>
        </TableHeader>
        <TableBody className={isFetching ? 'opacity-70' : undefined}>
          {data?.items.map((l) => (
            <TableRow key={l.id} className={l.is_new ? undefined : 'text-muted-foreground'}>
              <TableCell>{own(l) && <RowCheckbox selection={selection} value={l.id} />}</TableCell>
              <TableCell>
                <LeagueImage id={l.id} size={64} available={!!l.has_logo} className="size-8" />
              </TableCell>
              <TableCell data-grow>
                <Link to={`/leagues/${l.id}`} state={from.state} className={cn('font-medium underline-offset-4 hover:underline', l.hidden ? 'text-muted-foreground' : 'text-foreground')}>{l.name}</Link> {!l.is_new && <OriginalBadge edited={l.edited} />}
                {l.game_hidden && <GameHiddenBadge />}
                {l.hidden && (l.is_new ? <OutOfPatchBadge /> : <HiddenByProjectBadge label={t('leagues.hiddenByProject')} />)}
                {!l.hidden && l.hidden_by_countries && <HiddenByProjectBadge label={t('leagues.countryHidden')} />}
              </TableCell>
              <TableCell className="text-right">
                {l.country ?? '—'}
                {l.extra_countries.length > 0 && <span className="text-muted-foreground"> +{l.extra_countries.length}</span>}
              </TableCell>
              <TableCell className="text-center tabular-nums">{l.level ?? '—'}</TableCell>
              <TableCell className="text-center tabular-nums">{l.team_count}</TableCell>
              <TableCell className="text-center text-muted-foreground tabular-nums">{l.id}</TableCell>
              <DateCells entry={l} />
              <TableCell>
                {!l.game_hidden && (
                  <HideButton
                    hidden={l.hidden}
                    disabled={hide.isPending && hide.variables?.id === l.id}
                    onToggle={() => hide.mutate({ id: l.id, hidden: !l.hidden })}
                    hideHint={t(l.is_new ? 'leagues.hideHint' : 'leagues.originalHideHint')}
                    showHint={t(l.is_new ? 'leagues.showHint' : 'leagues.originalShowHint')}
                  />
                )}
              </TableCell>
              <TableCell>
                <EntityIssues kind="league" id={l.id} />
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
      <CreateDialog
        open={creating}
        onOpenChange={setCreating}
        title={t('league.new')}
        description={t('league.newHint')}
        label={t('leagueName.full')}
        maxLength={60}
        pending={create.isPending}
        onCreate={(name) => create.mutate(name)}
      />
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
