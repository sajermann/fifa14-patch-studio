import { useNavigate } from 'react-router-dom'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/api/client'
import { OverallBadge } from '@/components/common/detail'
import { Photo } from '@/components/common/pictures'
import { useI18n } from '@/i18n'
import { FilterBar, FilterSelect, LIST_PAGE, Pager, ScrollTable, SearchInput, SortHead, useListState } from '@/lib/list'
import { useList, useOptions } from '@/state/queries'

const FILTERS = ['q', 'position'] as const

export function PlayersPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const list = useListState(FILTERS)
  const { data, isFetching } = useList('players', list.request, api.players)
  const options = useOptions().data
  const sortState = { sort: list.sort, dir: list.dir, update: list.update, current: data?.sort ?? '', currentDir: data?.dir ?? '' }
  return (
    <div className={LIST_PAGE}>
      <div>
        <h1 className="text-2xl font-semibold">{t('players.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('players.subtitle')}</p>
      </div>
      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={list.values.q} onChange={(v) => list.update({ q: v })} placeholder={t('players.search')} />
        <FilterSelect
          value={list.values.position}
          onChange={(v) => list.update({ position: v })}
          allLabel={t('filter.allPositions')}
          className="w-40"
          options={(options?.positions ?? []).map((p) => ({ value: String(p.id), label: p.name }))}
        />
      </FilterBar>
      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12" />
            <SortHead field="name" label={t('col.name')} state={sortState} />
            <SortHead field="position" label={t('col.position')} state={sortState} />
            <SortHead field="overall" label={t('col.overall')} state={sortState} />
            <SortHead field="potential" label={t('col.potential')} state={sortState} />
            <SortHead field="team" label={t('col.team')} state={sortState} />
            <TableHead>{t('col.nationality')}</TableHead>
            <SortHead field="birthdate" label={t('col.birthdate')} state={sortState} />
            <SortHead field="id" label={t('col.id')} state={sortState} />
          </TableRow>
        </TableHeader>
        <TableBody className={isFetching ? 'opacity-70' : undefined}>
          {data?.items.map((p) => (
            <TableRow key={p.id} className="cursor-pointer" onClick={() => navigate(`/players/${p.id}`)}>
              <TableCell>
                <Photo id={p.id} size={64} available={p.has_photo} className="size-8" />
              </TableCell>
              <TableCell data-grow className="font-medium">
                {p.name}
              </TableCell>
              <TableCell>{p.position_name ?? '—'}</TableCell>
              <TableCell>
                <OverallBadge value={p.overall} />
              </TableCell>
              <TableCell>
                <OverallBadge value={p.potential} />
              </TableCell>
              <TableCell>{p.team ?? '—'}</TableCell>
              <TableCell>{p.nationality_name ?? '—'}</TableCell>
              <TableCell className="tabular-nums">{p.birthdate ?? '—'}</TableCell>
              <TableCell className="text-muted-foreground tabular-nums">{p.id}</TableCell>
            </TableRow>
          ))}
          {data && data.items.length === 0 && (
            <TableRow>
              <TableCell colSpan={9} className="py-10 text-center text-muted-foreground">
                {t('list.empty')}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </ScrollTable>
      {data && <Pager page={data.page} pages={data.pages} total={data.total} size={data.size} onPage={(page, size) => list.update({ page, ...(size ? { size } : {}) }, false)} />}
    </div>
  )
}
