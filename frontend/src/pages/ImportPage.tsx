import { useQueryClient } from '@tanstack/react-query'
import { FileArchive, Loader2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { api, ApiError } from '@/api/client'
import type { ShareInspect } from '@/api/types'
import { Section } from '@/components/common/detail'
import { ShareTreeView, TreeLegend, useTreeChoice } from '@/components/common/shareTree'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useStatus } from '@/state/queries'

/** Import: one place for any zip the app exported (one item or many) and for a package of the extractor. The zip is
 * read first and its tree shown (always, even for one item), with what happens to each id; nothing changes in the
 * project until "Import". */
export function ImportPage() {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [found, setFound] = useState<ShareInspect | null>(null)
  const [reading, setReading] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null) // the import this page started (the dialog and the end
  // toast come from the shell's JobWatcher)
  const job = useStatus().data?.job
  const running = !!jobId && job?.id === jobId && job.state === 'running'
  const applying = starting || running
  const [dragging, setDragging] = useState(false)
  const [fillMissing, setFillMissing] = useState(true) // complete the faces that lack their eyes or hair
  const choice = useTreeChoice(found, (n) => !!n.default)
  const token = found?.token

  // a zip read and left without importing is let go
  useEffect(() => () => void (token && api.shareForget(token).catch(() => undefined)), [token])

  const read = async (file: File | undefined) => {
    if (!file) return
    setReading(file.name)
    try {
      setFound(await api.shareInspect(file))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('share.readFailed'))
    } finally {
      setReading(null)
      if (input.current) input.current.value = ''
    }
  }

  // the import ended: done = the zip is used up (back to picking one); stopped or failed = the tree stays, to try again
  useEffect(() => {
    if (!jobId || job?.id !== jobId || job.state === 'running') return
    setJobId(null)
    if (job.state === 'done') setFound(null)
  }, [job, jobId])

  const apply = async () => {
    if (!found) return
    setStarting(true)
    try {
      const started = await api.shareApply(found.token, [...choice.picked], fillMissing)
      setJobId(started.id)
      await queryClient.invalidateQueries({ queryKey: ['status'] })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('share.importFailed'))
    } finally {
      setStarting(false)
    }
  }

  const nodes = found ? Object.values(found.nodes) : []
  const renumbered = nodes.filter((n) => choice.picked.has(n.key) && n.reason === 'taken').length
  const replacing = nodes.filter((n) => choice.picked.has(n.key) && n.reason === 'replaces').length

  return (
    <div className="flex h-full flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">{t('share.importTitle')}</h1>
        <p className="text-sm text-muted-foreground">{t('share.importSubtitle')}</p>
      </div>

      <input ref={input} type="file" accept=".zip,application/zip" className="hidden" onChange={(e) => void read(e.target.files?.[0])} />

      {!found && (
        <button
          type="button"
          disabled={!!reading}
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            void read(e.dataTransfer.files?.[0])
          }}
          className={cn(
            'flex min-h-48 flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 text-center transition-colors hover:bg-muted/40',
            dragging && 'border-primary bg-primary/5',
          )}
        >
          {reading ? <Loader2 className="size-8 animate-spin text-muted-foreground" /> : <Upload className="size-8 text-muted-foreground" />}
          <span className="text-sm font-medium">{reading ? t('share.reading', { name: reading }) : t('share.pick')}</span>
          <span className="max-w-xl text-xs text-muted-foreground">{t('share.pickHint')}</span>
        </button>
      )}

      {found && (
        <>
          <Section title={t(found.origin === 'package' ? 'share.originPackage' : 'share.originOwn')}>
            <div className="space-y-1 text-sm">
              <p className="flex items-center gap-2">
                <FileArchive className="size-4 text-muted-foreground" />
                {found.patch_name ? t('share.patchName', { name: found.patch_name }) : t('share.itemsFound', { count: nodes.length })}
              </p>
              {found.origin === 'package' && <p className="text-muted-foreground">{t('share.packageHint')}</p>}
              {renumbered > 0 && <p className="text-amber-700 dark:text-amber-300">{t('share.renumbered', { count: renumbered })}</p>}
              {replacing > 0 && <p className="text-amber-700 dark:text-amber-300">{t('share.replacing', { count: replacing })}</p>}
              {found.warnings.length > 0 && <p className="text-amber-700 dark:text-amber-300">{t('share.warnings', { count: found.warnings.length })}</p>}
              {!!found.fillable && (
                <label className="flex items-start gap-2 pt-2">
                  <Checkbox className="mt-0.5" checked={fillMissing} onCheckedChange={(v) => setFillMissing(v === true)} />
                  <span>
                    {t('share.fillMissing', { count: found.fillable })}
                    <span className="block text-xs text-muted-foreground">{t('share.fillMissingHint')}</span>
                  </span>
                </label>
              )}
            </div>
          </Section>
          <TreeLegend />
          <div className="min-h-0 flex-1 overflow-auto">
            <ShareTreeView tree={found} choice={choice} ids />
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" disabled={applying} onClick={() => setFound(null)}>
              {t('share.pickOther')}
            </Button>
            <Button disabled={applying || choice.picked.size === 0} onClick={() => void apply()}>
              {applying ? <Loader2 className="animate-spin" /> : <Upload />} {t('share.importSelected', { count: choice.picked.size })}
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
