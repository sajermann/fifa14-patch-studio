import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { OutOfPatchBadge } from '@/components/common/HideButton'
import { NewPlayerDialog, nameFields, type NewPlayer } from '@/components/player/NewPlayerDialog'
import { toast } from '@/lib/notify'
import { useFrom } from '@/lib/back'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/api/client'
import { OriginalBadge, OverallBadge } from '@/components/common/detail'
import { Photo } from '@/components/common/pictures'
import { useI18n } from '@/i18n'
import { FilterBar, FilterSelect, LIST_PAGE, Pager, ScrollTable, SearchInput, SortHead, useListState } from '@/lib/list'
import { useList, useOptions } from '@/state/queries'

const FILTERS = ['q', 'position', 'origin'] as const

export function PlayersPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const from = useFrom({ key: 'nav.players' })
  const list = useListState(FILTERS)
  const { data, isFetching } = useList('players', list.request, api.players)
  const options = useOptions().data
  const qc = useQueryClient()
  const [creating, setCreating] = useState(false)
  const create = useMutation({
    mutationFn: (n: NewPlayer) => api.createPlayer({ fields: nameFields(n.name), template: n.copyOf }),
    onSuccess: (p) => {
      for (const k of ['players', 'status']) void qc.invalidateQueries({ queryKey: [k] })
      setCreating(false)
      toast.success(t('player.created'))
      navigate(`/players/${p.id}`, from)
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
          <h1 className="text-2xl font-semibold">{t('players.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('players.subtitleFull')}</p>
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus /> {t('players.new')}
        </Button>
      </div>
      <NewPlayerDialog open={creating} onOpenChange={setCreating} pending={create.isPending} onCreate={(n) => create.mutate(n)} />
      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={list.values.q} onChange={(v) => list.update({ q: v })} placeholder={t('players.search')} />
        <FilterSelect
          value={list.values.position}
          onChange={(v) => list.update({ position: v })}
          allLabel={t('filter.allPositions')}
          className="w-40"
          options={(options?.positions ?? []).map((p) => ({
            value: String(p.id),
            label: p.name,
          }))}
        />
        <FilterSelect
          value={list.values.origin}
          onChange={(v) => list.update({ origin: v })}
          allLabel={t('list.originAll')}
          className="w-44"
          options={[
            { value: 'project', label: t('list.originProject') },
            { value: 'original', label: t('list.originOriginal') },
          ]}
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
            <TableRow key={p.id} className="cursor-pointer text-muted-foreground" onClick={() => navigate(`/players/${p.id}`, from)}>
              <TableCell>
                <Photo id={p.id} size={64} available={p.has_photo} className="size-8" />
              </TableCell>
              <TableCell data-grow>
                <span className="font-medium text-foreground">{p.name}</span> {!p.is_new && <OriginalBadge edited={p.edited} />}
                {p.hidden && <OutOfPatchBadge />}
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
