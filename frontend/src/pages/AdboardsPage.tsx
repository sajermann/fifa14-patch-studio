import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import type { Adboard } from '@/api/types'
import { AdboardThumb, useAdboardName, useAdboards, useCompetitionsText } from '@/components/adboard/AdboardChoice'
import { DateCells, DateHeads } from '@/components/common/dates'
import { OriginalBadge } from '@/components/common/detail'
import { EntityIssues } from '@/components/common/form'
import { NewItemDialog } from '@/components/common/NewItemDialog'
import { HideButton, OutOfPatchBadge } from '@/components/common/HideButton'
import { BulkActions, RowCheckbox, SelectAllCheckbox, SelectAllDialog, useListSelection } from '@/components/common/selection'
import { Button } from '@/components/ui/button'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { ALL, FilterBar, FilterSelect, LIST_PAGE, ScrollTable, SearchInput, SortHead, useLocalSort } from '@/lib/list'
import { toast } from '@/lib/notify'

/** The advertising boards (as the Street Studio's balls and gloves): the user's, then the game's (original or
 * edited), each with its picture; linked on the team and league screens. */
export function AdboardsPage() {
  const { t } = useI18n()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const from = useFrom({ key: 'nav.adboards' })
  const nameOf = useAdboardName()
  const where = useCompetitionsText()
  const { data, isLoading } = useAdboards()
  const [q, setQ] = useState('')
  const [origin, setOrigin] = useState(ALL)
  const query = q.trim().toLowerCase()
  const filtered = (data?.items ?? []).filter(
    (b) =>
      (nameOf(b).toLowerCase().includes(query) || String(b.id).includes(query)) &&
      (origin === ALL || (origin === 'project' ? b.is_new : origin === 'edited' ? b.edited : !b.is_new)),
  )
  const sorted = useLocalSort(filtered, {
    name: (b) => nameOf(b),
    game: (b) => (b.is_new ? '' : where(b)),
    teams: (b) => b.teams.length,
    leagues: (b) => b.leagues.length,
    created_at: (b) => b.created_at,
    updated_at: (b) => b.updated_at,
  })
  const boards = sorted.rows
  // the user's boards can be deleted, the game's edited ones restored, in bulk
  const pickable = boards.filter((b) => b.is_new || b.edited).map((b) => b.id)
  const selection = useListSelection(pickable, pickable)
  const [creating, setCreating] = useState(false)
  const create = useMutation({
    mutationFn: (n: { name: string; copyOf: number | null }) => api.createAdboard({ name: n.name, copy_of: n.copyOf ?? undefined }),
    onSuccess: (board) => {
      setCreating(false)
      void qc.invalidateQueries({ queryKey: ['adboards'] })
      navigate(`/adboards/${board.id}`, { state: from.state })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const hide = useMutation({
    mutationFn: ({ id, hidden }: { id: number; hidden: boolean }) => api.setAdboardHidden(id, hidden),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['adboards'] }),
    onError: (e: Error) => toast.error(e.message),
  })
  return (
    <div className={LIST_PAGE}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{t('adboards.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('adboards.subtitle')}</p>
        </div>
        <Button disabled={create.isPending} onClick={() => setCreating(true)}>
          {create.isPending ? <Loader2 className="animate-spin" /> : <Plus />} {t('adboards.new')}
        </Button>
        <NewItemDialog
          open={creating}
          onOpenChange={setCreating}
          title={t('adboards.new')}
          description={t('adboards.newHint')}
          label={t('adboards.name')}
          maxLength={60}
          pending={create.isPending}
          scratchHint={t('adboards.fromScratchHint')}
          copyLabel={t('adboards.copyOf')}
          copyHint={t('adboards.copyOfHint')}
          chooseLabel={t('adboards.choose')}
          placeholder={t('adboards.search')}
          groups={(query) => {
            const all = (data?.items ?? []).filter((b) => !query || nameOf(b).toLowerCase().includes(query) || String(b.id).includes(query))
            const item = (b: Adboard) => ({ key: b.id, icon: <AdboardThumb board={b} width={20} />, title: nameOf(b), subtitle: `ID ${b.id}` })
            return [
              { label: t('adboards.originProject'), items: all.filter((b) => b.is_new).map(item) },
              { label: t('list.originOriginal'), items: all.filter((b) => !b.is_new).map(item) },
            ]
          }}
          chosen={(id) => {
            const b = data?.items.find((x) => x.id === id)
            return (
              <>
                <AdboardThumb board={b} width={12} /> {b ? nameOf(b) : `#${id}`}
              </>
            )
          }}
          onCreate={(n) => create.mutate(n)}
        />
      </div>
      <FilterBar active={!!q || origin !== ALL} onClear={() => (setQ(''), setOrigin(ALL))}>
        <SearchInput value={q} onChange={setQ} placeholder={t('adboards.search')} />
        <FilterSelect
          value={origin}
          onChange={setOrigin}
          allLabel={t('list.originAll')}
          options={[
            { value: 'project', label: t('adboards.originProject') },
            { value: 'original', label: t('list.originOriginal') },
            { value: 'edited', label: t('adboards.originEdited') },
          ]}
        />
        <BulkActions kind="adboard" selection={selection} invalidate={['adboards', 'adboard', 'team', 'league']} />
      </FilterBar>
      <ScrollTable loading={isLoading}>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <SelectAllCheckbox selection={selection} />
            </TableHead>
            <TableHead className="w-12" />
            <SortHead field="name" label={t('col.name')} state={sorted.state} className="w-full" />
            <SortHead field="game" label={t('adboards.colGame')} state={sorted.state} className="text-right" />
            <SortHead field="teams" label={t('adboards.colTeams')} state={sorted.state} className="text-center" />
            <SortHead field="leagues" label={t('adboards.colLeagues')} state={sorted.state} className="text-center" />
            <DateHeads sort={sorted.state} />
            <TableHead className="w-28" />
            <TableHead className="w-16" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {boards.map((b) => (
            <TableRow key={b.id} className={b.is_new || b.edited ? undefined : 'text-muted-foreground'}>
              <TableCell>{(b.is_new || b.edited) && <RowCheckbox selection={selection} value={b.id} />}</TableCell>
              <TableCell>
                <AdboardThumb board={b} width={20} />
              </TableCell>
              <TableCell data-grow>
                <span className="flex flex-wrap items-center gap-2">
                  <Link
                    to={`/adboards/${b.id}`}
                    state={from.state}
                    className={b.hidden ? 'font-medium text-muted-foreground underline-offset-4 hover:underline' : 'font-medium text-foreground underline-offset-4 hover:underline'}
                  >
                    {nameOf(b)}
                  </Link>
                  {!b.is_new && <OriginalBadge edited={b.edited} />}
                  {b.hidden && <OutOfPatchBadge />}
                </span>
              </TableCell>
              <TableCell className="max-w-72 truncate text-right text-muted-foreground" title={b.is_new ? undefined : where(b)}>
                {b.is_new ? '—' : where(b)}
              </TableCell>
              <TableCell className="text-center tabular-nums" title={b.teams.map((x) => x.name).join(', ')}>
                {b.teams.length || '—'}
              </TableCell>
              <TableCell className="text-center tabular-nums" title={b.leagues.map((x) => x.name).join(', ')}>
                {b.leagues.length || '—'}
              </TableCell>
              <DateCells entry={b} />
              <TableCell>
                {b.is_new && <HideButton hidden={b.hidden} onToggle={() => hide.mutate({ id: b.id, hidden: !b.hidden })} hideHint={t('adboards.hideHint')} showHint={t('adboards.showHint')} />}
              </TableCell>
              <TableCell>
                <EntityIssues kind="adboard" id={b.id} />
              </TableCell>
            </TableRow>
          ))}
          {!isLoading && boards.length === 0 && (
            <TableRow>
              <TableCell colSpan={10} className="py-10 text-center text-muted-foreground">
                {t('list.empty')}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </ScrollTable>
      <SelectAllDialog selection={selection} />
    </div>
  )
}
