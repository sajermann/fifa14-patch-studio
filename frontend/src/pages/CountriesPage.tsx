import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/api/client'
import { CreateDialog } from '@/components/common/create'
import { OriginalBadge } from '@/components/common/detail'
import { CountryFlag } from '@/components/common/pictures'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { FilterBar, LIST_PAGE, Pager, ScrollTable, SearchInput, SortHead, useListState } from '@/lib/list'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useList } from '@/state/queries'

const FILTERS = ['q'] as const

export function CountriesPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const from = useFrom(t('nav.countries'))
  const list = useListState(FILTERS)
  const { data, isFetching } = useList('countries', list.request, api.countries)
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
      </FilterBar>
      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead className="w-14" />
            <SortHead field="name" label={t('col.name')} state={sortState} />
            <SortHead field="league_count" label={t('col.leagues')} state={sortState} />
            <SortHead field="id" label={t('col.id')} state={sortState} />
          </TableRow>
        </TableHeader>
        <TableBody className={isFetching ? 'opacity-70' : undefined}>
          {data?.items.map((c) => (
            <TableRow key={c.id} className={cn('cursor-pointer', !c.is_new && 'text-muted-foreground')} onClick={() => navigate(`/countries/${c.id}`, from)}>
              <TableCell>
                <CountryFlag id={c.flag_id} size={64} version={c.own_flag} available={c.has_flag || c.is_new || c.flag_id !== c.id || !!c.own_flag} className="h-6 w-9" />
              </TableCell>
              <TableCell data-grow>
                <span className="font-medium text-foreground">{c.name}</span> <OriginalBadge edited={c.edited} isNew={c.is_new} />
              </TableCell>
              <TableCell className="tabular-nums">{c.league_count}</TableCell>
              <TableCell className="text-muted-foreground tabular-nums">{c.id}</TableCell>
            </TableRow>
          ))}
          {data && data.items.length === 0 && (
            <TableRow>
              <TableCell colSpan={4} className="py-10 text-center text-muted-foreground">
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
    </div>
  )
}
