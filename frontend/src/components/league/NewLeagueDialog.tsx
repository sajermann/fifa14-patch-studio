import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { CreateDialog } from '@/components/common/create'
import { RefPickerDialog } from '@/components/common/edit'
import { LeagueImage } from '@/components/common/pictures'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useOptions } from '@/state/queries'

export interface NewLeague {
  name: string
  copyOf: number | null
  copyTeams: boolean
}

/** "New league", like "New team": from scratch (blank: no country, logo or teams) or a copy of a league (its level,
 * countries and logo, and its teams when asked). */
export function NewLeagueDialog({ open, onOpenChange, pending, onCreate }: { open: boolean; onOpenChange: (o: boolean) => void; pending: boolean; onCreate: (league: NewLeague) => void }) {
  const { t } = useI18n()
  const [mode, setMode] = useState<'scratch' | 'copy'>('scratch')
  const [copyOf, setCopyOf] = useState<number | null>(null)
  const [copyTeams, setCopyTeams] = useState(false)
  const [picking, setPicking] = useState(false)
  const leagues = useOptions().data?.leagues ?? []
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
        title={t('league.new')}
        description={t('league.newHint')}
        label={t('leagueName.full')}
        maxLength={60}
        pending={pending}
        onCreate={(name) => (mode === 'copy' && copyOf === null ? setPicking(true) : onCreate({ name, copyOf: mode === 'copy' ? copyOf : null, copyTeams }))}
      >
        <div className="flex gap-2 pt-2">
          {choice('scratch', t('create.fromScratch'), t('league.fromScratchHint'))}
          {choice('copy', t('league.copyOf'), t('league.copyOfHint'))}
        </div>
        {mode === 'copy' && (
          <div className="space-y-2 pt-1">
            <Button type="button" variant="outline" className="w-full justify-between font-normal" onClick={() => setPicking(true)}>
              <span className="flex min-w-0 items-center gap-2">
                {copyOf !== null && <LeagueImage id={copyOf} size={64} className="size-5 object-contain" />}
                <span className={cn('truncate', copyOf === null && 'text-muted-foreground')}>
                  {copyOf !== null ? (leagues.find((l) => l.id === copyOf)?.name ?? `#${copyOf}`) : t('league.choose')}
                </span>
              </span>
              <ChevronDown className="opacity-50" />
            </Button>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={copyTeams} onCheckedChange={(v) => setCopyTeams(v === true)} />
              {t('league.copyTeams')}
            </label>
          </div>
        )}
      </CreateDialog>
      <RefPickerDialog
        kind="league"
        open={picking}
        onOpenChange={setPicking}
        title={t('league.choose')}
        actionLabel={t('field.pick.choose')}
        onPick={(id) => {
          setCopyOf(id)
          setPicking(false)
        }}
      />
    </>
  )
}
