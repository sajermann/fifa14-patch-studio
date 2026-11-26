import { useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { ApiError, api } from '@/api/client'
import type { BulkKind } from '@/api/types'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { BulkDeleteProgressDialog } from '@/components/common/BulkDeleteProgress'
import { useI18n, type MessageKey } from '@/i18n'
import { toast } from '@/lib/notify'

// ---------------------------------------------------------------- selection in the lists (as in the Street Studio)
/** Rows picked by their checkbox; the header one asks "this page or every page". */
export function useListSelection(pageKeys: number[], allKeys: number[]) {
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [askAll, setAskAll] = useState(false)
  const toggle = (key: number) =>
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  const pick = (keys: number[]) => {
    setSelected((s) => new Set([...s, ...keys]))
    setAskAll(false)
  }
  const allOnPage = pageKeys.length > 0 && pageKeys.every((k) => selected.has(k))
  return { selected, toggle, clear: () => setSelected(new Set()), allOnPage, askAll, setAskAll, pick, pageKeys, allKeys }
}
export type ListSelection = ReturnType<typeof useListSelection>

export function SelectAllCheckbox({ selection }: { selection: ListSelection }) {
  const { t } = useI18n()
  return (
    <Checkbox
      checked={selection.allOnPage}
      disabled={!selection.pageKeys.length}
      aria-label={t('share.selectAll')}
      onCheckedChange={(v) => {
        if (v === true) selection.setAskAll(true)
        else selection.clear()
      }}
    />
  )
}

export function RowCheckbox({ selection, value }: { selection: ListSelection; value: number }) {
  const { t } = useI18n()
  return (
    <span onClick={(e) => e.stopPropagation()}>
      <Checkbox checked={selection.selected.has(value)} onCheckedChange={() => selection.toggle(value)} aria-label={t('share.select')} />
    </span>
  )
}

export function SelectAllDialog({ selection }: { selection: ListSelection }) {
  const { t } = useI18n()
  return (
    <AlertDialog open={selection.askAll} onOpenChange={selection.setAskAll}>
      {/* three buttons with counts: the medium width (ui/dialog-width.ts) */}
      <AlertDialogContent width="md">
        <AlertDialogHeader>
          <AlertDialogTitle>{t('share.selectAllTitle')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('share.selectAllDescription', { page: selection.pageKeys.length, all: selection.allKeys.length })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <Button variant="outline" onClick={() => selection.pick(selection.pageKeys)}>
            {t('share.selectPage', { count: selection.pageKeys.length })}
          </Button>
          <AlertDialogAction onClick={() => selection.pick(selection.allKeys)}>
            {t('share.selectEvery', { count: selection.allKeys.length })}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** "Delete (n)" of the selected rows, with the confirmation. A created item leaves the project, an edited one of the
 * game goes back to the game's; `invalidate` = the queries that show them. */
export function BulkActions({ kind, selection, invalidate }: { kind: BulkKind; selection: ListSelection; invalidate: string[] }) {
  const { t } = useI18n()
  const qc = useQueryClient()
  const picked = [...selection.selected]
  // the entries picked when the confirmation opened (the count stays while it closes)
  const [deleting, setDeleting] = useState<number[] | null>(null)
  // the entries being deleted (the progress window shows while it runs)
  const [busy, setBusy] = useState<number[] | null>(null)
  const run = async (ids: number[]) => {
    setBusy(ids)
    try {
      const out = await api.bulkDelete(kind, ids)
      const done = out.deleted.length + out.reset.length
      if (out.cancelled) toast.info(t('bulkDelete.stopped', { count: done }))
      else if (done) toast.success(t('share.deleted', { count: done }))
      if (out.skipped.length) toast.warning(t(`share.deleteSkipped.${kind}` as MessageKey, { count: out.skipped.length }))
      selection.clear()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('share.deleteError'))
    } finally {
      for (const k of [...invalidate, 'status', 'options']) void qc.invalidateQueries({ queryKey: [k] })
      setBusy(null)
    }
  }
  return (
    <div className="ml-auto flex gap-2">
      <Button variant="outline" size="sm" disabled={!picked.length || !!busy} onClick={() => setDeleting(picked)}>
        <Trash2 /> {t('share.deleteSelected', { count: picked.length })}
      </Button>
      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('share.deleteTitle', { count: deleting?.length ?? 0 })}</AlertDialogTitle>
            <AlertDialogDescription>{t(`share.deleteDescription.${kind}` as MessageKey)}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => deleting && void run(deleting)}>{t('common.delete')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <BulkDeleteProgressDialog open={!!busy} total={busy?.length ?? 0} />
    </div>
  )
}
