import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, ScanFace } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { HideButton, OutOfPatchBadge, useHide } from '@/components/common/HideButton'
import { NewPlayerDialog, nameFields, type NewPlayer } from '@/components/player/NewPlayerDialog'
import { toast } from '@/lib/notify'
import { useFrom } from '@/lib/back'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/api/client'
import { OriginalBadge, OverallBadge } from '@/components/common/detail'
import { EntityIssues } from '@/components/common/form'
import { Photo } from '@/components/common/pictures'
import { BulkActions, RowCheckbox, SelectAllCheckbox, SelectAllDialog, useListSelection } from '@/components/common/selection'
import { useI18n } from '@/i18n'
import { FilterBar, FilterSelect, LIST_PAGE, Pager, ScrollTable, SearchInput, SortHead, useListState } from '@/lib/list'
import { useList, useOptions } from '@/state/queries'

const FILTERS = ['q', 'position', 'team', 'face', 'origin'] as const

export function PlayersPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const from = useFrom({ key: 'nav.players' })
  const list = useListState(FILTERS)
  const { data, isFetching } = useList('players', list.request, api.players)
  // the project's items (created, or edited ones of the game) can be picked and deleted in bulk, like in the Street Studio
  const own = (r: { is_new: boolean; edited?: boolean }) => r.is_new || !!r.edited
  const selection = useListSelection((data?.items ?? []).filter(own).map((r) => r.id), data?.own_ids ?? [])
  const options = useOptions().data
  const qc = useQueryClient()
  const hide = useHide('player', ['players', 'player', 'teams', 'team'])
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
          options={(options?.positions ?? []).map((p) => ({
            value: String(p.id),
            label: p.name,
          }))}
        />
        <FilterSelect
          value={list.values.team}
          onChange={(v) => list.update({ team: v })}
          allLabel={t('filter.allTeams')}
          options={(options?.teams ?? []).map((tm) => ({ value: String(tm.id), label: tm.name }))}
        />
        <FilterSelect
          value={list.values.face}
          onChange={(v) => list.update({ face: v })}
          allLabel={t('filter.faceAny')}
          options={[
            { value: 'yes', label: t('filter.faceYes') },
            { value: 'no', label: t('filter.faceNo') },
          ]}
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
        <BulkActions kind="player" selection={selection} invalidate={['players', 'player', 'teams', 'team']} />
      </FilterBar>
      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <SelectAllCheckbox selection={selection} />
            </TableHead>
            <TableHead className="w-12" />
            <SortHead field="name" label={t('col.name')} state={sortState} />
            <SortHead field="team" label={t('col.team')} state={sortState} className="text-right" />
            <SortHead field="overall" label={t('col.overall')} state={sortState} className="text-center" />
            <SortHead field="position" label={t('col.position')} state={sortState} className="text-center" />
            <SortHead field="birthdate" label={t('col.birthdate')} state={sortState} className="text-center" />
            <SortHead field="id" label={t('col.id')} state={sortState} className="text-center" />
            <TableHead>{t('col.nationality')}</TableHead>
            <TableHead className="w-28" />
            <TableHead className="w-16" />
          </TableRow>
        </TableHeader>
        <TableBody className={isFetching ? 'opacity-70' : undefined}>
          {data?.items.map((p) => (
            <TableRow key={p.id} className="text-muted-foreground">
              <TableCell>{own(p) && <RowCheckbox selection={selection} value={p.id} />}</TableCell>
              <TableCell>
                <Photo id={p.id} size={64} available={p.has_photo} className="size-8" />
              </TableCell>
              <TableCell data-grow>
                <span className="inline-flex items-center gap-2">
                  <Link to={`/players/${p.id}`} state={from.state} className="font-medium text-foreground underline-offset-4 hover:underline">{p.name}</Link>
                  {p.has_face && <ScanFace className="size-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-label={t('squad.hasFace')} />}
                  {!p.is_new && <OriginalBadge edited={p.edited} />}
                  {p.hidden && <OutOfPatchBadge />}
                </span>
              </TableCell>
              <TableCell className="text-right">{p.team ?? '—'}</TableCell>
              <TableCell className="text-center">
                <OverallBadge value={p.overall} />
              </TableCell>
              <TableCell className="text-center">{p.position_name ?? '—'}</TableCell>
              <TableCell className="text-center tabular-nums">{p.birthdate ?? '—'}</TableCell>
              <TableCell className="text-center text-muted-foreground tabular-nums">{p.id}</TableCell>
              <TableCell>{p.nationality_name ?? '—'}</TableCell>
              <TableCell>
                {p.is_new && (
                  <HideButton
                    hidden={p.hidden}
                    disabled={hide.isPending && hide.variables?.id === p.id}
                    onToggle={() => hide.mutate({ id: p.id, hidden: !p.hidden })}
                    hideHint={t('players.hideHint')}
                    showHint={t('players.showHint')}
                  />
                )}
              </TableCell>
              <TableCell>
                <EntityIssues kind="player" id={p.id} />
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
