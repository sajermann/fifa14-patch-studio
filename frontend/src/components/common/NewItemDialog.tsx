import { ChevronDown } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { CreateDialog } from '@/components/common/create'
import { PickerDialog, type PickerGroup } from '@/components/common/PickerDialog'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'

/** "New …" of the lists without a dialog of their own (boards, boots, gloves, balls), laid out like "New team": the
 * name, then from scratch (blank) or a copy of an item picked from the list (`groups` for the search `query`;
 * `chosen` = how the picked one shows on its button). */
export function NewItemDialog({
  open,
  onOpenChange,
  title,
  description,
  label,
  maxLength,
  pending,
  scratchHint,
  copyLabel,
  copyHint,
  chooseLabel,
  placeholder,
  groups,
  chosen,
  onCreate,
  copyOnly = false,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  description: string
  label: string
  maxLength?: number
  pending: boolean
  scratchHint: string
  copyLabel: string
  copyHint: string
  chooseLabel: string
  placeholder: string
  groups: (query: string) => PickerGroup<number>[]
  chosen: (id: number) => ReactNode
  onCreate: (item: { name: string; copyOf: number | null }) => void
  /** an item is always a copy of another (no "from scratch") */
  copyOnly?: boolean
}) {
  const { t } = useI18n()
  const [mode, setMode] = useState<'scratch' | 'copy'>(copyOnly ? 'copy' : 'scratch')
  const [copyOf, setCopyOf] = useState<number | null>(null)
  const [picking, setPicking] = useState(false)
  const [q, setQ] = useState('')
  const choice = (value: 'scratch' | 'copy', text: string, hint: string) => (
    <button
      type="button"
      onClick={() => setMode(value)}
      className={cn('flex-1 rounded-md border p-2 text-left text-sm', mode === value ? 'border-primary bg-primary/5' : 'hover:bg-muted/50')}
    >
      <span className="block font-medium">{text}</span>
      <span className="block text-xs text-muted-foreground">{hint}</span>
    </button>
  )
  return (
    <>
      <CreateDialog
        open={open}
        onOpenChange={(o) => {
          onOpenChange(o)
          if (!o) setCopyOf(null)
        }}
        title={title}
        description={description}
        label={label}
        maxLength={maxLength}
        pending={pending}
        onCreate={(name) => (mode === 'copy' && copyOf === null ? setPicking(true) : onCreate({ name, copyOf: mode === 'copy' ? copyOf : null }))}
      >
        {copyOnly ? (
          <p className="pt-2 text-xs text-muted-foreground">{copyHint}</p>
        ) : (
          <div className="flex gap-2 pt-2">
            {choice('scratch', t('create.fromScratch'), scratchHint)}
            {choice('copy', copyLabel, copyHint)}
          </div>
        )}
        {mode === 'copy' && (
          <div className="pt-1">
            <Button type="button" variant="outline" className="w-full justify-between font-normal" onClick={() => setPicking(true)}>
              <span className={cn('flex min-w-0 items-center gap-2 truncate', copyOf === null && 'text-muted-foreground')}>
                {copyOf !== null ? chosen(copyOf) : chooseLabel}
              </span>
              <ChevronDown className="opacity-50" />
            </Button>
          </div>
        )}
      </CreateDialog>
      <PickerDialog
        open={picking}
        onOpenChange={(o) => {
          setPicking(o)
          if (!o) setQ('')
        }}
        title={chooseLabel}
        description={copyHint}
        placeholder={placeholder}
        query={q}
        onQuery={setQ}
        groups={groups(q.trim().toLowerCase())}
        empty={t('field.pick.empty')}
        actionLabel={t('field.pick.choose')}
        onPick={(id) => {
          setCopyOf(id)
          setPicking(false)
          setQ('')
        }}
      />
    </>
  )
}
