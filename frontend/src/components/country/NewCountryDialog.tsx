import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { CreateDialog } from '@/components/common/create'
import { RefPickerDialog } from '@/components/common/edit'
import { CountryFlag } from '@/components/common/pictures'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useOptions } from '@/state/queries'

export interface NewCountry {
  name: string
  copyOf: number | null
}

/** "New country", like "New team": from scratch (blank: just its name) or a copy of a country (its flag). */
export function NewCountryDialog({ open, onOpenChange, pending, onCreate }: { open: boolean; onOpenChange: (o: boolean) => void; pending: boolean; onCreate: (country: NewCountry) => void }) {
  const { t } = useI18n()
  const [mode, setMode] = useState<'scratch' | 'copy'>('scratch')
  const [copyOf, setCopyOf] = useState<number | null>(null)
  const [picking, setPicking] = useState(false)
  const nations = useOptions().data?.nations ?? []
  const choice = (value: 'scratch' | 'copy', label: string, hint: string) => (
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
          if (!o) setCopyOf(null)
        }}
        title={t('countries.new')}
        description={t('countries.newHint')}
        label={t('countryName.full')}
        maxLength={40}
        pending={pending}
        onCreate={(name) => (mode === 'copy' && copyOf === null ? setPicking(true) : onCreate({ name, copyOf: mode === 'copy' ? copyOf : null }))}
      >
        <div className="flex gap-2 pt-2">
          {choice('scratch', t('create.fromScratch'), t('country.fromScratchHint'))}
          {choice('copy', t('country.copyOf'), t('country.copyOfHint'))}
        </div>
        {mode === 'copy' && (
          <div className="pt-1">
            <Button type="button" variant="outline" className="w-full justify-between font-normal" onClick={() => setPicking(true)}>
              <span className="flex min-w-0 items-center gap-2">
                {copyOf !== null && <CountryFlag id={copyOf} size={64} className="h-3.5 w-5" />}
                <span className={cn('truncate', copyOf === null && 'text-muted-foreground')}>
                  {copyOf !== null ? (nations.find((n) => n.id === copyOf)?.name ?? `#${copyOf}`) : t('country.choose')}
                </span>
              </span>
              <ChevronDown className="opacity-50" />
            </Button>
          </div>
        )}
      </CreateDialog>
      <RefPickerDialog
        kind="nation"
        open={picking}
        onOpenChange={setPicking}
        title={t('country.choose')}
        actionLabel={t('field.pick.choose')}
        onPick={(id) => {
          setCopyOf(id)
          setPicking(false)
        }}
      />
    </>
  )
}
