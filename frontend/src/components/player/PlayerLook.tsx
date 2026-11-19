import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Dices, Eraser, LoaderCircle, User } from 'lucide-react'
import { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import type { PlayerTeamBody } from '@/api/client'
import { api } from '@/api/client'
import type { FaceChoice, FieldValue, PlayerDetail, PlayerOptions } from '@/api/types'
import { ThumbnailField, ThumbnailPicker } from '@/components/common/AppearanceThumbnails'
import { Stepper } from '@/components/common/form'
import { useFieldLabel } from '@/components/common/edit'
import type { PreviewKit, View } from '@/components/team/KitPreview'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useI18n, type MessageKey } from '@/i18n'
import { cn } from '@/lib/utils'
import { useToken } from '@/state/queries'
import { FacePicker, browsedChoice, type BrowsedFace } from './FacePicker'
import type { PendingPhoto } from './PlayerPhoto'

const KitPreview = lazy(() => import('@/components/team/KitPreview')) // three.js only loads on this tab

// the Visual card's groups (the Street Studio's Face and Body; FIFA 14 has more kit codes: their own group)
const FACE_CODES = ['headtypecode', 'hairtypecode', 'haircolorcode', 'facialhairtypecode', 'facialhaircolorcode', 'eyebrowcode', 'sideburnscode', 'eyecolorcode', 'skintypecode', 'skintonecode']
const BODY_CODES = ['bodytypecode']
const KIT_CODES = ['jerseysleevelengthcode', 'socklengthcode', 'jerseystylecode', 'jerseyfit', 'shortstyle', 'hasseasonaljersey']
// codes that still matter with a real face: the hair color, the body skin, the body and the kit
const FACE_MODE_CODES = ['haircolorcode', 'skintonecode', ...BODY_CODES, ...KIT_CODES]
const FACE_MODE_LABELS: Record<string, MessageKey> = { haircolorcode: 'playerEdit.faceHairColor', skintonecode: 'playerEdit.faceSkinTone' }
const RANDOM = ['headtypecode', 'hairtypecode', 'haircolorcode', 'skintonecode', 'facialhairtypecode', 'eyecolorcode']
const LOOK_MIN_HEIGHT = 360
const LOOK_BOTTOM_GAP = 16

type Fields = Record<string, FieldValue>

/** Height that takes an element from where it starts to the end of the viewport (a small gap below it). */
function useHeightToViewportEnd() {
  const ref = useRef<HTMLDivElement>(null)
  const [height, setHeight] = useState<number>()
  useLayoutEffect(() => {
    const measure = () => {
      if (ref.current) setHeight(Math.max(LOOK_MIN_HEIGHT, window.innerHeight - ref.current.getBoundingClientRect().top - LOOK_BOTTOM_GAP))
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])
  return { ref, height }
}

/** The Visual tab, the Street Studio's: the look card on the left (its own scroll; a code with pictures opens them in
 * its place), the 3D preview of the player in his team's kit in the middle (the screen's values, saved or not, and
 * the face or picture being looked at) and his photo on the right. */
export function PlayerLook({
  player,
  fields,
  setField,
  options,
  teams,
  pendingPhoto,
}: {
  player: PlayerDetail
  fields: Fields
  setField: (name: string, value: FieldValue) => void
  options: PlayerOptions | undefined
  teams: PlayerTeamBody[]
  pendingPhoto: PendingPhoto
}) {
  const { t } = useI18n()
  const { label, option } = useFieldLabel()
  const named = (code: string) => (codes[code] ?? []).some((v) => option(code, v) !== String(v)) ? (v: number) => option(code, v) : undefined
  const token = useToken()
  const codes = options?.codes ?? {}
  const thumbs = options?.thumbs ?? []
  const face = (fields.face ?? null) as FaceChoice | null
  const savedGeneric = face?.source === 'generic' || (face === null && !player.game_face)
  // the toggle: a created player can go to "real face" before a face is chosen (he stays generic until then)
  const [realMode, setRealMode] = useState(!savedGeneric)
  useEffect(() => setRealMode(!savedGeneric), [savedGeneric, player.id])
  const generic = !realMode
  // the pictures of a code in place of this card: the clicked one shows in the preview until Apply or Cancel
  const [picking, setPicking] = useState<{ code: string; start: number | undefined; value: number | undefined } | null>(null)
  const [browsing, setBrowsing] = useState<BrowsedFace | null>(null)
  useEffect(() => {
    setPicking(null)
    setBrowsing(null)
  }, [player.id])
  // touching a face option shows the Face view, a body option the Body view
  const [viewRequest, setViewRequest] = useState<{ view: View; seq: number }>()
  const showView = (view: View) => setViewRequest((r) => ({ view, seq: (r?.seq ?? 0) + 1 }))
  const isBodyCode = (code: string) => BODY_CODES.includes(code) || KIT_CODES.includes(code) || (!generic && code === 'skintonecode')
  const viewOf = (code: string): View => (isBodyCode(code) ? 'body' : 'face')
  const effective: Fields = { ...player.values, ...fields, ...(picking?.value !== undefined && { [picking.code]: picking.value }) }
  const own = (code: string) => (typeof fields[code] === 'number' ? (fields[code] as number) : undefined)
  const inheritedCode = (code: string) => (typeof player.values[code] === 'number' ? (player.values[code] as number) : undefined)
  const numberOf = (code: string) => (typeof effective[code] === 'number' ? (effective[code] as number) : 0)
  const set = (code: string, value: number | undefined) => {
    showView(viewOf(code))
    setField(code, value ?? null)
  }
  const thumbnailVariant = (code: string) =>
    code === 'hairtypecode' ? numberOf('haircolorcode') : code === 'facialhairtypecode' || code === 'eyebrowcode' ? numberOf('facialhaircolorcode') : 0
  const openPicker = (code: string) => {
    showView(viewOf(code))
    const start = own(code) ?? inheritedCode(code)
    setPicking({ code, start, value: start })
  }
  const applyPick = () => {
    if (!picking) return
    set(picking.code, picking.value)
    setPicking(null)
  }
  const fieldLabel = (code: string) => (!generic && FACE_MODE_LABELS[code] ? t(FACE_MODE_LABELS[code]) : label(code))
  const randomize = () => {
    showView('face')
    for (const code of RANDOM) {
      const list = codes[code] ?? []
      if (list.length) setField(code, list[Math.floor(Math.random() * list.length)])
    }
  }
  const switchMode = (toGeneric: boolean) => {
    setRealMode(!toGeneric)
    setBrowsing(null)
    if (toGeneric) setField('face', { source: 'generic' })
    else if (face?.source === 'generic') setField('face', null) // the player's own face (a created one: none yet)
  }

  // the preview: the screen's values, with the face being looked at
  const shownFace = browsing ? browsedChoice(browsing) : generic ? { source: 'generic' as const } : face
  const lookCodes = [...FACE_CODES, ...BODY_CODES, ...KIT_CODES, 'height', 'preferredposition1']
  const lookValues = Object.fromEntries(lookCodes.filter((k) => effective[k] !== undefined).map((k) => [k, effective[k]]))
  const look = useQuery({
    queryKey: ['player-look', token, player.id, lookValues, shownFace],
    queryFn: () => api.playerLook(player.id, lookValues, shownFace),
    enabled: !!token,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  }).data
  // the kit of his first team in the patch (the goalkeeper's for a goalkeeper)
  const team = teams.find((r) => !r.hidden) ?? teams[0]
  const teamName = player.teams.find((tm) => tm.id === team?.team)?.name
  const keeper = effective.preferredposition1 === 0
  const kind = keeper ? 2 : 0
  const backName = String(effective['name.jersey'] || effective['name.last'] || effective['name.common'] || player.names.jersey_name || '')
  const v = `v=${token}`
  const print = (part: string) =>
    team ? `/api/preview/kit-print/${team.team}/${kind}.png?part=${part}&number=${team.jersey ?? (keeper ? 1 : 10)}&name=${encodeURIComponent(backName)}&${v}` : null
  const kit: PreviewKit = {
    jersey: team ? `/api/image/kit/${team.team}/${kind}?part=jersey&${v}` : null,
    shorts: team ? `/api/image/kit/${team.team}/${kind}?part=shorts&${v}` : null,
    jerseyPrint: print('jersey'),
    shortsPrint: print('shorts'),
    collar: 0,
    goalkeeper: keeper,
  }
  const photoUrl = pendingPhoto && pendingPhoto !== 'remove' ? pendingPhoto.url : player.has_photo && pendingPhoto !== 'remove' ? `/api/image/photo/${player.id}?size=256&own=${player.own_photo ?? 0}&${v}` : null
  const lookCard = useHeightToViewportEnd()
  const groups = [
    { title: t('playerEdit.lookGroupFace'), codes: FACE_CODES.filter((c) => !isBodyCode(c)) },
    { title: t('playerEdit.lookGroupBody'), codes: [...(generic ? [] : ['skintonecode']), ...BODY_CODES] },
    { title: t('playerEdit.lookGroupKit'), codes: KIT_CODES },
  ]
  const gameHead = player.game_face

  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
      <div
        ref={lookCard.ref}
        style={{ '--look-height': `${lookCard.height}px` } as CSSProperties}
        className="order-3 w-[420px] max-w-full xl:order-1 xl:h-(--look-height) xl:shrink-0"
      >
        <Card className="h-full">
          {picking ? (
            <ThumbnailPicker
              key={picking.code}
              code={picking.code}
              title={fieldLabel(picking.code)}
              options={codes[picking.code] ?? []}
              value={picking.value}
              variant={thumbnailVariant(picking.code)}
              changed={picking.value !== picking.start}
              onSelect={(value) => setPicking({ ...picking, value })}
              onApply={applyPick}
              onCancel={() => setPicking(null)}
            />
          ) : (
            <div className="flex min-h-0 flex-1 flex-col gap-(--card-spacing) overflow-y-auto">
              <CardHeader>
                <CardTitle>{t('playerEdit.tabLook')}</CardTitle>
                <div className="flex w-fit rounded-md border p-0.5 text-sm">
                  {([true, false] as const).map((g) => (
                    <button
                      key={String(g)}
                      type="button"
                      onClick={() => switchMode(g)}
                      className={cn('rounded px-3 py-1', generic === g ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
                    >
                      {g ? t('playerEdit.genericHead') : t('playerEdit.realFace')}
                    </button>
                  ))}
                </div>
                <CardDescription>{generic ? t('playerEdit.lookGenericDescription') : t('playerEdit.lookFaceDescription')}</CardDescription>
                <div className="flex gap-1 pt-1">
                  {generic && (
                    <Button variant="outline" size="sm" onClick={randomize}>
                      <Dices /> {t('playerEdit.randomize')}
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" onClick={() => [...FACE_CODES, ...BODY_CODES, ...KIT_CODES].forEach((c) => setField(c, null))}>
                    <Eraser /> {t('playerEdit.resetDefault')}
                  </Button>
                </div>
              </CardHeader>
              {!generic && (
                <CardContent>
                  {gameHead && (
                    <div className="mb-3 flex items-center justify-between gap-2 rounded-md border p-2 text-sm">
                      <span>{face ? t('playerEdit.gameHeadReplaced') : t('playerEdit.gameHead')}</span>
                      {face && (
                        <Button variant="outline" size="sm" onClick={() => setField('face', null)}>
                          {t('playerEdit.gameHeadBack')}
                        </Button>
                      )}
                    </div>
                  )}
                  <FacePicker
                    key={player.id}
                    player={player}
                    current={face}
                    browsing={browsing}
                    onBrowse={(b) => {
                      if (b) showView('face')
                      setBrowsing(b)
                    }}
                    onPick={(f) => setField('face', f as FieldValue)}
                  />
                </CardContent>
              )}
              {groups.map(({ title, codes: groupCodes }) => {
                const shown = groupCodes.filter((c) => codes[c] && (generic || FACE_MODE_CODES.includes(c)))
                if (!shown.length) return null
                return (
                  <CardContent key={title} className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
                    <h3 className="border-b pb-1 text-sm font-semibold text-muted-foreground sm:col-span-2">{title}</h3>
                    {shown.map((code) => (
                      <div key={code} className="grid gap-1.5">
                        <p className="text-sm font-medium">{fieldLabel(code)}</p>
                        {thumbs.includes(code) ? (
                          <ThumbnailField
                            code={code}
                            value={own(code)}
                            inherited={inheritedCode(code)}
                            options={codes[code]}
                            variant={thumbnailVariant(code)}
                            onOpen={() => openPicker(code)}
                          />
                        ) : (
                          <Stepper value={own(code)} options={codes[code]} onChange={(value) => set(code, value)} inherited={inheritedCode(code)} label={named(code)} />
                        )}
                      </div>
                    ))}
                  </CardContent>
                )
              })}
            </div>
          )}
        </Card>
      </div>
      {/* the 3D preview takes all the free width, pushing the reference photo to the right */}
      <Card className="order-1 h-fit min-w-0 flex-1 gap-2 overflow-hidden py-0 xl:sticky xl:top-4 xl:order-2">
        <div className="aspect-[3/4] max-h-[75vh] w-full bg-gradient-to-b from-muted to-background">
          <Suspense
            fallback={
              <div className="flex size-full items-center justify-center text-muted-foreground">
                <LoaderCircle className="size-6 animate-spin" />
              </div>
            }
          >
            <KitPreview kit={kit} look={look} initialView="face" viewRequest={viewRequest} />
          </Suspense>
        </div>
        <p className="px-4 pb-3 text-center text-xs text-muted-foreground">{team ? t('look.previewKit', { team: teamName ?? `#${team.team}` }) : t('look.previewNoTeam')}</p>
      </Card>
      <Card className="order-2 h-fit w-full max-w-56 shrink-0 gap-2 overflow-hidden py-0 xl:sticky xl:top-4 xl:order-3 xl:w-56">
        <div className="flex aspect-[3/4] items-center justify-center bg-muted">
          {photoUrl ? <img src={photoUrl} alt="" className="size-full object-contain" /> : <User className="size-16 text-muted-foreground/50" />}
        </div>
        <p className="px-4 pb-3 text-center text-xs text-muted-foreground">{photoUrl ? t('playerEdit.photoReference') : t('playerEdit.noPhoto')}</p>
      </Card>
    </div>
  )
}
