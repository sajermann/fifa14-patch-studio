import { useQuery } from '@tanstack/react-query'
import { ChevronDown, Loader2, Plus, Shirt, Trash2, Upload, X } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import { api } from '@/api/client'
import type { KitConfig, KitFonts, KitPart, KitPrint, TeamDetail, TeamKit } from '@/api/types'
import { Section } from '@/components/common/detail'
import { readPicture } from '@/components/common/pictures'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useI18n, type MessageKey } from '@/i18n'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useToken } from '@/state/queries'
import { TeamPickerDialog } from './NewTeamDialog'
import { EXTRA_KITS, fromHex, hex, type PendingKit, type PendingPicture } from './pending'

const KIND_LABELS: Record<number, MessageKey> = { 0: 'kit.home', 1: 'kit.away', 2: 'kit.goalkeeper', 3: 'kit.third' }
const COLLARS = Array.from({ length: 16 }, (_, i) => i) // jerseycollargeometrytype values of the game (0-15)
type Source = 'default' | 'game' | 'upload' | 'generic'

function useKindLabel() {
  const { t } = useI18n()
  return (kind: number) => (KIND_LABELS[kind] ? t(KIND_LABELS[kind]) : t('kit.extra', { n: kind }))
}

function useImageUrl() {
  const token = useToken()
  return (url: string) => `${url}${url.includes('?') ? '&' : '?'}v=${token}`
}

function useKitFonts() {
  const token = useToken()
  return useQuery({ queryKey: ['kit-fonts', token], queryFn: api.kitFonts, enabled: !!token, staleTime: Infinity }).data
}

function KitPicture({ src, className }: { src: string | null; className?: string }) {
  const [failed, setFailed] = useState<string | null>(null)
  if (!src || failed === src)
    return (
      <span className={cn('flex items-center justify-center text-muted-foreground/50', className)}>
        <Shirt className="size-1/2" />
      </span>
    )
  return <img src={src} alt="" loading="lazy" className={cn('object-contain', className)} onError={() => setFailed(src)} />
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <p className="text-sm font-medium">{label}</p>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

function Choice({ value, onChange, children }: { value: string; onChange: (v: string) => void; children: ReactNode }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>{children}</SelectContent>
    </Select>
  )
}

const rgbCss = (rgb: number[]) => `rgb(${rgb.join(',')})`

/** A number color: the palette of the game's number files (each shown in the color its digits really have). */
function NumberColorSelect({ value, fonts, onChange }: { value: number; fonts: KitFonts | undefined; onChange: (v: number) => void }) {
  const { t } = useI18n()
  const colors = fonts?.colors ?? []
  const ids = colors.some((c) => c.id === value) ? colors : [...colors, { id: value, rgb: [128, 128, 128] }]
  return (
    <Choice value={String(value)} onChange={(v) => onChange(Number(v))}>
      {ids.map((c) => (
        <SelectItem key={c.id} value={String(c.id)}>
          <span className="size-3.5 rounded-sm border" style={{ background: rgbCss(c.rgb) }} />
          {t('kit.numberColor', { n: c.id })}
        </SelectItem>
      ))}
    </Choice>
  )
}

/** A number font: only the fonts the game has digits for in the chosen color (the current one stays listed). */
function NumberFontSelect({ value, color, fonts, onChange }: { value: number; color: number; fonts: KitFonts | undefined; onChange: (v: number) => void }) {
  const list = Object.entries(fonts?.number ?? {})
    .filter(([font, colors]) => colors.includes(color) || Number(font) === value)
    .map(([font]) => Number(font))
  if (!list.includes(value)) list.push(value)
  return (
    <Choice value={String(value)} onChange={(v) => onChange(Number(v))}>
      {list.sort((a, b) => a - b).map((f) => (
        <SelectItem key={f} value={String(f)}>
          {f}
        </SelectItem>
      ))}
    </Choice>
  )
}

/** One picture of an uploaded kit: click or drop to choose, the X takes it out. */
function KitFileBox({ label, hint, aspect, src, onPick, onRemove }: { label: string; hint: string; aspect: string; src: string | null; onPick: (file: File) => Promise<void>; onRemove: () => void }) {
  const { t } = useI18n()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const pick = async (file: File) => {
    setBusy(true)
    try {
      await onPick(file)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm font-medium">{label}</p>
        <span className="text-xs text-muted-foreground">{hint}</span>
      </div>
      <div
        className={cn('relative flex cursor-pointer items-center justify-center overflow-hidden rounded-lg border border-dashed bg-muted/40', aspect)}
        onClick={() => input.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          const f = e.dataTransfer.files[0]
          if (f) void pick(f)
        }}
      >
        {busy ? (
          <Loader2 className="animate-spin" />
        ) : src ? (
          <img src={src} alt={label} className="size-full object-contain" />
        ) : (
          <span className="flex flex-col items-center gap-1 p-2 text-center text-xs text-muted-foreground">
            <Upload className="size-4" /> {t('kit.clickOrDrop')}
          </span>
        )}
        {src && !busy && (
          <Button
            variant="secondary"
            size="icon"
            className="absolute top-1 right-1 size-6"
            title={t('kit.removePicture')}
            onClick={(e) => {
              e.stopPropagation()
              onRemove()
            }}
          >
            <X className="size-3" />
          </Button>
        )}
      </div>
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/bmp"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) void pick(f)
          e.target.value = ''
        }}
      />
    </div>
  )
}

/** Dialog: the game's generic mask kits painted with the two colors chosen. */
function ModelGallery({ open, onOpenChange, colors, onPick }: { open: boolean; onOpenChange: (o: boolean) => void; colors: number[][]; onPick: (model: number) => void }) {
  const { t } = useI18n()
  const token = useToken()
  const url = useImageUrl()
  const { data } = useQuery({ queryKey: ['kit-models', token], queryFn: api.kitModels, enabled: open && !!token, staleTime: Infinity })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent width="lg">
        <DialogHeader>
          <DialogTitle>{t('kit.models')}</DialogTitle>
          <DialogDescription>{t('kit.modelsHint')}</DialogDescription>
        </DialogHeader>
        <div className="grid max-h-[60vh] grid-cols-4 gap-2 overflow-y-auto pr-2 sm:grid-cols-6">
          {(data?.models ?? []).map((m) => (
            <button key={m} type="button" className="rounded-md border p-1 hover:border-primary" onClick={() => onPick(m)} title={`#${m}`}>
              <KitPicture src={url(`/api/image/kitmodel/${m}?c1=${hex(colors[0])}&c2=${hex(colors[1])}&size=128`)} className="aspect-square w-full" />
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** Name and numbers of the kit (teamkits): the same choices as the Street Studio's. A value left unchanged keeps the
 * kit's own (shown as the current value). */
function KitPrintEditor({ shown, set, fonts }: { shown: Required<KitPrint>; set: (p: KitPrint) => void; fonts: KitFonts | undefined }) {
  const { t } = useI18n()
  const check = (key: 'front_number' | 'shorts_number' | 'show_name', label: MessageKey, hint?: MessageKey) => (
    <label className="flex items-start gap-2 text-sm">
      <Checkbox className="mt-0.5" checked={shown[key]} onCheckedChange={(c) => set({ [key]: c === true })} />
      <span>
        {t(label)}
        {hint && <span className="block text-xs text-muted-foreground">{t(hint)}</span>}
      </span>
    </label>
  )
  return (
    <div className="space-y-4 border-t pt-4">
      <p className="text-sm font-medium">{t('kit.printTitle')}</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t('kit.nameColor')}>
          <label className="flex items-center gap-2">
            <input
              type="color"
              className="h-9 w-14 cursor-pointer rounded border bg-transparent"
              value={`#${hex(shown.name_color)}`}
              onChange={(e) => set({ name_color: fromHex(e.target.value) })}
            />
            <span className="font-mono text-xs text-muted-foreground">{shown.name_color.join(', ')}</span>
          </label>
        </Field>
        <Field label={t('kit.collar')} hint={t('kit.collarHint')}>
          <Choice value={String(shown.collar)} onChange={(v) => set({ collar: Number(v) })}>
            {COLLARS.map((c) => (
              <SelectItem key={c} value={String(c)}>
                {t('kit.collarOption', { n: c })}
              </SelectItem>
            ))}
          </Choice>
        </Field>
        <Field label={t('kit.jerseyNumber')}>
          <NumberColorSelect value={shown.number_color} fonts={fonts} onChange={(v) => set({ number_color: v })} />
        </Field>
        <Field label={t('kit.shortsNumber')}>
          <NumberColorSelect value={shown.shorts_number_color} fonts={fonts} onChange={(v) => set({ shorts_number_color: v })} />
        </Field>
      </div>
      {check('front_number', 'kit.frontNumber', 'kit.frontNumberHint')}
      {check('shorts_number', 'kit.shortsNumberOn')}
      {check('show_name', 'kit.showName')}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t('kit.nameLayout')}>
          <Choice value={String(shown.name_layout)} onChange={(v) => set({ name_layout: Number(v) })}>
            <SelectItem value="0">{t('kit.nameStraight')}</SelectItem>
            <SelectItem value="1">{t('kit.nameArc')}</SelectItem>
          </Choice>
        </Field>
        <Field label={t('kit.nameFont')}>
          <Choice value={String(shown.name_font)} onChange={(v) => set({ name_font: Number(v) })}>
            {(fonts?.name ?? [{ id: shown.name_font, name: null }]).map((f) => (
              <SelectItem key={f.id} value={String(f.id)}>
                {f.name ? `${f.id} · ${f.name}` : String(f.id)}
              </SelectItem>
            ))}
          </Choice>
        </Field>
        <Field label={t('kit.numberFont')} hint={t('kit.numberFontHint')}>
          <NumberFontSelect value={shown.number_font} color={shown.number_color} fonts={fonts} onChange={(v) => set({ number_font: v })} />
        </Field>
        <Field label={t('kit.shortsNumberFont')}>
          <NumberFontSelect value={shown.shorts_number_font} color={shown.shorts_number_color} fonts={fonts} onChange={(v) => set({ shorts_number_font: v })} />
        </Field>
      </div>
    </div>
  )
}

const PRINT_FALLBACK: Required<KitPrint> = {
  name_color: [255, 255, 255],
  number_color: 1,
  shorts_number_color: 1,
  front_number: false,
  shorts_number: false,
  show_name: true,
  name_layout: 0,
  name_font: 0,
  number_font: 1,
  shorts_number_font: 1,
  collar: 0,
}

/** One kit of the team: where it comes from (with a preview), its pictures when uploaded, and its name and numbers. */
function KitCard({ team, kit, pending, setPending, fonts }: { team: TeamDetail; kit: TeamKit; pending: PendingKit | undefined; setPending: (p: PendingKit | undefined) => void; fonts: KitFonts | undefined }) {
  const { t } = useI18n()
  const kindLabel = useKindLabel()
  const url = useImageUrl()
  const [picking, setPicking] = useState(false)
  const [gallery, setGallery] = useState(false)
  const config: KitConfig | null = pending ? pending.config : kit.config
  const source: Source = !config || config.source === 'keep' ? 'default' : config.source
  const pictures = pending?.pictures ?? {}
  const teamColor = (n: number, fallback: number[]) => ((team.saved[`teamcolor${n}`] ?? team.values[`teamcolor${n}`]) as number[] | null) ?? fallback
  const colors = config?.source === 'generic' ? config.colors : [teamColor(1, [200, 200, 200]), teamColor(2, [255, 255, 255])].map((c) => c.map((v) => v ?? 0))
  const update = (next: KitConfig | null, pics: Partial<Record<KitPart, PendingPicture>> = pictures) => setPending({ config: next, pictures: pics })
  const extra = kit.kind > 3
  const exists = !!config || !!kit.default // the kit is in the patch (its own, a default, or the user's)
  const shown: Required<KitPrint> = { ...PRINT_FALLBACK, ...kit.print, ...(config?.print ?? {}), ...(config?.collar !== undefined ? { collar: config.collar } : {}) }
  const setPrint = (patch: KitPrint) => {
    const { collar, ...rest } = patch
    const base: KitConfig = config ?? { source: 'keep' }
    update({ ...base, ...(collar !== undefined ? { collar } : {}), print: { ...(base.print ?? {}), ...rest } })
  }
  const savedVersion = Object.values(kit.pictures).filter(Boolean).join('-')
  const picture = (part: KitPart): string | null => {
    const p = pictures[part]
    if (p && p !== 'remove') return p.url
    if (p === 'remove') return null
    return kit.pictures[part] ? url(`/api/image/kit/${team.id}/${kit.kind}?part=${part}&own=${kit.pictures[part]}`) : null
  }
  const preview = (part: 'mini' | 'jersey'): string | null => {
    const size = part === 'mini' ? 256 : 512
    if (!pending || config?.source === 'keep') return kit.config || kit.default ? url(`/api/image/kit/${team.id}/${kit.kind}?part=${part}&size=${size}&own=${savedVersion}`) : null
    if (!config) return null
    if (config.source === 'generic') return url(`/api/image/kitmodel/${config.model}?c1=${hex(config.colors[0])}&c2=${hex(config.colors[1])}&part=${part}&size=${size}`)
    if (config.source === 'game') return url(`/api/image/kit/${config.team}/${config.kind}?part=${part}&size=${size}`)
    return picture(part)
  }
  const choosePicture = async (part: KitPart, file: File) => {
    try {
      const data = await readPicture(file)
      update(config, { ...pictures, [part]: { data, url: URL.createObjectURL(file) } })
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  const keepExtras = { ...(config?.collar !== undefined ? { collar: config.collar } : {}), ...(config?.print ? { print: config.print } : {}) }
  const removeAll = () => update(null, Object.fromEntries((['jersey', 'shorts', 'mini'] as KitPart[]).map((p) => [p, kit.pictures[p] ? 'remove' : null])))
  const setSource = (value: Source) => {
    if (value === 'default' && extra && !kit.config && !kit.default) return setPending(undefined) // an extra not saved yet
    if (value === 'default') return config?.print || config?.collar !== undefined ? update({ source: 'keep', ...keepExtras }) : removeAll()
    if (value === 'game') return setPicking(true)
    if (value === 'upload') return update({ source: 'upload', ...keepExtras })
    update({ source: 'generic', model: 7500 + (kit.kind === 1 ? 100 : 0), colors: kit.kind === 1 ? [colors[1], colors[0]] : [colors[0], colors[1]], ...keepExtras })
  }
  const removeExtra = () => (kit.config || kit.default ? removeAll() : setPending(undefined))
  const defaultLabel = extra && !kit.default ? t('kit.chooseSource') : kit.default === 'generic' ? t(kit.kind === 2 ? 'kit.defaultKeeper' : 'kit.defaultGeneric') : kit.default === 'game' ? t(team.is_new ? 'kit.defaultCopied' : 'kit.defaultGame') : t('kit.none')
  const removedExtra = extra && !!pending && !pending.config && !kit.default
  return (
    <div className="space-y-4 rounded-lg border p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="font-medium">
          {kindLabel(kit.kind)}
          {pending && <span className="ml-2 text-xs font-normal text-amber-600 dark:text-amber-400">{t(removedExtra ? 'kit.removedPending' : 'kit.pending')}</span>}
        </p>
        {extra && !removedExtra && (
          <Button variant="ghost" size="sm" onClick={removeExtra}>
            <Trash2 /> {t('kit.removeExtra')}
          </Button>
        )}
      </div>
      <div className="flex flex-wrap items-start gap-4">
        <div className="flex gap-2">
          <KitPicture src={preview('mini')} className="size-24 shrink-0 rounded bg-muted/40" />
          <KitPicture src={preview('jersey')} className="size-24 shrink-0 rounded bg-muted/40" />
        </div>
        <div className="min-w-0 flex-1 basis-56 space-y-2">
          <Field label={t('kit.source')}>
            <Choice value={source} onChange={(v) => setSource(v as Source)}>
              <SelectItem value="default">{defaultLabel}</SelectItem>
              <SelectItem value="game">{t('kit.sourceGame')}</SelectItem>
              <SelectItem value="upload">{t('kit.sourceUpload')}</SelectItem>
              <SelectItem value="generic">{t('kit.sourceGeneric')}</SelectItem>
            </Choice>
          </Field>
          {config?.source === 'game' && (
            <Button variant="outline" size="sm" className="w-full justify-between font-normal" onClick={() => setPicking(true)}>
              <span className="truncate">{t('kit.fromTeam', { team: config.team, kind: kindLabel(config.kind) })}</span>
              <ChevronDown className="opacity-50" />
            </Button>
          )}
          {config?.source === 'generic' && (
            <>
              <Button variant="outline" size="sm" className="w-full justify-between font-normal" onClick={() => setGallery(true)}>
                <span>{t('kit.model', { model: config.model })}</span>
                <ChevronDown className="opacity-50" />
              </Button>
              <div className="flex flex-wrap gap-4">
                {[0, 1].map((i) => (
                  <label key={i} className="flex items-center gap-2 text-sm">
                    <input
                      type="color"
                      className="h-8 w-12 cursor-pointer rounded border bg-transparent"
                      value={`#${hex(config.colors[i])}`}
                      onChange={(e) => update({ ...config, colors: i === 0 ? [fromHex(e.target.value), config.colors[1]] : [config.colors[0], fromHex(e.target.value)] })}
                    />
                    {t(i === 0 ? 'team.color1' : 'team.color2')}
                  </label>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
      {config?.source === 'upload' && (
        <>
          <div className="grid grid-cols-[1fr_1fr_2fr] gap-3">
            <KitFileBox label={t('kit.part.mini')} hint={t('kit.optional')} aspect="aspect-square" src={picture('mini')} onPick={(f) => choosePicture('mini', f)} onRemove={() => update(config, { ...pictures, mini: kit.pictures.mini ? 'remove' : null })} />
            <KitFileBox label={t('kit.part.jersey')} hint="2048×2048" aspect="aspect-square" src={picture('jersey')} onPick={(f) => choosePicture('jersey', f)} onRemove={() => update(config, { ...pictures, jersey: kit.pictures.jersey ? 'remove' : null })} />
            <KitFileBox label={t('kit.part.shorts')} hint="2048×1024" aspect="aspect-[2/1]" src={picture('shorts')} onPick={(f) => choosePicture('shorts', f)} onRemove={() => update(config, { ...pictures, shorts: kit.pictures.shorts ? 'remove' : null })} />
          </div>
          <p className="text-xs text-muted-foreground">{t('kit.uploadHint')}</p>
        </>
      )}
      {exists && !removedExtra && <KitPrintEditor shown={shown} set={setPrint} fonts={fonts} />}
      <TeamPickerDialog
        open={picking}
        onOpenChange={setPicking}
        title={t('kit.sourceGame')}
        description={t('kit.sourceGameHint', { kind: kindLabel(kit.kind) })}
        exclude={[team.id]}
        onPick={(other) => {
          update({ source: 'game', team: other.id, kind: kit.kind, ...keepExtras })
          setPicking(false)
        }}
      />
      {config?.source === 'generic' && (
        <ModelGallery
          open={gallery}
          onOpenChange={setGallery}
          colors={config.colors}
          onPick={(model) => {
            update({ ...config, model })
            setGallery(false)
          }}
        />
      )}
    </div>
  )
}

/** The team's kits (home, away, goalkeeper, third and the extras), two per row like the Street Studio's. */
export function TeamKits({ team, pending, setPending }: { team: TeamDetail; pending: Record<number, PendingKit>; setPending: (kind: number, p: PendingKit | undefined) => void }) {
  const { t } = useI18n()
  const fonts = useKitFonts()
  // the team's kits + extra kits added on the page and not saved yet
  const kinds = [...new Set([...team.kits.map((k) => k.kind), ...Object.keys(pending).map(Number)])].sort((a, b) => a - b)
  const nextExtra = EXTRA_KITS.find((k) => !kinds.includes(k))
  const color = (n: number, fallback: number[]) => ((team.saved[`teamcolor${n}`] ?? team.values[`teamcolor${n}`]) as number[] | null) ?? fallback
  const empty = (kind: number): TeamKit => ({ kind, config: null, pictures: { jersey: null, shorts: null, mini: null }, default: null, print: team.kits.find((k) => k.kind === 0)?.print ?? {} })
  return (
    <Section
      title={t('kit.title')}
      description={t('kit.hint')}
      action={
        nextExtra !== undefined && (
          <Button
            size="sm"
            title={t('kit.addExtraHint')}
            onClick={() => setPending(nextExtra, { config: { source: 'generic', model: 7500, colors: [color(1, [200, 200, 200]), color(2, [255, 255, 255])] }, pictures: {} })}
          >
            <Plus /> {t('kit.addExtra')}
          </Button>
        )
      }
    >
      <div className="grid gap-4 xl:grid-cols-2">
        {kinds.map((kind) => (
          <KitCard key={kind} team={team} kit={team.kits.find((k) => k.kind === kind) ?? empty(kind)} pending={pending[kind]} setPending={(p) => setPending(kind, p)} fonts={fonts} />
        ))}
      </div>
    </Section>
  )
}
