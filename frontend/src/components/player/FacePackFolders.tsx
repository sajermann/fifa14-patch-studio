import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderPlus, X } from 'lucide-react'
import { api } from '@/api/client'
import { Section } from '@/components/common/detail'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { toast } from '@/lib/notify'
import { useStatus } from '@/state/queries'

/** The face pack folders (Settings): one folder = one or more packs, read in place, never written. */
export function FacePackFolders() {
  const { t } = useI18n()
  const qc = useQueryClient()
  const dirs = useStatus().data?.config.face_pack_dirs ?? []
  const packs = useQuery({ queryKey: ['facepacks'], queryFn: api.facePacks })
  const save = useMutation({
    mutationFn: (face_pack_dirs: string[]) => api.saveSettings({ face_pack_dirs }),
    onSuccess: () => {
      for (const k of ['status', 'facepacks', 'facepack']) void qc.invalidateQueries({ queryKey: [k] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const add = useMutation({
    mutationFn: () => api.pickFolder(dirs[dirs.length - 1] ?? null, t('settings.chooseFaceFolder')),
    onSuccess: ({ path }) => {
      if (path && !dirs.includes(path)) save.mutate([...dirs, path])
    },
    onError: (e: Error) => toast.error(e.message),
  })
  return (
    <Section
      title={t('settings.facePacks')}
      description={t('settings.facePacksHint')}
      action={
        <Button size="sm" variant="outline" disabled={add.isPending || save.isPending} onClick={() => add.mutate()}>
          <FolderPlus /> {t('settings.addFolder')}
        </Button>
      }
    >
      <div className="space-y-2">
        {dirs.map((dir) => {
          const info = packs.data?.find((f) => f.folder === dir)
          const faces = info?.parts.reduce((n, p) => n + p.count, 0) ?? 0
          return (
            <div key={dir} className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-xs">{dir}</p>
                <p className="text-xs text-muted-foreground">
                  {info && !info.exists ? t('settings.folderMissing') : info ? t('settings.packsFound', { count: info.parts.length, faces }) : '…'}
                </p>
              </div>
              <Button variant="ghost" size="icon-sm" title={t('settings.removeFolder')} aria-label={t('settings.removeFolder')} onClick={() => save.mutate(dirs.filter((d) => d !== dir))}>
                <X />
              </Button>
            </div>
          )
        })}
      </div>
    </Section>
  )
}
