import { useQuery } from '@tanstack/react-query'
import { ChevronDown, FolderOpen } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api/client'
import { CreateDialog } from '@/components/common/create'
import { StadiumImage } from '@/components/common/pictures'
import { StadiumPickerDialog } from '@/components/team/TeamStadiums'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useToken } from '@/state/queries'

export interface NewStadium {
  name: string
  /** the folder of a downloaded stadium (its 3D scene), or null */
  folder: string | null
  /** the game stadium it copies, or null */
  template: number | null
}

/** "New stadium" (same layout as the New team dialog): from the folder of a downloaded stadium (its 3D scene; the data
 * of the stadium it replaced in the game) or a copy of a game stadium (its data, 3D and pictures). The folder is
 * optional: without it the stadium starts as the generic one and gets its folder later, on its screen. */
export function NewStadiumDialog({ open, onOpenChange, pending, onCreate }: { open: boolean; onOpenChange: (o: boolean) => void; pending: boolean; onCreate: (s: NewStadium) => void }) {
  const { t } = useI18n()
  const token = useToken()
  const [mode, setMode] = useState<'folder' | 'copy'>('folder')
  const [folder, setFolder] = useState<string | null>(null)
  const [copyOf, setCopyOf] = useState<number | null>(null)
  const [picking, setPicking] = useState(false)
  const [browsing, setBrowsing] = useState(false)
  const template = useQuery({
    queryKey: ['stadium', token, 'template', copyOf],
    queryFn: () => api.stadium(copyOf as number),
    enabled: !!token && copyOf !== null,
  }).data
  const browse = async () => {
    setBrowsing(true)
    try {
      const { path } = await api.pickFolder(folder, t('stadium.newFolderTitle'))
      if (path) setFolder(path)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBrowsing(false)
    }
  }
  const choice = (value: 'folder' | 'copy', label: string, hint: string) => (
    <button
      type="button"
      onClick={() => setMode(value)}
      className={cn('flex-1 rounded-md border p-2 text-left text-sm', mode === value ? 'border-primary bg-primary/5' : 'hover:bg-muted/50')}
    >
      <span className="block font-medium">{label}</span>
      <span className="block text-xs text-muted-foreground">{hint}</span>
    </button>
  )
  return (
    <>
      <CreateDialog
        open={open}
        onOpenChange={(o) => {
          onOpenChange(o)
          if (!o) {
            setFolder(null)
            setCopyOf(null)
          }
        }}
        title={t('stadium.newTitle')}
        description={t('stadium.newDescription')}
        label={t('stadiumName.full')}
        maxLength={60}
        pending={pending}
        onCreate={(name) => {
          if (mode === 'copy' && copyOf === null) return setPicking(true)
          onCreate({ name, folder: mode === 'folder' ? folder : null, template: mode === 'copy' ? copyOf : null })
        }}
      >
        <div className="flex gap-2 pt-2">
          {choice('folder', t('stadium.fromFolder'), t('stadium.fromFolderHint'))}
          {choice('copy', t('stadium.copyOf'), t('stadium.copyOfHint'))}
        </div>
        {mode === 'folder' ? (
          <div className="space-y-1 pt-1">
            <Button type="button" variant="outline" className="w-full justify-between font-normal" disabled={browsing} onClick={browse}>
              <span className={cn('truncate', !folder && 'text-muted-foreground')}>{folder ?? t('stadium.chooseFolder')}</span>
              <FolderOpen className="opacity-50" />
            </Button>
            {pending && <p className="text-xs text-muted-foreground">{t('stadium.readingFolder')}</p>}
          </div>
        ) : (
          <div className="pt-1">
            <Button type="button" variant="outline" className="w-full justify-between font-normal" onClick={() => setPicking(true)}>
              <span className="flex min-w-0 items-center gap-2">
                {template && template.pictures.length > 0 && (
                  <StadiumImage id={template.id} variant={template.pictures[0]} size={128} className="h-5 w-16 rounded object-cover" />
                )}
                <span className={cn('truncate', copyOf === null && 'text-muted-foreground')}>{copyOf === null ? t('stadium.chooseStadium') : (template?.name ?? `#${copyOf}`)}</span>
              </span>
              <ChevronDown className="opacity-50" />
            </Button>
          </div>
        )}
      </CreateDialog>
      <StadiumPickerDialog
        open={picking}
        onOpenChange={setPicking}
        current={null}
        gameOnly
        title={t('stadium.chooseStadium')}
        description={t('stadium.copyOfHint')}
        onPick={(sid) => setCopyOf(sid)}
      />
    </>
  )
}
