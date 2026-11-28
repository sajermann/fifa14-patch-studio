import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LayoutGrid, Loader2, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import type { Formation } from '@/api/types'
import { OriginalBadge } from '@/components/common/detail'
import { HideButton, OutOfPatchBadge } from '@/components/common/HideButton'
import { NewItemDialog } from '@/components/common/NewItemDialog'
import { Button } from '@/components/ui/button'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { ALL, FilterBar, FilterSelect, LIST_PAGE, ScrollTable, SearchInput, SortHead, useLocalSort } from '@/lib/list'
import { toast } from '@/lib/notify'
import { useOptions, useToken } from '@/state/queries'

export function useFormations() {
  const token = useToken()
  return useQuery({ queryKey: ['formations', token], queryFn: api.formations, enabled: !!token })
}

/** The positions of a formation in the game's short names, goalkeeper left out ("RB RCB LCB LB ..."). */
export function usePositionsText() {
  const positions = useOptions().data?.positions ?? []
  return (codes: number[]) => codes.slice(1).map((c) => positions.find((p) => p.id === c)?.name ?? String(c)).join(' ')
}

/** The formations (laid out like the boards list): the user's, then the game's 33 (read only: copy one to change it).
 * Each of the user's goes into the patch as a formation of its own that any team may take. */
export function FormationsPage() {
  const { t } = useI18n()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const from = useFrom({ key: 'nav.formations' })
  const text = usePositionsText()
  const { data, isLoading } = useFormations()
  const [q, setQ] = useState('')
  const [origin, setOrigin] = useState(ALL)
  const query = q.trim().toLowerCase()
  const filtered = (data?.items ?? []).filter(
    (f) =>
      (f.name.toLowerCase().includes(query) || String(f.id).includes(query) || text(f.positions).toLowerCase().includes(query)) &&
      (origin === ALL || (origin === 'project' ? f.is_new : !f.is_new)),
  )
  const sorted = useLocalSort(filtered, { name: (f) => f.name, id: (f) => f.id, teams: (f) => f.teams ?? 0 })
  const rows = sorted.rows
  const [creating, setCreating] = useState(false)
  const create = useMutation({
    mutationFn: (n: { name: string; copyOf: number | null }) => api.createFormation({ name: n.name, copy_of: n.copyOf ?? undefined }),
    onSuccess: (f) => {
      setCreating(false)
      void qc.invalidateQueries({ queryKey: ['formations'] })
      void qc.invalidateQueries({ queryKey: ['status'] })
      navigate(`/formations/${f.id}`, { state: from.state })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const hide = useMutation({
    mutationFn: ({ id, hidden }: { id: number; hidden: boolean }) => api.setFormationHidden(id, hidden),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['formations'] })
      void qc.invalidateQueries({ queryKey: ['issues'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  return (
    <div className={LIST_PAGE}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{t('formations.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('formations.subtitle', { max: data?.max ?? 899 })}</p>
        </div>
        <Button disabled={create.isPending} onClick={() => setCreating(true)}>
          {create.isPending ? <Loader2 className="animate-spin" /> : <Plus />} {t('formations.new')}
        </Button>
        <NewItemDialog
          copyOnly
          open={creating}
          onOpenChange={setCreating}
          title={t('formations.new')}
          description={t('formations.newHint')}
          label={t('formations.name')}
          maxLength={24}
          pending={create.isPending}
          scratchHint=""
          copyLabel={t('formations.copyOf')}
          copyHint={t('formations.copyOfHint')}
          chooseLabel={t('formations.choose')}
          placeholder={t('formations.search')}
          groups={(query) => {
            const all = (data?.items ?? []).filter((f) => !query || f.name.toLowerCase().includes(query) || String(f.id).includes(query))
            const item = (f: Formation) => ({ key: f.id, icon: <LayoutGrid className="size-5 text-muted-foreground" />, title: f.name, subtitle: text(f.positions) })
            return [
              { label: t('formations.originProject'), items: all.filter((f) => f.is_new).map(item) },
              { label: t('list.originOriginal'), items: all.filter((f) => !f.is_new).map(item) },
            ]
          }}
          chosen={(id) => data?.items.find((x) => x.id === id)?.name ?? `#${id}`}
          onCreate={(n) => create.mutate(n)}
        />
      </div>
      <FilterBar active={!!q || origin !== ALL} onClear={() => (setQ(''), setOrigin(ALL))}>
        <SearchInput value={q} onChange={setQ} placeholder={t('formations.search')} />
        <FilterSelect
          value={origin}
          onChange={setOrigin}
          allLabel={t('list.originAll')}
          options={[
            { value: 'project', label: t('formations.originProject') },
            { value: 'original', label: t('list.originOriginal') },
          ]}
        />
      </FilterBar>
      <ScrollTable loading={isLoading}>
        <TableHeader>
          <TableRow>
            <SortHead field="name" label={t('col.name')} state={sorted.state} />
            <TableHead className="w-full">{t('formations.colPositions')}</TableHead>
            <SortHead field="teams" label={t('formations.colTeams')} state={sorted.state} className="text-center" />
            <SortHead field="id" label="ID" state={sorted.state} className="text-center" />
            <TableHead className="w-28" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((f) => (
            <TableRow key={f.id} className={f.is_new ? undefined : 'text-muted-foreground'}>
              <TableCell className="whitespace-nowrap">
                <span className="flex items-center gap-2">
                  <Link
                    to={`/formations/${f.id}`}
                    state={from.state}
                    className={f.hidden ? 'font-medium text-muted-foreground underline-offset-4 hover:underline' : 'font-medium text-foreground underline-offset-4 hover:underline'}
                  >
                    {f.name}
                  </Link>
                  {!f.is_new && <OriginalBadge />}
                  {f.hidden && <OutOfPatchBadge />}
                </span>
              </TableCell>
              <TableCell data-grow className="text-muted-foreground">
                {text(f.positions)}
              </TableCell>
              <TableCell className="text-center tabular-nums">{f.teams || '—'}</TableCell>
              <TableCell className="text-center tabular-nums">{f.id}</TableCell>
              <TableCell>
                {f.is_new && <HideButton hidden={!!f.hidden} onToggle={() => hide.mutate({ id: f.id, hidden: !f.hidden })} hideHint={t('formations.hideHint')} showHint={t('formations.showHint')} />}
              </TableCell>
            </TableRow>
          ))}
          {!isLoading && rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                {t('list.empty')}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </ScrollTable>
    </div>
  )
}
