import { useQuery } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api/client'
import type { TeamRow } from '@/api/types'
import { CreateDialog } from '@/components/common/create'
import { PickerDialog, type PickerItem } from '@/components/common/PickerDialog'
import { Crest } from '@/components/common/pictures'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useToken } from '@/state/queries'

export interface NewTeam {
  name: string
  copyOf: number | null
  copySquad: boolean
}

/** Dialog: search the teams of the game and the project (the Add dialog), picking one. */
export function TeamPickerDialog({ open, onOpenChange, title, description, onPick, exclude = [] }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; description: string; onPick: (team: TeamRow) => void; exclude?: number[] }) {
  const { t } = useI18n()
  const token = useToken()
  const [q, setQ] = useState('')
  const { data } = useQuery({
    queryKey: ['teams', token, 'picker', q],
    queryFn: () => api.teams({ q, size: 50, sort: 'name' }),
    enabled: open && !!token,
    placeholderData: (previous) => previous,
  })
  const items = (data?.items ?? []).filter((r) => !exclude.includes(r.id))
  const toItem = (r: TeamRow): PickerItem<number> => ({
    key: r.id,
    icon: <Crest id={r.id} size={64} available={r.has_crest} version={r.own_crest} className="size-8" />,
    title: r.name,
    subtitle: [r.league, `ID ${r.id}`].filter(Boolean).join(' · '),
  })
  return (
    <PickerDialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      placeholder={t('teams.search')}
      query={q}
      onQuery={setQ}
      groups={[
        { label: t('teams.newTeams'), items: items.filter((r) => r.is_new).map(toItem) },
        { label: t('teams.originalTeams'), items: items.filter((r) => !r.is_new).map(toItem) },
      ]}
      empty={t('field.pick.empty')}
      actionLabel={t('field.pick.choose')}
      onPick={(id) => {
        const team = items.find((r) => r.id === id)
        if (team) onPick(team)
      }}
    />
  )
}

/** "New team": from scratch (blank, like a stadium from scratch: its data, formation, stadium and squad are set on its
 * screen, and it stays out of the patch until they are) or a copy of a team (its crest, kits and formation, and its
 * squad when asked). */
export function NewTeamDialog({ open, onOpenChange, pending, onCreate }: { open: boolean; onOpenChange: (o: boolean) => void; pending: boolean; onCreate: (team: NewTeam) => void }) {
  const { t } = useI18n()
  const [mode, setMode] = useState<'scratch' | 'copy'>('scratch')
  const [copyOf, setCopyOf] = useState<TeamRow | null>(null)
  const [copySquad, setCopySquad] = useState(true)
  const [picking, setPicking] = useState(false)
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
        title={t('team.newTitle')}
        description={t('team.newDescription')}
        label={t('team.newName')}
        maxLength={30}
        pending={pending}
        onCreate={(name) => (mode === 'copy' && !copyOf ? setPicking(true) : onCreate({ name, copyOf: mode === 'copy' ? (copyOf?.id ?? null) : null, copySquad }))}
      >
        <div className="flex gap-2 pt-2">
          {choice('scratch', t('team.fromScratch'), t('team.fromScratchHint'))}
          {choice('copy', t('team.copyOf'), t('team.copyOfHint'))}
        </div>
        {mode === 'copy' && (
          <div className="space-y-2 pt-1">
            <Button type="button" variant="outline" className="w-full justify-between font-normal" onClick={() => setPicking(true)}>
              <span className="flex min-w-0 items-center gap-2">
                {copyOf && <Crest id={copyOf.id} size={64} available={copyOf.has_crest} className="size-5" />}
                <span className={cn('truncate', !copyOf && 'text-muted-foreground')}>{copyOf?.name ?? t('team.chooseTeam')}</span>
              </span>
              <ChevronDown className="opacity-50" />
            </Button>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={copySquad} onCheckedChange={(v) => setCopySquad(v === true)} />
              {t('team.copySquad')}
            </label>
          </div>
        )}
      </CreateDialog>
      <TeamPickerDialog
        open={picking}
        onOpenChange={setPicking}
        title={t('team.chooseTeam')}
        description={t('team.copyOfHint')}
        onPick={(team) => {
          setCopyOf(team)
          setPicking(false)
        }}
      />
    </>
  )
}
