import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { AlertTriangle, Check, FolderOpen, LoaderCircle, Pencil, Settings, Undo2, Users, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '@/api/client'
import type { FaceChoice, FaceFill, FacePagePack, FacePart, PackFace, PlayerDetail } from '@/api/types'
import { CreditsLink } from '@/components/common/CreditsLink'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useI18n, type MessageKey } from '@/i18n'
import { facePartLabel } from '@/lib/issues'
import { FilterSelect, Pager, SearchInput } from '@/lib/list'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useStatus, useToken } from '@/state/queries'
import { PlayerPickerDialog } from './NewPlayerDialog'

/** A face being looked at in the 3D preview (not picked yet): a face of a pack, or the real face of a game player
 * (a FIFA 14 particularity: the game's own faces can go to another player). */
export type BrowsedFace = { folder: string; pack: string; face: PackFace } | { player: number; name: string }

type PackChoice = Extract<FaceChoice, { source: 'pack' }>

export const browsedChoice = (b: BrowsedFace): FaceChoice =>
  'player' in b
    ? { source: 'player', player: b.player }
    : {
        source: 'pack',
        pack: b.folder,
        id: b.face.id,
        pack_name: b.pack,
        ...(b.face.name && { name: b.face.name }),
        ...(b.face.credits && { credits: b.face.credits }),
        ...(b.face.credits_url && { credits_url: b.face.credits_url }),
      }

const ALL = 'all'

export const packThumbUrl = (folder: string, id: number) => `/api/facepack/thumb?pack=${encodeURIComponent(folder)}&id=${id}`

// Real faces from FIFA 14 packs, the same picker as the Street Studio's: the packs stay where the user keeps them
// (the folders set in the Settings; the backend reads them in place, pages and searches); clicking a face shows it in
// the 3D preview; "use this face" puts it on the player (its files are copied into the project when he is saved).
// "Browse another folder" shows only the faces of a folder picked here, for this visit. Who the face is and who made
// it come from the pack's manifest.json ("type": "faces"); they can be edited in the project.
export function FacePicker({
  player,
  current,
  browsing,
  onBrowse,
  onPick,
  fillOptions,
  onFill,
  pickedMissing,
  onPickedMissing,
  bald = false,
}: {
  player: PlayerDetail
  /** the face chosen on the screen (saved or not) */
  current: FaceChoice | null
  browsing: BrowsedFace | null
  onBrowse: (face: BrowsedFace | null) => void
  onPick: (face: FaceChoice) => void
  /** the game's generic eyes / hair a face lacking them may be filled in with (/api/player-options) */
  fillOptions?: { eyes: number[]; hair: number[]; hairlod: number[] }
  /** opens the picker of the game's eyes or hair (the Look card shows it in place of this one) */
  onFill: (group: FillGroup) => void
  /** parts the face picked on this visit (not saved yet) does not bring: kept by the Look card, which stays mounted
   * while the pictures of the game's eyes or hair take the place of this picker */
  pickedMissing: FacePart[] | null
  onPickedMissing: (parts: FacePart[] | null) => void
  /** the player's hair code is 0 (no hair): a face without hair lacks nothing there */
  bald?: boolean
}) {
  const { t } = useI18n()
  const token = useToken()
  const folders = useStatus().data?.config.face_pack_dirs ?? []
  // folder picked here for this visit only (e.g. a face just downloaded): only its faces; leaving the screen forgets it
  const [otherDir, setOtherDir] = useState<string | null>(null)
  const [choosing, setChoosing] = useState(false)
  const [search, setSearch] = useState('')
  const [pack, setPack] = useState(ALL)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [editingInfo, setEditingInfo] = useState(false)
  const [pickingPlayer, setPickingPlayer] = useState(false)

  const pageQuery = useQuery({
    queryKey: ['facepack', otherDir ?? folders, search, pack, page, pageSize],
    queryFn: () =>
      api.facePage({
        offset: (page - 1) * pageSize,
        limit: pageSize,
        q: search,
        ...(otherDir ? { folder: otherDir } : { pack: pack === ALL ? undefined : pack }),
      }),
    enabled: !!otherDir || folders.length > 0,
    retry: false,
    placeholderData: keepPreviousData,
  })
  const data = pageQuery.data
  const packs: FacePagePack[] = data?.packs ?? []
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize))

  const showFolder = (folder: string | null) => {
    setOtherDir(folder)
    setPack(ALL)
    setPage(1)
    onBrowse(null)
  }

  const browseOther = async () => {
    setChoosing(true)
    try {
      const { path } = await api.pickFolder(otherDir ?? folders[folders.length - 1] ?? null, t('settings.chooseFaceFolder'))
      if (path) showFolder(path)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('folder.pickFailed'))
    } finally {
      setChoosing(false)
    }
  }

  // once the face is saved, the backend tells what it does not bring again (player.face_missing)
  const pick = () => {
    if (!browsing) return
    onPick(browsedChoice(browsing))
    onPickedMissing('face' in browsing ? (browsing.face.missing ?? []) : null)
    onBrowse(null)
  }

  const chosenPack = current?.source === 'pack' ? current : null
  const savedFace = player.saved.face as FaceChoice | null | undefined
  const sameAsSaved = !!chosenPack && savedFace?.source === 'pack' && savedFace.pack === chosenPack.pack && savedFace.id === chosenPack.id
  const lacking = (parts: FacePart[]) => (bald ? parts.filter((p) => !HAIR_PARTS.includes(p)) : parts)
  const currentMissing = lacking(!chosenPack ? [] : sameAsSaved && player.face_stored ? (player.face_missing ?? []) : (pickedMissing ?? []))
  const browsedMissing = browsing && 'face' in browsing ? lacking(browsing.face.missing ?? []) : []
  const isCurrent = (f: PackFace & { folder: string }) => !!chosenPack && chosenPack.id === f.id && chosenPack.pack === f.folder
  const isBrowsed = (f: PackFace & { folder: string }) => !!browsing && 'folder' in browsing && browsing.folder === f.folder && browsing.face.id === f.id
  const goToSettings = (label: string) => (
    <Button variant="outline" size="sm" asChild>
      <Link to="/settings">
        <Settings /> {label}
      </Link>
    </Button>
  )

  return (
    <div className="flex flex-col gap-3">
      {current && current.source !== 'generic' && (
        <div className="flex items-start gap-3 rounded-md border p-2">
          <img
            src={current.source === 'pack' ? packThumbUrl(current.pack, current.id) : `/api/game-face/thumb/${current.player}?v=${token}`}
            alt=""
            className="size-14 rounded bg-muted object-contain"
          />
          {editingInfo && chosenPack ? (
            <FaceInfoForm
              face={chosenPack}
              onCancel={() => setEditingInfo(false)}
              onSave={(info) => {
                const { name: _n, credits: _c, credits_url: _u, ...rest } = chosenPack
                onPick({ ...rest, ...info })
                setEditingInfo(false)
              }}
            />
          ) : (
            <>
              <div className="min-w-0 flex-1 self-center text-sm">
                {current.source === 'pack' ? (
                  <>
                    <p className="font-medium">
                      {current.name ? `${current.name} · ` : ''}
                      {t('faces.face', { id: current.id })}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {player.face_stored && player.saved.face && JSON.stringify(player.saved.face) === JSON.stringify(current)
                        ? (current.pack_name ?? t('faces.unknownPack'))
                        : t('faces.inProject', { pack: current.pack_name ?? t('faces.unknownPack') })}
                    </p>
                    {(current.credits || current.credits_url) && (
                      <p className="truncate text-xs text-muted-foreground">
                        {t('credits.by', { credits: '' })}
                        <CreditsLink credits={current.credits} url={current.credits_url} />
                      </p>
                    )}
                  </>
                ) : (
                  <p className="font-medium">{t('look.playerFace', { name: `#${current.player}` })}</p>
                )}
              </div>
              {chosenPack && (
                <Button variant="ghost" size="sm" onClick={() => setEditingInfo(true)} title={t('faces.editInfoHint')}>
                  <Pencil /> {t('faces.editInfo')}
                </Button>
              )}
            </>
          )}
        </div>
      )}
      {chosenPack && (!!currentMissing.length || !!chosenPack.fill) && (
        <MissingParts
          parts={currentMissing}
          fill={chosenPack.fill}
          options={fillOptions}
          onFill={onFill}
          onClear={(group) => {
            const { fill, ...rest } = chosenPack
            const next = { ...fill }
            delete next[group]
            onPick(Object.keys(next).length ? { ...rest, fill: next } : rest)
          }}
        />
      )}

      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Button variant="outline" size="sm" onClick={() => void browseOther()} disabled={choosing}>
          {choosing ? <LoaderCircle className="animate-spin" /> : <FolderOpen />} {t('faces.browseOther')}
        </Button>
        <Button variant="outline" size="sm" onClick={() => setPickingPlayer(true)}>
          <Users /> {t('faces.fromPlayer')}
        </Button>
        {otherDir ? (
          <>
            <span className="min-w-0 truncate font-mono" title={otherDir}>
              {otherDir}
            </span>
            <Button variant="ghost" size="sm" onClick={() => showFolder(null)}>
              <Undo2 /> {folders.length ? t('faces.backToDefault') : t('faces.closeFolder')}
            </Button>
          </>
        ) : (
          <span>{t('faces.onlyThisScreen')}</span>
        )}
      </div>

      {!otherDir && !folders.length ? (
        <div className="flex flex-col items-start gap-2 rounded-md border border-dashed p-3 text-sm">
          <p className="text-muted-foreground">{t('faces.setPackFirst')}</p>
          {goToSettings(t('faces.goToSettings'))}
        </div>
      ) : pageQuery.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin" /> {t('faces.opening')}
        </p>
      ) : pageQuery.error ? (
        <div className="flex flex-col items-start gap-2 rounded-md border border-destructive/40 p-3 text-sm">
          <p className="text-destructive">{pageQuery.error instanceof ApiError ? pageQuery.error.message : t('faces.openFailed')}</p>
          {!otherDir && goToSettings(t('faces.checkSettings'))}
        </div>
      ) : null}

      {data && (
        <div className="flex flex-col gap-2">
          <PackProblems packs={packs} />
          <div className="flex flex-wrap items-center gap-2">
            {packs.length > 1 && (
              <FilterSelect
                value={pack}
                onChange={(v) => {
                  setPack(v)
                  setPage(1)
                }}
                className="w-48"
                allLabel={t('faces.allPacks', { count: packs.reduce((n, p) => n + p.count, 0) })}
                options={packs.filter((p) => !p.error).map((p) => ({ value: p.folder, label: t('faces.packOption', { name: p.name, count: p.count }) }))}
              />
            )}
            <SearchInput
              value={search}
              onChange={(v) => {
                setSearch(v.trim())
                setPage(1)
              }}
              placeholder={t('faces.filter')}
              className="min-w-40 flex-1"
            />
            {pageQuery.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
          </div>
          <div className="grid max-h-[26rem] grid-cols-[repeat(auto-fill,minmax(5.5rem,1fr))] gap-1.5 overflow-y-auto rounded-md border bg-muted/30 p-1.5">
            {data.items.map((f) => {
              const selected = isBrowsed(f)
              const choose = () => onBrowse(selected ? null : { folder: f.folder, pack: f.pack, face: f })
              return (
                <div
                  key={`${f.folder}|${f.id}`}
                  role="button"
                  tabIndex={0}
                  onClick={choose}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      choose()
                    }
                  }}
                  className={cn(
                    'relative flex cursor-pointer flex-col items-center rounded-md border bg-background p-1 text-xs hover:border-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                    selected && 'border-primary ring-2 ring-primary/40',
                  )}
                  title={[f.name, t('faces.face', { id: f.id }) + (f.hair ? '' : ` ${t('faces.noHair')}`), f.pack, f.credits && t('credits.by', { credits: f.credits })]
                    .filter(Boolean)
                    .join('\n')}
                >
                  <img
                    src={packThumbUrl(f.folder, f.id)}
                    alt=""
                    loading="lazy"
                    className="aspect-square w-full object-contain"
                    onError={(e) => {
                      e.currentTarget.style.visibility = 'hidden' // a face the app cannot read: no broken image icon
                    }}
                  />
                  <span className="w-full truncate text-center text-[11px] leading-tight">{f.name ?? '—'}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">{f.id}</span>
                  {f.pack.includes('/') && (
                    // one of the versions a pack brings side by side (e.g. "08", "FIFA 14 PC"): same id, other look
                    <span className="w-full truncate text-center text-[10px] text-muted-foreground">{f.pack.split('/').slice(1).join(' / ')}</span>
                  )}
                  {(f.credits || f.credits_url) && (
                    <CreditsLink credits={f.credits} url={f.credits_url} className="max-w-full text-[10px] text-muted-foreground" />
                  )}
                  {isCurrent(f) && <Check className="absolute top-1 left-1 size-3.5 text-primary" />}
                </div>
              )
            })}
            {!data.items.length && <p className="col-span-full p-4 text-center text-xs text-muted-foreground">{t('faces.none')}</p>}
          </div>
          <Pager
            page={Math.min(page, pages)}
            pages={pages}
            total={data.total}
            size={pageSize}
            onPage={(n, size = pageSize) => {
              setPage(n)
              setPageSize(size)
            }}
          />
        </div>
      )}

      {browsing && (
        <div className="flex items-center gap-2 rounded-md border border-primary/40 bg-primary/5 p-2 text-sm">
          <div className="min-w-0 flex-1">
            <p>
              {t('faces.viewing')}{' '}
              <span className="font-medium">
                {'player' in browsing ? browsing.name : browsing.face.name ? `${browsing.face.name} (${browsing.face.id})` : browsing.face.id}
              </span>{' '}
              {t('faces.viewingRest')}
            </p>
            {!!browsedMissing.length && <MissingParts parts={browsedMissing} className="mt-2" />}
          </div>
          <Button size="sm" onClick={pick}>
            <Check /> {t('faces.use')}
          </Button>
          <Button size="icon" variant="ghost" className="size-8" onClick={() => onBrowse(null)} title={t('faces.stopViewing')}>
            <X />
          </Button>
        </div>
      )}
      <PlayerPickerDialog
        open={pickingPlayer}
        onOpenChange={setPickingPlayer}
        withFace
        title={t('look.fromPlayerTitle')}
        description={t('look.fromPlayerDescription')}
        onPick={(p) => {
          onBrowse({ player: p.id, name: p.name })
          setPickingPlayer(false)
        }}
      />
    </div>
  )
}

export type FillGroup = keyof FaceFill

const HAIR_PARTS: FacePart[] = ['hair', 'hair_textures', 'hairlod']

/** parts: what the group puts in (the hair replaces all three files); offeredFor: the missing parts the button
 * shows for; notWith: missing parts that hide it (a face lacking its hair gets the whole hair, not only the one seen
 * from afar: a face lacking only that one keeps its own hair and takes just the generic one from afar). */
const FILL_GROUPS: { key: FillGroup; parts: FacePart[]; offeredFor: FacePart[]; notWith?: FacePart[]; button: MessageKey; chosen: MessageKey }[] = [
  { key: 'eyes', parts: ['eyes'], offeredFor: ['eyes'], button: 'faces.fillEyesButton', chosen: 'faces.fillEyesChosen' },
  { key: 'hair', parts: ['hair', 'hair_textures', 'hairlod'], offeredFor: ['hair', 'hair_textures'], button: 'faces.fillHairButton', chosen: 'faces.fillHairChosen' },
  { key: 'hairlod', parts: ['hairlod'], offeredFor: ['hairlod'], notWith: ['hair', 'hair_textures'], button: 'faces.fillHairlodButton', chosen: 'faces.fillHairlodChosen' },
]

/** The optional parts a face does not bring, one line each (the screen shows it for the face being looked at and for
 * the chosen one, saved or not). For the chosen face it also offers the game's generic eyes and hair for what is
 * missing (the project keeps only their codes; the files are read from the game folder when the patch is built). */
function MissingParts({
  parts,
  fill,
  options,
  onFill,
  onClear,
  className,
}: {
  parts: readonly FacePart[]
  fill?: FaceFill
  options?: { eyes: number[]; hair: number[]; hairlod: number[] }
  onFill?: (group: FillGroup) => void
  onClear?: (group: FillGroup) => void
  className?: string
}) {
  const { t } = useI18n()
  const covered = FILL_GROUPS.filter((g) => fill?.[g.key])
  const left = parts.filter((p) => !covered.some((g) => g.parts.includes(p)))
  const offered =
    onFill && options
      ? FILL_GROUPS.filter(
          (g) => !fill?.[g.key] && g.offeredFor.some((p) => left.includes(p)) && !g.notWith?.some((p) => left.includes(p)) && options[g.key]?.length,
        )
      : []
  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {!!left.length && (
        <div className="flex gap-1.5 text-xs text-amber-700 dark:text-amber-400">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <div className="min-w-0">
            <p className="font-medium">{t('faces.missingTitle')}</p>
            <ul className="list-inside list-disc">
              {left.map((p) => (
                <li key={p}>{facePartLabel(t, p)}</li>
              ))}
            </ul>
            {left.includes('eyes') && <p className="mt-0.5 opacity-80">{t('faces.missingHintEyes')}</p>}
            {left.some((p) => p === 'hair' || p === 'hair_textures') && <p className="mt-0.5 opacity-80">{t('faces.missingHintHair')}</p>}
            {left.includes('hairlod') && !left.some((p) => p === 'hair' || p === 'hair_textures') && (
              <p className="mt-0.5 opacity-80">{t('faces.missingHintHairlod')}</p>
            )}
            {!!offered.length && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {offered.map((g) => (
                  <Button key={g.key} variant="outline" size="sm" onClick={() => onFill?.(g.key)}>
                    {t(g.button)}
                  </Button>
                ))}
              </div>
            )}
            {offered.some((g) => g.key === 'hair') && <p className="mt-1.5 opacity-80">{t('faces.fillHairWarning')}</p>}
          </div>
        </div>
      )}
      {!!covered.length && (
        <div className="flex gap-1.5 rounded-md border p-2 text-xs">
          <Check className="mt-0.5 size-3.5 shrink-0 text-primary" />
          <div className="min-w-0 flex-1">
            <p className="font-medium">{t('faces.fillTitle')}</p>
            <ul className="mt-1 flex flex-col gap-1">
              {covered.map((g) => (
                <li key={g.key} className="flex flex-wrap items-center gap-1.5">
                  <span className="min-w-0 flex-1">{t(g.chosen, { n: (options?.[g.key]?.indexOf(fill?.[g.key] ?? -1) ?? -1) + 1 || fill?.[g.key] || 0 })}</span>
                  {onFill && (
                    <Button variant="ghost" size="sm" onClick={() => onFill(g.key)}>
                      {t('faces.fillChange')}
                    </Button>
                  )}
                  {onClear && (
                    <Button variant="ghost" size="sm" onClick={() => onClear(g.key)}>
                      {t('faces.fillRemove')}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
            {fill?.hair && <p className="mt-1 text-amber-700 dark:text-amber-400">{t('faces.fillHairWarning')}</p>}
            <p className="mt-1 text-muted-foreground">{t('faces.fillGameNote')}</p>
          </div>
        </div>
      )}
    </div>
  )
}

type FaceInfo = Pick<PackChoice, 'name' | 'credits' | 'credits_url'>

const webLink = (url: string) => {
  const text = url.trim()
  const full = /^[a-z][a-z0-9+.-]*:/i.test(text) ? text : `https://${text}`
  try {
    const u = new URL(full)
    return /^https?:$/.test(u.protocol) && u.hostname.includes('.') ? full : null
  } catch {
    return null
  }
}

/** Who the chosen face is and who made it, edited in the project only (the pack and its manifest.json stay as they
 * are). Empty fields are cleared. */
function FaceInfoForm({ face, onSave, onCancel }: { face: PackChoice; onSave: (info: FaceInfo) => void; onCancel: () => void }) {
  const { t } = useI18n()
  const [name, setName] = useState(face.name ?? '')
  const [credits, setCredits] = useState(face.credits ?? '')
  const [link, setLink] = useState(face.credits_url ?? '')
  const url = link.trim() ? webLink(link) : null
  const badLink = !!link.trim() && !url
  const save = () => {
    if (badLink) return
    onSave({
      ...(name.trim() && { name: name.trim() }),
      ...(credits.trim() && { credits: credits.trim() }),
      ...(url && { credits_url: url }),
    })
  }
  return (
    <form
      className="grid min-w-0 flex-1 gap-2 text-sm"
      onSubmit={(e) => {
        e.preventDefault()
        save()
      }}
    >
      <p className="font-medium">{t('faces.face', { id: face.id })}</p>
      <div className="grid gap-1">
        <Label htmlFor="face-info-name">{t('faces.infoName')}</Label>
        <Input id="face-info-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      </div>
      <div className="grid gap-1">
        <Label htmlFor="face-info-credits">{t('faces.infoCredits')}</Label>
        <Input id="face-info-credits" value={credits} onChange={(e) => setCredits(e.target.value)} />
      </div>
      <div className="grid gap-1">
        <Label htmlFor="face-info-link">{t('faces.infoCreditsUrl')}</Label>
        <Input id="face-info-link" value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://" aria-invalid={badLink} className="font-mono" />
        {badLink && <p className="text-xs text-destructive">{t('faces.infoBadLink')}</p>}
      </div>
      <p className="text-xs text-muted-foreground">{t('faces.infoHint')}</p>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" size="sm" disabled={badLink}>
          <Check /> {t('common.apply')}
        </Button>
      </div>
    </form>
  )
}

/** Folders without faces and problems of the packs' manifest.json (the gallery still works). */
export function PackProblems({ packs }: { packs: FacePagePack[] }) {
  const { t } = useI18n()
  const lines = packs.flatMap((p) =>
    p.error
      ? [t('faces.packMissing', { folder: p.folder })]
      : p.warnings.map((w) => t('faces.manifestWarning', { pack: p.name, problem: t(`faces.warning.${w.code}` as MessageKey, { count: w.count ?? 0 }) })),
  )
  if (!lines.length) return null
  return (
    <div className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs text-amber-700 dark:text-amber-400">
      <AlertTriangle className="size-3.5 shrink-0" />
      <ul className="min-w-0 space-y-0.5">
        {lines.map((line, i) => (
          <li key={i} className="break-words">
            {line}
          </li>
        ))}
      </ul>
    </div>
  )
}
