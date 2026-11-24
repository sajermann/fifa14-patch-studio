import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeftRight, ExternalLink, Megaphone, Plus, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import type { Adboard } from '@/api/types'
import { OriginalBadge, Section } from '@/components/common/detail'
import { PickerDialog } from '@/components/common/PickerDialog'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useToken } from '@/state/queries'

/** A board chosen on a team or league screen but not saved yet: a board id, or 'none' = no board. */
export type PendingAdboard = number | 'none' | null

export const useAdboards = () => {
  const token = useToken()
  return useQuery({ queryKey: ['adboards', token], queryFn: api.adboards, enabled: !!token })
}

/** The shown name of a board: the user's name, or "Game board <n>" for one of the game's. */
export function useAdboardName() {
  const { t } = useI18n()
  return (b: Pick<Adboard, 'id' | 'is_new' | 'name'>) => (b.is_new ? b.name || t('adboards.gameName', { id: b.id }) : t('adboards.gameName', { id: b.id }))
}

/** The board picture (its 16 bands, top to bottom), or an empty box when it has none. */
export function AdboardThumb({ board, width = 48, className }: { board: Pick<Adboard, 'id' | 'picture'> | undefined; width?: number; className?: string }) {
  if (!board || board.picture === null)
    return (
      <span className={cn('inline-flex aspect-[1/2] shrink-0 items-center justify-center rounded bg-muted text-muted-foreground/50', className)} style={{ width }}>
        <Megaphone className="size-1/2" />
      </span>
    )
  return (
    <img
      src={`/api/image/adboard/${board.id}?width=${Math.min(512, width * 2)}&v=${board.picture}`}
      alt=""
      className={cn('aspect-[1/2] shrink-0 rounded border object-cover', className)}
      style={{ width }}
    />
  )
}

/** Where the game itself shows one of its boards: the competitions of its table (named when they are leagues of the
 * database) and, for the default board, everything the table lacks. */
export function useCompetitionsText() {
  const { t } = useI18n()
  return (b: Adboard) => {
    const names = (b.competitions ?? []).map((c) => c.name ?? t('adboards.competition', { id: c.id }))
    if (b.default) names.push(t('adboards.defaultUses'))
    return names.join(', ') || t('adboards.noCompetition')
  }
}

/** The yellow notice of a game board: a new picture changes it in the game's competitions that show it too. */
export function GameBoardWarning({ board, className }: { board: Adboard; className?: string }) {
  const { t } = useI18n()
  const where = useCompetitionsText()
  if (board.is_new) return null
  return (
    <p className={cn('flex items-start gap-1.5 text-sm text-amber-600 dark:text-amber-400', className)}>
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <span>{t(board.edited ? 'adboards.gameEditedWarning' : 'adboards.gameWarning', { where: where(board) })}</span>
    </p>
  )
}

/** The board tab of a team or a league: the board it has (the saved one, or the one chosen and not saved yet) and the
 * buttons to choose another (the user's or the game's) or none. The choice is saved with the rest of the screen. */
export function AdboardChoice({ kind, saved, pending, onPending }: { kind: 'team' | 'league'; saved: number | null; pending: PendingAdboard; onPending: (p: PendingAdboard) => void }) {
  const { t } = useI18n()
  const nameOf = useAdboardName()
  const boards = useAdboards().data?.items ?? []
  const [picking, setPicking] = useState(false)
  const [q, setQ] = useState('')
  const currentId = pending === 'none' ? null : typeof pending === 'number' ? pending : saved
  const current = boards.find((b) => b.id === currentId)
  const choose = (id: number | null) => onPending(id === saved ? null : id === null ? 'none' : id)
  const query = q.trim().toLowerCase()
  const item = (b: Adboard) => ({
    key: b.id,
    icon: <AdboardThumb board={b} width={20} />,
    title: (
      <span className="flex flex-wrap items-center gap-2">
        {nameOf(b)}
        {!b.is_new && <OriginalBadge edited={b.edited} />}
      </span>
    ),
    subtitle: b.is_new
      ? [b.picture === null && t('adboard.noPicture'), b.hidden && t('adboard.hidden')].filter(Boolean).join(' · ') || undefined
      : t('adboards.gameUses', { where: (b.competitions ?? []).length + (b.default ? 1 : 0) }),
  })
  const matches = (b: Adboard) => b.id !== currentId && (nameOf(b).toLowerCase().includes(query) || String(b.id).includes(query))
  return (
    <Section
      title={t('adboard.title')}
      description={t(kind === 'team' ? 'adboard.teamHint' : 'adboard.leagueHint')}
      action={
        <div className="flex flex-wrap gap-2">
          {currentId !== null && (
            <Button variant="ghost" size="sm" onClick={() => choose(null)}>
              <X /> {t('adboard.remove')}
            </Button>
          )}
          <Button size="sm" onClick={() => setPicking(true)}>
            {currentId !== null ? <ArrowLeftRight /> : <Plus />} {t(currentId !== null ? 'adboard.change' : 'adboard.choose')}
          </Button>
        </div>
      }
    >
      {pending !== null && (
        <p className="mb-3 text-xs text-amber-600 dark:text-amber-400">
          {pending === 'none' ? t('adboard.pendingNone') : t('adboard.pending', { name: current ? nameOf(current) : `#${pending}` })}
        </p>
      )}
      {current ? (
        <div className="flex items-start gap-4">
          <AdboardThumb board={current} width={160} />
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Link to={`/adboards/${current.id}`} className="font-medium underline-offset-4 hover:underline">
                {nameOf(current)}
              </Link>
              {!current.is_new && <OriginalBadge edited={current.edited} />}
            </div>
            {current.is_new && current.picture === null && <p className="text-sm text-amber-600 dark:text-amber-400">{t('adboards.noPictureWarning')}</p>}
            {current.hidden && <p className="text-sm text-amber-600 dark:text-amber-400">{t('adboards.hideHint')}</p>}
            {current.edited && <GameBoardWarning board={current} />}
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{t('adboard.none')}</p>
      )}
      <Button variant="link" size="sm" className="mt-2 px-0" asChild>
        <Link to="/adboards">
          <ExternalLink /> {t('adboard.manage')}
        </Link>
      </Button>
      <PickerDialog
        open={picking}
        onOpenChange={(o) => {
          setPicking(o)
          if (!o) setQ('')
        }}
        title={t('adboard.pickTitle')}
        description={t('adboard.pickDescription')}
        placeholder={t('adboards.search')}
        query={q}
        onQuery={setQ}
        groups={[
          { label: t('adboards.groupProject'), items: boards.filter((b) => b.is_new && matches(b)).map(item) },
          { label: t('adboards.groupGame'), items: boards.filter((b) => !b.is_new && matches(b)).map(item) },
        ]}
        empty={t('adboard.pickEmpty')}
        actionLabel={t('field.pick.choose')}
        onPick={(id) => {
          choose(id)
          setPicking(false)
          setQ('')
        }}
      />
    </Section>
  )
}
