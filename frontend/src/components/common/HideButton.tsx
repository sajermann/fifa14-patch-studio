import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Eye, EyeOff, Lock } from 'lucide-react'
import { api } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useI18n } from '@/i18n'
import { toast } from '@/lib/notify'

/** Show / hide toggle for table rows (the row itself is a link, so the click does not reach it) and edit pages.
 * Same rule as the Street Studio: a created item hidden is out of the patch; an original one is hidden by the
 * project (the patch hides it in the game). */
export function HideButton({
  hidden,
  onToggle,
  hideHint,
  showHint,
  variant = 'ghost',
  disabled = false,
}: {
  hidden: boolean
  onToggle: () => void
  hideHint: string
  showHint: string
  variant?: 'ghost' | 'outline'
  disabled?: boolean
}) {
  const { t } = useI18n()
  return (
    <Button
      variant={variant}
      size="sm"
      className="min-w-24 justify-start" // same width for "hide" and "show": the columns do not move
      title={hidden ? showHint : hideHint}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation()
        onToggle()
      }}
    >
      {hidden ? <Eye /> : <EyeOff />} {hidden ? t('list.show') : t('list.hide')}
    </Button>
  )
}

/** "Not in the patch" badge (always red, like the one in the title of the edit pages). `alert`: in a title, where the
 * gap comes from the row; without it (in a table cell) it keeps a margin from the name. */
export function OutOfPatchBadge({ label, alert = false }: { label?: string; alert?: boolean }) {
  const { t } = useI18n()
  return (
    <Badge variant="destructive" className={alert ? 'font-normal' : 'ml-2 font-normal'}>
      {label ?? t('list.outOfPatch')}
    </Badge>
  )
}

/** "Hidden by the project" badge of a hidden original item (in lists): out of the patch, so red too. */
export function HiddenByProjectBadge({ label }: { label: string }) {
  return (
    <Badge variant="destructive" className="ml-2 font-normal">
      {label}
    </Badge>
  )
}

/** Country or league the game itself hides (in its code or with a country it never lists): unlike "hidden by the
 * project" there is no button to show it. */
export function GameHiddenBadge({ country = false }: { country?: boolean }) {
  const { t } = useI18n()
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="secondary" className="ml-1 gap-1 font-normal text-amber-700 dark:text-amber-400">
          <Lock className="size-3" /> {country ? t('list.countryHiddenInGame') : t('list.hiddenInGame')}
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{country ? t('list.countryHiddenInGameHint') : t('list.hiddenInGameHint')}</TooltipContent>
    </Tooltip>
  )
}

type HideKind = 'country' | 'league' | 'team'
const SETTERS: Record<HideKind, (id: number, hidden: boolean) => Promise<{ hidden: boolean }>> = {
  country: api.setCountryHidden,
  league: api.setLeagueHidden,
  team: api.setTeamHidden,
}

/** Saves the Hide button at once (list rows). */
export function useHide(kind: HideKind, invalidate: string[]) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, hidden }: { id: number; hidden: boolean }) => SETTERS[kind](id, hidden),
    onSuccess: () => {
      for (const k of [...invalidate, 'status']) void qc.invalidateQueries({ queryKey: [k] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

/** The Hide button of an edit page: a change of the form like any other (Save sends it, Discard drops it).
 * `pending` = the value chosen and not saved yet (null = unchanged). */
export function usePendingHide(saved: boolean | undefined) {
  const [pending, setPending] = useState<boolean | null>(null)
  const hidden = pending ?? !!saved
  return {
    hidden,
    pending,
    toggle: () => setPending(!hidden === !!saved ? null : !hidden),
    clear: () => setPending(null),
  }
}
