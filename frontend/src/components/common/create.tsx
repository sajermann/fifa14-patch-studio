import { Loader2, Plus } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/i18n'

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
