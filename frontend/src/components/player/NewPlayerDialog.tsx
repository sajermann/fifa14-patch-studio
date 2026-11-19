import { useQuery } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api/client'
import type { PlayerRow } from '@/api/types'
import { CreateDialog } from '@/components/common/create'
import { PickerDialog, type PickerItem } from '@/components/common/PickerDialog'
import { Photo } from '@/components/common/pictures'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useToken } from '@/state/queries'

/** Dialog: search the players of the game and the project and pick one (`withFace` = only the ones with a real face
 * in the game). */
export function PlayerPickerDialog({
  open,
  onOpenChange,
  title,
  description,
  onPick,
  exclude = [],
  withFace = false,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  description: string
  onPick: (player: PlayerRow) => void
  exclude?: number[]
  withFace?: boolean
}) {
  const { t } = useI18n()
  const token = useToken()
  const [q, setQ] = useState('')
  const { data } = useQuery({
    queryKey: ['players', token, 'picker', q, withFace],
    queryFn: () => api.players({ q, size: 50, sort: 'overall', face: withFace ? 'yes' : undefined }),
    enabled: open && !!token,
    placeholderData: (previous) => previous,
  })
  const items = (data?.items ?? []).filter((p) => !exclude.includes(p.id))
  const toItem = (p: PlayerRow): PickerItem<number> => ({
    key: p.id,
    icon: withFace ? (
      <img src={`/api/game-face/thumb/${p.id}?v=${token}`} alt="" loading="lazy" className="size-10 object-contain" />
    ) : (
      <Photo id={p.id} size={64} available={p.has_photo} className="size-8" />
    ),
    title: p.name,
    subtitle: [p.position_name, p.overall, p.team, `ID ${p.id}`].filter((v) => v !== null && v !== undefined && v !== '').join(' · '),
  })
  return (
    <PickerDialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      placeholder={t('players.search')}
      query={q}
      onQuery={setQ}
      groups={[
        { label: t('players.newPlayers'), items: items.filter((p) => p.is_new).map(toItem) },
        { label: t('players.originalPlayers'), items: items.filter((p) => !p.is_new).map(toItem) },
      ]}
      empty={t('field.pick.empty')}
      actionLabel={t('field.pick.choose')}
      onPick={(id) => {
        const p = items.find((x) => x.id === id)
        if (p) onPick(p)
      }}
    />
  )
}

export interface NewPlayer {
  name: string
  copyOf: number | null
}

/** "New player": from scratch (a plain player of the game, generic head) or a copy of a player (his values, face
 * and photo). The name typed becomes first + last name (one word: the known name). */
export function NewPlayerDialog({ open, onOpenChange, pending, onCreate }: { open: boolean; onOpenChange: (o: boolean) => void; pending: boolean; onCreate: (p: NewPlayer) => void }) {
  const { t } = useI18n()
  const [mode, setMode] = useState<'scratch' | 'copy'>('scratch')
  const [copyOf, setCopyOf] = useState<PlayerRow | null>(null)
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
        title={t('player.newTitle')}
        description={t('player.newDescription')}
        label={t('player.newName')}
        maxLength={80}
        pending={pending}
        onCreate={(name) => (mode === 'copy' && !copyOf ? setPicking(true) : onCreate({ name, copyOf: mode === 'copy' ? (copyOf?.id ?? null) : null }))}
      >
        <div className="flex gap-2 pt-2">
          {choice('scratch', t('player.fromScratch'), t('player.fromScratchHint'))}
          {choice('copy', t('player.copyOf'), t('player.copyOfHint'))}
        </div>
        {mode === 'copy' && (
          <Button type="button" variant="outline" className="w-full justify-between font-normal" onClick={() => setPicking(true)}>
            <span className="flex min-w-0 items-center gap-2">
              {copyOf && <Photo id={copyOf.id} size={64} available={copyOf.has_photo} className="size-5" />}
              <span className={cn('truncate', !copyOf && 'text-muted-foreground')}>{copyOf?.name ?? t('player.choosePlayer')}</span>
            </span>
            <ChevronDown className="opacity-50" />
          </Button>
        )}
      </CreateDialog>
      <PlayerPickerDialog
        open={picking}
        onOpenChange={setPicking}
        title={t('player.choosePlayer')}
        description={t('player.copyOfHint')}
        onPick={(p) => {
          setCopyOf(p)
          setPicking(false)
        }}
      />
    </>
  )
}

/** The fields of a typed name: "First Last…" → first + last; one word → the known name. */
export function nameFields(name: string): Record<string, string> {
  const words = name.trim().split(/\s+/)
  if (words.length < 2) return { 'name.common': words[0] ?? '' }
  return { 'name.first': words[0], 'name.last': words.slice(1).join(' ') }
}
