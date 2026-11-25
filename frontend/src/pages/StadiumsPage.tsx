import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Landmark, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useFrom } from '@/lib/back'
import { toast } from '@/lib/notify'
import { Button } from '@/components/ui/button'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/api/client'
import { DateCells, DateHeads } from '@/components/common/dates'
import { Badge, OriginalBadge } from '@/components/common/detail'
import { StadiumImage } from '@/components/common/pictures'
import { BulkActions, RowCheckbox, SelectAllCheckbox, SelectAllDialog, useListSelection } from '@/components/common/selection'
import { NewStadiumDialog, type NewStadium } from '@/components/stadium/NewStadiumDialog'
import { useI18n } from '@/i18n'
import { FilterBar, FilterSelect, LIST_PAGE, Pager, ScrollTable, SearchInput, SortHead, useListState } from '@/lib/list'
import { useList, useOptions } from '@/state/queries'

const FILTERS = ['q', 'country', 'home', 'origin'] as const

/** The stadiums (the user's and the game's): the same list as the leagues (filters, checkboxes, dates, New button),
 * with the extractor's columns. */
export function StadiumsPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const from = useFrom({ key: 'nav.stadiums' })
  const list = useListState(FILTERS)
  const { data, isFetching } = useList('stadiums', list.request, api.stadiums)
  const options = useOptions().data
  // the project's ones can be picked: a created one is deleted, an edited one goes back to the game's
  const selection = useListSelection((data?.items ?? []).filter((r) => r.edited || r.is_new).map((r) => r.id), data?.own_ids ?? [])
  const [creating, setCreating] = useState(false)
  const create = useMutation({
    mutationFn: (s: NewStadium) => api.createStadium({ names: { full: { '*': s.name } }, folder: s.folder, template: s.template }),
    onSuccess: (stadium) => {
      for (const k of ['stadiums', 'options', 'status']) void qc.invalidateQueries({ queryKey: [k] })
      setCreating(false)
      toast.success(t('stadium.created'))
      navigate(`/stadiums/${stadium.id}`, from)
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
          <h1 className="text-2xl font-semibold">{t('stadiums.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('stadiums.subtitle')}</p>
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus /> {t('stadium.new')}
        </Button>
      </div>
      <NewStadiumDialog open={creating} onOpenChange={setCreating} pending={create.isPending} onCreate={(s) => create.mutate(s)} />
      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={list.values.q} onChange={(v) => list.update({ q: v })} placeholder={t('stadiums.search')} />
        <FilterSelect
          value={list.values.country}
          onChange={(v) => list.update({ country: v })}
          allLabel={t('filter.allCountries')}
          options={(options?.nations ?? []).map((n) => ({ value: String(n.id), label: n.name ?? `#${n.id}` }))}
        />
        <FilterSelect
          value={list.values.home}
          onChange={(v) => list.update({ home: v })}
          allLabel={t('filter.homeAny')}
          options={[
            { value: 'yes', label: t('filter.homeYes') },
            { value: 'no', label: t('filter.homeNo') },
          ]}
        />
        <FilterSelect
          value={list.values.origin}
          onChange={(v) => list.update({ origin: v })}
          allLabel={t('list.originAll')}
          options={[
            { value: 'project', label: t('stadiums.originEdited') },
            { value: 'original', label: t('list.originOriginal') },
          ]}
        />
        <BulkActions kind="stadium" selection={selection} invalidate={['stadiums', 'stadium', 'teams', 'team', 'options']} />
      </FilterBar>
      <ScrollTable loading={!data}>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <SelectAllCheckbox selection={selection} />
            </TableHead>
            <TableHead className="w-28" />
            <SortHead field="name" label={t('col.name')} state={sortState} />
            <SortHead field="country" label={t('col.country')} state={sortState} />
            <TableHead>{t('col.homeTeam')}</TableHead>
            <SortHead field="capacity" label={t('col.capacity')} state={sortState} className="text-right" />
            <SortHead field="team_count" label={t('col.teams')} state={sortState} className="text-center" />
            <SortHead field="id" label={t('col.id')} state={sortState} className="text-center" />
            <DateHeads sort={sortState} />
          </TableRow>
        </TableHeader>
        <TableBody className={isFetching ? 'opacity-70' : undefined}>
          {data?.items.map((s) => (
            <TableRow key={s.id} className={s.edited || s.is_new ? undefined : 'text-muted-foreground'}>
              <TableCell>{(s.edited || s.is_new) && <RowCheckbox selection={selection} value={s.id} />}</TableCell>
              <TableCell>
                {s.picture !== null ? (
                  <StadiumImage id={s.id} variant={s.picture} size={128} version={s.updated_at} className="h-7 w-24 rounded object-cover" />
                ) : (
                  <span className="inline-flex h-7 w-24 items-center justify-center rounded bg-muted text-muted-foreground/50">
                    <Landmark className="size-4" />
                  </span>
                )}
              </TableCell>
              <TableCell data-grow>
                <div className="flex flex-wrap items-center gap-2">
                  <Link to={`/stadiums/${s.id}`} state={from.state} className="font-medium text-foreground underline-offset-4 hover:underline">
                    {s.name}
                  </Link>
                  {!s.is_new && <OriginalBadge edited={s.edited} />}
                  {!s.has_3d && <Badge>{t('stadiums.no3d')}</Badge>}
                </div>
                {s.language_name && s.language_name !== s.name && <div className="text-xs text-muted-foreground">{s.language_name}</div>}
              </TableCell>
              <TableCell>{s.country ?? '—'}</TableCell>
              <TableCell>{s.home_team ?? '—'}</TableCell>
              <TableCell className="text-right tabular-nums">{s.capacity?.toLocaleString() ?? '—'}</TableCell>
              <TableCell className="text-center tabular-nums">{s.team_count}</TableCell>
              <TableCell className="text-center text-muted-foreground tabular-nums">{s.id}</TableCell>
              <DateCells entry={s} />
            </TableRow>
          ))}
          {data && data.items.length === 0 && (
            <TableRow>
              <TableCell colSpan={10} className="py-10 text-center text-muted-foreground">
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
