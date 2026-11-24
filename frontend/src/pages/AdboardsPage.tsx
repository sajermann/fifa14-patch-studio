import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import { AdboardThumb, useAdboardName, useAdboards, useCompetitionsText } from '@/components/adboard/AdboardChoice'
import { DateCells, DateHeads } from '@/components/common/dates'
import { OriginalBadge } from '@/components/common/detail'
import { HideButton, OutOfPatchBadge } from '@/components/common/HideButton'
import { BulkActions, RowCheckbox, SelectAllCheckbox, SelectAllDialog, useListSelection } from '@/components/common/selection'
import { Button } from '@/components/ui/button'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { ALL, FilterBar, FilterSelect, LIST_PAGE, ScrollTable, SearchInput } from '@/lib/list'
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
  const boards = (data?.items ?? []).filter(
    (b) =>
      (nameOf(b).toLowerCase().includes(query) || String(b.id).includes(query)) &&
      (origin === ALL || (origin === 'project' ? b.is_new : origin === 'edited' ? b.edited : !b.is_new)),
  )
  // the user's boards can be deleted, the game's edited ones restored, in bulk
  const pickable = boards.filter((b) => b.is_new || b.edited).map((b) => b.id)
  const selection = useListSelection(pickable, pickable)
  const create = useMutation({
    mutationFn: () => api.createAdboard({ name: t('adboards.defaultName', { n: (data?.items.filter((b) => b.is_new).length ?? 0) + 1 }) }),
    onSuccess: (board) => {
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
        <Button disabled={create.isPending} onClick={() => create.mutate()}>
          {create.isPending ? <Loader2 className="animate-spin" /> : <Plus />} {t('adboards.new')}
        </Button>
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
      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <SelectAllCheckbox selection={selection} />
            </TableHead>
            <TableHead className="w-12" />
            <TableHead data-grow>{t('col.name')}</TableHead>
            <TableHead>{t('adboards.colGame')}</TableHead>
            <TableHead className="text-center">{t('adboards.colTeams')}</TableHead>
            <TableHead className="text-center">{t('adboards.colLeagues')}</TableHead>
            <DateHeads />
            <TableHead className="w-28" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {boards.map((b) => (
            <TableRow key={b.id} className={b.is_new || b.edited ? 'cursor-pointer' : 'cursor-pointer text-muted-foreground'} onClick={() => navigate(`/adboards/${b.id}`, { state: from.state })}>
              <TableCell>{(b.is_new || b.edited) && <RowCheckbox selection={selection} value={b.id} />}</TableCell>
              <TableCell>
                <AdboardThumb board={b} width={20} />
              </TableCell>
              <TableCell data-grow>
                <span className="flex flex-wrap items-center gap-2">
                  <Link
                    to={`/adboards/${b.id}`}
                    state={from.state}
                    className={b.hidden ? 'font-medium text-muted-foreground' : 'font-medium text-foreground'}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {nameOf(b)}
                  </Link>
                  {!b.is_new && <OriginalBadge edited={b.edited} />}
                  {b.is_new && b.picture === null && <span className="text-xs text-amber-600 dark:text-amber-400">{t('adboards.noPicture')}</span>}
                  {b.hidden && <OutOfPatchBadge />}
                </span>
              </TableCell>
              <TableCell className="max-w-72 truncate text-muted-foreground" title={b.is_new ? undefined : where(b)}>
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
            </TableRow>
          ))}
          {!isLoading && boards.length === 0 && (
            <TableRow>
              <TableCell colSpan={9} className="py-10 text-center text-muted-foreground">
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
