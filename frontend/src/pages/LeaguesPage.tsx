import { useNavigate } from 'react-router-dom'
import { useFrom } from '@/lib/back'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/api/client'
import { OriginalBadge } from '@/components/common/detail'
import { LeagueImage } from '@/components/common/pictures'
import { useI18n } from '@/i18n'
import { FilterBar, LIST_PAGE, Pager, ScrollTable, SearchInput, SortHead, useListState } from '@/lib/list'
import { useList } from '@/state/queries'

const FILTERS = ['q'] as const

export function LeaguesPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const from = useFrom(t('nav.leagues'))
  const list = useListState(FILTERS)
  const { data, isFetching } = useList('leagues', list.request, api.leagues)
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
      </div>
      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={list.values.q} onChange={(v) => list.update({ q: v })} placeholder={t('leagues.search')} />
      </FilterBar>
      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12" />
            <SortHead field="name" label={t('col.name')} state={sortState} />
            <SortHead field="country" label={t('col.country')} state={sortState} />
            <SortHead field="level" label={t('col.level')} state={sortState} />
            <SortHead field="team_count" label={t('col.teams')} state={sortState} />
            <SortHead field="id" label={t('col.id')} state={sortState} />
          </TableRow>
        </TableHeader>
        <TableBody className={isFetching ? 'opacity-70' : undefined}>
          {data?.items.map((l) => (
            <TableRow key={l.id} className={l.is_new ? 'cursor-pointer' : 'cursor-pointer text-muted-foreground'} onClick={() => navigate(`/leagues/${l.id}`, from)}>
              <TableCell>
                <LeagueImage id={l.id} size={64} available={!!l.has_logo} className="size-8" />
              </TableCell>
              <TableCell data-grow>
                <span className="font-medium text-foreground">{l.name}</span> <OriginalBadge edited={l.edited} isNew={l.is_new} />
              </TableCell>
              <TableCell>{l.country ?? '—'}</TableCell>
              <TableCell className="tabular-nums">{l.level ?? '—'}</TableCell>
              <TableCell className="tabular-nums">{l.team_count}</TableCell>
              <TableCell className="text-muted-foreground tabular-nums">{l.id}</TableCell>
            </TableRow>
          ))}
          {data && data.items.length === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
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
