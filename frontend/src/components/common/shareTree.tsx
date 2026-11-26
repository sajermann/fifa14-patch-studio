import { Building2, Check, ChevronDown, ChevronRight, CircleDot, Footprints, Hand, Megaphone, Minus, Volleyball } from 'lucide-react'
import { useMemo, useState } from 'react'
import { sharePictureUrl } from '@/api/client'
import type { ShareKind, ShareNode, ShareTree } from '@/api/types'
import { Badge } from '@/components/common/detail'
import { CountryFlag, Crest, LeagueImage, Photo } from '@/components/common/pictures'
import { useI18n, type MessageKey } from '@/i18n'
import { cn } from '@/lib/utils'

// The selection tree of the import page and of the export dialog: the same rows, marks and kind badges as the
// extractor's export tree (fifa-patch-extractor, components/common/selectionTree.tsx), with the choice kept here.

export type TreeState = 'full' | 'part' | 'only' | 'none'

/** The kind badge in front of each row: its label and color (same color for the same kind of thing). */
const KIND_BADGE: Record<ShareKind, [MessageKey, string]> = {
  country: ['tree.kind.country', 'bg-sky-500/15 text-sky-700 dark:text-sky-300'],
  league: ['tree.kind.league', 'bg-violet-500/15 text-violet-700 dark:text-violet-300'],
  team: ['tree.kind.team', 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'],
  player: ['tree.kind.player', 'bg-amber-500/15 text-amber-700 dark:text-amber-300'],
  stadium: ['tree.kind.stadium', 'bg-orange-500/15 text-orange-700 dark:text-orange-300'],
  ball: ['tree.kind.ball', 'bg-rose-500/15 text-rose-700 dark:text-rose-300'],
  adboard: ['tree.kind.adboard', 'bg-cyan-500/15 text-cyan-700 dark:text-cyan-300'],
  boot: ['tree.kind.boot', 'bg-lime-500/15 text-lime-700 dark:text-lime-300'],
  glove: ['tree.kind.glove', 'bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300'],
}

function KindBadge({ kind }: { kind: ShareKind }) {
  const { t } = useI18n()
  const [label, color] = KIND_BADGE[kind]
  return <span className={cn('inline-flex w-16 shrink-0 justify-center rounded px-1.5 py-0.5 text-[11px] font-medium', color)}>{t(label)}</span>
}

/** The tree's checkbox: ✓ it and everything inside, – some of it, • it alone. */
export function TreeBox({ state, onClick, disabled, label }: { state: TreeState; onClick: () => void; disabled?: boolean; label: string }) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={state === 'full' ? true : state === 'none' ? false : 'mixed'}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      className={cn(
        'flex size-4 shrink-0 items-center justify-center rounded-[4px] border border-input outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50 dark:bg-input/30 [&>svg]:size-3.5',
        state === 'full' && 'border-primary bg-primary text-primary-foreground dark:bg-primary',
        (state === 'part' || state === 'only') && 'border-primary bg-primary/15 text-primary',
      )}
    >
      {state === 'full' && <Check />}
      {state === 'part' && <Minus />}
      {state === 'only' && <span className="size-1.5 rounded-full bg-current" />}
    </button>
  )
}

/** The legend of the three marks. */
export function TreeLegend() {
  const { t } = useI18n()
  const item = (state: TreeState, text: string) => (
    <span className="flex items-center gap-1.5">
      <span className="pointer-events-none">
        <TreeBox state={state} onClick={() => {}} label={text} />
      </span>
      {text}
    </span>
  )
  return (
    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
      {item('full', t('tree.legendFull'))}
      {item('part', t('tree.legendPart'))}
      {item('only', t('tree.legendOnly'))}
    </div>
  )
}

// ---------------------------------------------------------------- the choice

/** Every key below `key` (each once, even when an item is under two parents). */
function below(tree: ShareTree, key: string): string[] {
  const out = new Set<string>()
  const walk = (k: string) => {
    for (const c of tree.nodes[k]?.children ?? []) {
      if (out.has(c) || c === key) continue
      out.add(c)
      walk(c)
    }
  }
  walk(key)
  return [...out]
}

const usable = (n: ShareNode | undefined) => !!n && !n.error

/** The picked items of a tree and the clicks that change them. `initial`: the keys picked at first. */
export function useTreeChoice(tree: ShareTree | null, initial: (n: ShareNode) => boolean) {
  const [picked, setPicked] = useState<Set<string>>(() => new Set(tree ? Object.values(tree.nodes).filter((n) => usable(n) && initial(n)).map((n) => n.key) : []))
  const [forToken, setForToken] = useState(tree?.token)
  if (tree && forToken !== tree.token) {
    // a new tree (another zip): its own first choice
    setForToken(tree.token)
    setPicked(new Set(Object.values(tree.nodes).filter((n) => usable(n) && initial(n)).map((n) => n.key)))
  }
  const insideOf = useMemo(() => {
    const out: Record<string, string[]> = {}
    if (tree) for (const k of Object.keys(tree.nodes)) out[k] = below(tree, k).filter((c) => usable(tree.nodes[c]))
    return out
  }, [tree])
  const state = (key: string): TreeState => {
    const own = picked.has(key)
    const inside = insideOf[key] ?? []
    if (!inside.length) return own ? 'full' : 'none'
    const on = inside.filter((k) => picked.has(k)).length
    if (own && on === inside.length) return 'full'
    if (own && on === 0) return 'only'
    return own || on > 0 ? 'part' : 'none'
  }
  const change = (keys: string[], on: boolean) =>
    setPicked((prev) => {
      const next = new Set(prev)
      for (const k of keys) if (on) next.add(k)
      else next.delete(k)
      return next
    })
  return {
    picked,
    state,
    count: (key: string) => {
      const inside = insideOf[key] ?? []
      return { on: inside.filter((k) => picked.has(k)).length, total: inside.length }
    },
    /** ✓ = it and everything inside; a click on a full one takes it all out. A country the game already has
     * (a package's): only what is inside, the country itself stays the game's unless asked for (`self`) */
    toggle: (key: string) => {
      const inside = insideOf[key] ?? []
      if (tree?.nodes[key]?.game_has) change(inside, !inside.every((k) => picked.has(k)))
      else change([key, ...inside], state(key) !== 'full')
    },
    /** the item itself, in or out (nothing inside changes) */
    self: (key: string) => change([key], !picked.has(key)),
    /** it alone (nothing inside) */
    only: (key: string) => {
      change(insideOf[key] ?? [], false)
      change([key], true)
    },
    setAll: (on: boolean) => tree && change(Object.values(tree.nodes).filter((n) => usable(n) && !n.game_has).map((n) => n.key), on),
  }
}

export type TreeChoice = ReturnType<typeof useTreeChoice>

// ---------------------------------------------------------------- the rows

const ICONS: Partial<Record<ShareKind, typeof Building2>> = { stadium: Building2, adboard: Megaphone, boot: Footprints, glove: Hand, ball: Volleyball }

/** `live`: the items are in the project (an export): the app's own picture of each, as its screens show it. */
function NodePicture({ token, n, live }: { token: string; n: ShareNode; live: boolean }) {
  const box = 'size-6 shrink-0 object-contain'
  if (n.picture && !(live && (n.kind === 'team' || n.kind === 'country' || n.kind === 'league')))
    return <img src={sharePictureUrl(token, n.key)} alt="" className={cn(box, n.kind === 'player' && 'rounded-full')} loading="lazy" />
  if ((live || !n.created) && n.id >= 0) {
    // in the project, or one of the game's items changed without a picture of its own: the app's picture
    if (n.kind === 'country') return <CountryFlag id={n.id} size={32} className="h-4 w-6 shrink-0" />
    if (n.kind === 'league') return <LeagueImage id={n.id} size={32} className={box} />
    if (n.kind === 'team') return <Crest id={n.id} size={32} className={box} />
    if (n.kind === 'player') return <Photo id={n.id} size={32} className={cn(box, 'rounded-full')} />
  }
  const Icon = ICONS[n.kind] ?? CircleDot
  return <Icon className="size-4 shrink-0 text-muted-foreground" />
}

/** What happens to the item's id (import): kept, a new one (taken, or out of the range the app uses), or it replaces
 * the changes the project already has. */
function IdNote({ n, picked }: { n: ShareNode; picked: boolean }) {
  const { t } = useI18n()
  if (n.error) return <Badge tone="warn">{t(`share.error.${n.error}`)}</Badge>
  // left out, the game's own is used: no new id to warn about (ticked, it comes in as a new country)
  if (n.game_has && !picked) return <span className="shrink-0 text-xs text-muted-foreground">{t('share.gameHas')}</span>
  if (n.reason === 'taken') return <Badge tone="warn">{t('share.idTaken', { id: n.id, newId: n.new_id ?? '' })}</Badge>
  if (n.reason === 'range') return <span className="shrink-0 text-xs text-muted-foreground">{t('share.idNew', { newId: n.new_id ?? '' })}</span>
  if (n.reason === 'replaces') return <Badge tone="warn">{t('share.replaces')}</Badge>
  return null
}

function TreeRow({ tree, choice, nodeKey, depth, ids, open: startOpen, path }: { tree: ShareTree; choice: TreeChoice; nodeKey: string; depth: number; ids: boolean; open: boolean; path: string[] }) {
  const { t } = useI18n()
  const n = tree.nodes[nodeKey]
  const kids = n.children.filter((c) => !path.includes(c))
  const [open, setOpen] = useState(startOpen)
  const state = choice.state(n.key)
  const count = kids.length ? choice.count(n.key) : null
  return (
    <>
      <div className="flex min-h-9 items-center gap-2 border-b py-1 pr-3 hover:bg-muted/50" style={{ paddingLeft: 8 + depth * 22 }}>
        {kids.length ? (
          <button
            type="button"
            className="flex size-5 shrink-0 items-center justify-center rounded text-muted-foreground hover:bg-muted"
            aria-label={open ? t('tree.close') : t('tree.open')}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          </button>
        ) : (
          <span className="w-5 shrink-0" />
        )}
        <TreeBox state={state} disabled={!!n.error} onClick={() => choice.toggle(n.key)} label={state === 'full' ? t('tree.remove') : t('tree.add')} />
        <KindBadge kind={n.kind} />
        <NodePicture token={tree.token} n={n} live={!ids} />
        <button type="button" className="min-w-0 truncate text-left text-sm" onClick={() => kids.length && setOpen(!open)}>
          {n.name ?? `#${n.id}`}
        </button>
        {n.id >= 0 && <span className="shrink-0 text-xs text-muted-foreground tabular-nums">ID {n.id}</span>}
        {!n.created && <Badge>{t('share.gameItem')}</Badge>}
        {ids && <IdNote n={n} picked={choice.picked.has(n.key)} />}
        {ids && n.game_has && (choice.picked.has(n.key) || n.new_id != null) && (
          <button type="button" className="shrink-0 text-xs text-primary hover:underline" onClick={() => choice.self(n.key)}>
            {choice.picked.has(n.key) ? t('share.useGames') : t('share.comeInAsNew')}
          </button>
        )}
        <span className="ml-auto" />
        {state === 'only' && <Badge>{t('tree.alone')}</Badge>}
        {count && count.total > 0 && (
          <span className="text-xs text-muted-foreground tabular-nums" title={t('tree.insideHint')}>
            {t('tree.inside', { on: count.on, total: count.total })}
          </span>
        )}
        {count && count.total > 0 && !n.error && !n.game_has && (
          <button type="button" className="shrink-0 text-xs text-primary hover:underline" onClick={() => (state === 'only' ? choice.toggle(n.key) : choice.only(n.key))}>
            {state === 'only' ? t('tree.everything') : t('tree.onlyIt')}
          </button>
        )}
      </div>
      {open && kids.map((c) => <TreeRow key={c} tree={tree} choice={choice} nodeKey={c} depth={depth + 1} ids={ids} open={false} path={[...path, n.key]} />)}
    </>
  )
}

/** The whole tree (`ids`: show what happens to each item's id, on the import page). */
export function ShareTreeView({ tree, choice, ids = false }: { tree: ShareTree; choice: TreeChoice; ids?: boolean }) {
  return (
    <div className="overflow-hidden rounded-md border">
      {tree.roots.map((k) => (
        <TreeRow key={k} tree={tree} choice={choice} nodeKey={k} depth={0} ids={ids} open={tree.roots.length === 1} path={[]} />
      ))}
    </div>
  )
}
