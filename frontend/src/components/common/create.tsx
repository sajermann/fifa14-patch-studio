import { useQuery } from '@tanstack/react-query'
import { Check, Loader2, Plus } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { api } from '@/api/client'
import { Crest } from '@/components/common/pictures'
import { useI18n } from '@/i18n'
import { SearchInput } from '@/lib/list'
import { cn } from '@/lib/utils'
import { useToken } from '@/state/queries'

/** Asks for the name of a new item (the same name for every language; the edit screen refines it). */
export function CreateDialog({
  open,
  onOpenChange,
  title,
  description,
  label,
  maxLength,
  pending,
  onCreate,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  label: string
  maxLength?: number
  pending: boolean
  onCreate: (name: string) => void
  children?: ReactNode
}) {
  const { t } = useI18n()
  const [name, setName] = useState('')
  const submit = () => name.trim() && onCreate(name.trim())
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!pending) onOpenChange(o)
        if (!o) setName('')
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <p className="text-sm font-medium">{label}</p>
          <Input autoFocus value={name} maxLength={maxLength} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && submit()} />
          {children}
        </div>
        <DialogFooter>
          <Button variant="outline" disabled={pending} onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button disabled={!name.trim() || pending} onClick={submit}>
            {pending ? <Loader2 className="animate-spin" /> : <Plus />} {t('common.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Search the game's teams and pick some (the ones already chosen are marked). */
export function TeamPicker({ open, onOpenChange, chosen, onPick }: { open: boolean; onOpenChange: (open: boolean) => void; chosen: number[]; onPick: (id: number) => void }) {
  const { t } = useI18n()
  const token = useToken()
  const [q, setQ] = useState('')
  const { data, isFetching } = useQuery({
    queryKey: ['teams', token, 'picker', q],
    queryFn: () => api.teams({ q, size: 50, sort: 'name' }),
    enabled: open && !!token,
  })
  const taken = new Set(chosen)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent width="lg">
        <DialogHeader>
          <DialogTitle>{t('league.addTeams')}</DialogTitle>
          <DialogDescription>{t('league.addTeamsHint')}</DialogDescription>
        </DialogHeader>
        <SearchInput value={q} onChange={setQ} placeholder={t('teams.search')} className="w-full" />
        <ScrollArea className="max-h-[60vh] pr-3">
          <div className={cn('space-y-1', isFetching && 'opacity-70')}>
            {data?.items.map((tm) => {
              const inside = taken.has(tm.id)
              return (
                <button
                  key={tm.id}
                  type="button"
                  disabled={inside}
                  onClick={() => onPick(tm.id)}
                  className="flex w-full items-center gap-3 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent disabled:cursor-default disabled:opacity-60 disabled:hover:bg-transparent"
                >
                  <Crest id={tm.id} size={64} available={tm.has_crest} className="size-7" />
                  <span className="flex-1 truncate">
                    {tm.name} <span className="text-xs text-muted-foreground">{tm.league ?? ''}</span>
                  </span>
                  {inside ? <Check className="size-4 text-emerald-600" /> : <Plus className="size-4 text-muted-foreground" />}
                </button>
              )
            })}
            {data && data.items.length === 0 && <p className="py-8 text-center text-sm text-muted-foreground">{t('list.empty')}</p>}
          </div>
        </ScrollArea>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.close')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
