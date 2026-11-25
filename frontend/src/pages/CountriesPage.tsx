import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/api/client'
import { DateCells, DateHeads } from '@/components/common/dates'
import { CreateDialog } from '@/components/common/create'
import { OriginalBadge } from '@/components/common/detail'
import { GameHiddenBadge, HiddenByProjectBadge, HideButton, OutOfPatchBadge, useHide } from '@/components/common/HideButton'
import { CountryFlag } from '@/components/common/pictures'
import { BulkActions, RowCheckbox, SelectAllCheckbox, SelectAllDialog, useListSelection } from '@/components/common/selection'
import { hasMessage, useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { FilterBar, FilterSelect, LIST_PAGE, Pager, ScrollTable, SearchInput, SortHead, useListState } from '@/lib/list'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useList, useOptions } from '@/state/queries'

const FILTERS = ['q', 'confederation', 'origin', 'status'] as const

/** Name of a confederation code of the database (same as the extractor's countries list). */
export function useConfederationName() {
  const { t } = useI18n()
  return (code: number | null) => {
    if (code === null) return '—'
    const key = `confederation.${code}`
    return hasMessage(key) ? t(key) : String(code)
  }
}

export function CountriesPage() {
  const { t } = useI18n()
  const confederation = useConfederationName()
  const options = useOptions().data
  const navigate = useNavigate()
  const qc = useQueryClient()
  const from = useFrom({ key: 'nav.countries' })
  const list = useListState(FILTERS)
  const { data, isFetching } = useList('countries', list.request, api.countries)
  // the project's items (created, or edited ones of the game) can be picked and deleted in bulk, like in the Street Studio
  const own = (r: { is_new: boolean; edited?: boolean }) => r.is_new || !!r.edited
  const selection = useListSelection((data?.items ?? []).filter(own).map((r) => r.id), data?.own_ids ?? [])
  const hide = useHide('country', ['countries', 'country', 'leagues'])
  const [creating, setCreating] = useState(false)
  const create = useMutation({
    mutationFn: (name: string) => api.createCountry({ full: { '*': name } }),
    onSuccess: (country) => {
      for (const k of ['countries', 'options', 'status']) void qc.invalidateQueries({ queryKey: [k] })
      setCreating(false)
      toast.success(t('country.created'))
      navigate(`/countries/${country.id}`, from)
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const sortState = { sort: list.sort, dir: list.dir, update: list.update, current: data?.sort ?? '', currentDir: data?.dir ?? '' }
  return (
    <div className={LIST_PAGE}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{t('countries.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('countries.subtitle')}</p>
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus /> {t('countries.new')}
        </Button>
      </div>
      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={list.values.q} onChange={(v) => list.update({ q: v })} placeholder={t('countries.search')} />
        <FilterSelect
          value={list.values.confederation}
          onChange={(v) => list.update({ confederation: v })}
          allLabel={t('filter.allConfederations')}
          options={(options?.confederations ?? []).map((c) => ({ value: String(c), label: confederation(c) }))}
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
        <BulkActions kind="country" selection={selection} invalidate={['countries', 'country', 'leagues']} />
      </FilterBar>
      <ScrollTable loading={!data}>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <SelectAllCheckbox selection={selection} />
            </TableHead>
            <TableHead className="w-14" />
            <SortHead field="name" label={t('col.name')} state={sortState} />
            <SortHead field="confederation" label={t('col.confederation')} state={sortState} className="text-right" />
            <SortHead field="league_count" label={t('col.leagues')} state={sortState} className="text-center" />
            <SortHead field="id" label={t('col.id')} state={sortState} className="text-center" />
            <DateHeads sort={sortState} />
            <TableHead className="w-28" />
            <TableHead className="w-16" />
          </TableRow>
        </TableHeader>
        <TableBody className={isFetching ? 'opacity-70' : undefined}>
          {data?.items.map((c) => (
            <TableRow key={c.id} className={cn(!c.is_new && 'text-muted-foreground')}>
              <TableCell>{own(c) && <RowCheckbox selection={selection} value={c.id} />}</TableCell>
              <TableCell>
                <CountryFlag id={c.flag_id} size={64} version={c.own_flag} available={c.has_flag || c.is_new || c.flag_id !== c.id || !!c.own_flag} className="h-6 w-9" />
              </TableCell>
              <TableCell data-grow>
                <Link to={`/countries/${c.id}`} state={from.state} className="font-medium text-foreground underline-offset-4 hover:underline">{c.name}</Link> {!c.is_new && <OriginalBadge edited={c.edited} />}
                {c.game_hidden && <GameHiddenBadge country />}
                {c.hidden && (c.is_new ? <OutOfPatchBadge /> : <HiddenByProjectBadge label={t('countries.hiddenByProject')} />)}
              </TableCell>
              <TableCell className="text-right">{confederation(c.confederation)}</TableCell>
              <TableCell className="text-center tabular-nums">{c.league_count}</TableCell>
              <TableCell className="text-center text-muted-foreground tabular-nums">{c.id}</TableCell>
              <DateCells entry={c} />
              <TableCell>
                {!c.game_hidden && (
                  <HideButton
                    hidden={c.hidden}
                    disabled={hide.isPending && hide.variables?.id === c.id}
                    onToggle={() => hide.mutate({ id: c.id, hidden: !c.hidden })}
                    hideHint={t(c.is_new ? 'countries.hideHint' : 'countries.originalHideHint')}
                    showHint={t(c.is_new ? 'countries.showHint' : 'countries.originalShowHint')}
                  />
                )}
              </TableCell>
              <TableCell />{/* warnings column: countries have none yet */}
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
        <Pager page={data.page} pages={data.pages} total={data.total} size={data.size} onPage={(page, size) => list.update({ page, ...(size ? { size } : {}) }, false)} />
      )}
      <CreateDialog
        open={creating}
        onOpenChange={setCreating}
        title={t('countries.new')}
        description={t('countries.newHint')}
        label={t('countryName.full')}
        maxLength={40}
        pending={create.isPending}
        onCreate={(name) => create.mutate(name)}
      />
      <SelectAllDialog selection={selection} />
    </div>
  )
}
