import { Download, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { api, ApiError, saveBlob } from '@/api/client'
import type { ShareKind, ShareTree } from '@/api/types'
import { ShareTreeView, TreeLegend, useTreeChoice } from '@/components/common/shareTree'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useI18n } from '@/i18n'

/** "Export" on an item's screen: the tree of the item and what it takes along (only what the project created or
 * changed), each one with its checkbox, then the zip. `dirty`: the screen has changes not saved yet (they do not go). */
export function ExportButton({ kind, id, dirty }: { kind: ShareKind; id: number; dirty?: boolean }) {
  const { t } = useI18n()
  const [tree, setTree] = useState<ShareTree | null>(null)
  const [busy, setBusy] = useState(false)
  const open = async () => {
    setBusy(true)
    try {
      setTree(await api.shareExport(kind, id))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('share.downloadFailed'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <Button variant="outline" size="sm" disabled={busy} title={dirty ? t('share.downloadDirty') : t('share.downloadHint')} onClick={() => void open()}>
        {busy ? <Loader2 className="animate-spin" /> : <Download />} {t('share.download')}
      </Button>
      {tree && <ExportDialog tree={tree} onClose={() => setTree(null)} />}
    </>
  )
}

function ExportDialog({ tree, onClose }: { tree: ShareTree; onClose: () => void }) {
  const { t } = useI18n()
  const choice = useTreeChoice(tree, () => true)
  const [busy, setBusy] = useState(false)
  const count = choice.picked.size
  const run = async () => {
    setBusy(true)
    try {
      const { name, blob } = await api.shareExportZip(tree.token, [...choice.picked])
      saveBlob(name, blob)
      toast.success(t('share.downloaded', { count }))
      onClose()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('share.downloadFailed'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent width="full" className="flex flex-col">
        <DialogHeader>
          <DialogTitle>{t('share.exportTitle')}</DialogTitle>
          <DialogDescription>{t('share.exportHint')}</DialogDescription>
        </DialogHeader>
        <TreeLegend />
        <div className="min-h-0 flex-1 overflow-auto">
          <ShareTreeView tree={tree} choice={choice} />
        </div>
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button disabled={busy || count === 0} onClick={() => void run()}>
            {busy ? <Loader2 className="animate-spin" /> : <Download />} {t('share.downloadSelected', { count })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
