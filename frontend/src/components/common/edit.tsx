import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { ChevronDown, Loader2, Plus, RotateCcw, Save, Undo2, X } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useBlocker } from 'react-router-dom'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Slider } from '@/components/ui/slider'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { EditForm, FieldSpec, FieldValue, NameTable, Ref, RosterRow } from '@/api/types'
import { FillScroll, Section } from '@/components/common/detail'
import { PickerDialog, type PickerItem } from '@/components/common/PickerDialog'
import { CountryFlag, Crest } from '@/components/common/pictures'
import { hasMessage, useI18n, type MessageKey } from '@/i18n'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useOptions, useStatus } from '@/state/queries'

export const ALL = '*'
export type Fields = Record<string, FieldValue>

/** Longest text the game shows for each name (the others have no fixed limit). */
export const NAME_LIMITS: Record<'team' | 'league' | 'country' | 'stadium', Record<string, number | undefined>> = {
  team: { abbr15: 15, abbr10: 10, abbr7: 7, abbr3: 3 },
  league: { abbr15: 15, trophy_abbr15: 15 },
  country: { full: 40, abbr3: 3 },
  stadium: { full: 60 },
}

// ---- comparing forms -------------------------------------------------------------------------------------------

export const cleanNames = (names: NameTable): NameTable =>
  Object.fromEntries(
    Object.entries(names)
      .map(([k, v]) => [k, Object.fromEntries(Object.entries(v).filter(([, text]) => text.trim()))] as const)
      .filter(([, v]) => Object.keys(v).length),
  )

const sameValue = (a: FieldValue | undefined, b: FieldValue | undefined) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null)

/** The fields that differ from the game (empty = the game's value). */
export const cleanFields = (fields: Fields, original: Fields): Fields =>
  Object.fromEntries(
    Object.entries(fields).filter(([k, v]) => v !== null && v !== '' && !(typeof v === 'string' && !v.trim()) && !sameValue(v, original[k])),
  )

const canonical = (value: unknown): unknown =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? Object.keys(value as object)
        .sort()
        .map((k) => [k, canonical((value as Record<string, unknown>)[k])])
    : value

const sameForm = (a: unknown, b: unknown) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b))

// ---- the CRUD of one entity -------------------------------------------------------------------------------------

interface FormState {
  names: NameTable
  fields: Fields
}

/** The edit form of one entity: its state, dirty flag, save, discard and back-to-original. */
export function useEntityForm<T extends EditForm & { saved_names?: NameTable }>({
  data,
  queryKey,
  invalidate,
  save,
  reset,
  extraDirty = false,
  onDiscard,
  invalid,
}: {
  data: T | undefined
  queryKey: QueryKey
  invalidate: string[]
  save: (form: FormState) => Promise<T>
  reset: () => Promise<T>
  /** A change the page keeps outside the form (a picture chosen but not saved yet): Save and Discard count it. */
  extraDirty?: boolean
  onDiscard?: () => void
  /** Whether the form has something to fix before saving (a required name): Save stays off. */
  invalid?: (form: FormState) => boolean
}) {
  const { t } = useI18n()
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>({ names: {}, fields: {} })
  const savedForm = useMemo<FormState>(() => ({ names: data?.saved_names ?? {}, fields: data?.saved ?? {} }), [data])
  // the form starts again only when what is saved changes (a flag of the page, like Hide, keeps the edits)
  const savedKey = data ? JSON.stringify([(data as { id?: number }).id, canonical(savedForm)]) : null
  useEffect(() => {
    if (savedKey !== null) setForm(savedForm)
  }, [savedKey]) // eslint-disable-line react-hooks/exhaustive-deps
  const cleaned = useMemo(() => ({ names: cleanNames(form.names), fields: cleanFields(form.fields, data?.values ?? {}) }), [form, data])
  const dirty = !!data && (extraDirty || !sameForm(cleaned, savedForm))
  const after = (saved: T) => {
    qc.setQueryData(queryKey, saved)
    for (const k of [...invalidate, 'status']) void qc.invalidateQueries({ queryKey: [k] })
  }
  const saving = useMutation({
    mutationFn: () => save(cleaned),
    onSuccess: (saved) => {
      after(saved)
      toast.success(t('edit.saved'))
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const resetting = useMutation({
    mutationFn: reset,
    onSuccess: (saved) => {
      after(saved)
      toast.success(t('edit.restored'))
    },
    onError: (e: Error) => toast.error(e.message),
  })
  return {
    form,
    dirty,
    invalid: !!data && !!invalid?.(form),
    setNames: (names: NameTable) => setForm((f) => ({ ...f, names })),
    setField: (name: string, value: FieldValue) => setForm((f) => ({ ...f, fields: { ...f.fields, [name]: value } })),
    discard: () => {
      setForm(savedForm)
      onDiscard?.()
    },
    saving,
    resetting,
  }
}

/** Discard, Save and (for an edited item) back to the original, with its confirmation. */
export function EditActions({ edited, entity }: { edited: boolean; entity: ReturnType<typeof useEntityForm> }) {
  const { t } = useI18n()
  const [confirm, setConfirm] = useState(false)
  return (
    <div className="flex flex-wrap items-start gap-2">
      <UnsavedGuard dirty={entity.dirty} />
      <Button variant="ghost" size="sm" disabled={!entity.dirty} onClick={entity.discard}>
        <Undo2 /> {t('common.discard')}
      </Button>
      <Button size="sm" disabled={!entity.dirty || entity.invalid || entity.saving.isPending} onClick={() => entity.saving.mutate()}>
        {entity.saving.isPending ? <Loader2 className="animate-spin" /> : <Save />} {t('common.save')}
      </Button>
      {edited && (
        <Button variant="outline" size="sm" disabled={entity.resetting.isPending} onClick={() => setConfirm(true)}>
          <RotateCcw /> {t('edit.restore')}
        </Button>
      )}
      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('edit.restoreTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('edit.restoreText')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => entity.resetting.mutate()}>
              {t('edit.restore')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

/** Holds the user on the page while the form has unsaved changes (inside the app and when closing the window). */
export function UnsavedGuard({ dirty }: { dirty: boolean }) {
  const { t } = useI18n()
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname)
  useEffect(() => {
    if (!dirty) return
    const onUnload = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [dirty])
  return (
    <AlertDialog open={blocker.state === 'blocked'}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('edit.unsavedTitle')}</AlertDialogTitle>
          <AlertDialogDescription>{t('edit.unsavedText')}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => blocker.reset?.()}>{t('edit.stay')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={() => blocker.proceed?.()}>
            {t('edit.leave')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

// ---- names by language (teams and leagues) ----------------------------------------------------------------------

/** Each name, in one table: the select picks "every language" (the value for all of them) or one language (a value
 * of its own, that wins over the one of every language). */
export function NamesEditor({
  kind,
  nameKeys,
  languages,
  original,
  names,
  setNames,
}: {
  kind: 'team' | 'league' | 'country'
  nameKeys: string[]
  languages: string[]
  original: NameTable
  names: NameTable
  setNames: (n: NameTable) => void
}) {
  const { t } = useI18n()
  const uiLang = useStatus().data?.names_language ?? 'eng_us'
  const [lang, setLang] = useState(ALL)
  const every = lang === ALL
  const limits = NAME_LIMITS[kind]
  const label = (key: string) => {
    const k = `${kind}Name.${key}`
    return hasMessage(k) ? t(k as MessageKey) : key
  }
  const hint = (key: string) => {
    const k = `${kind}Name.${key}.hint`
    return [limits[key] ? t('team.limit', { count: limits[key] }) : '', hasMessage(k) ? t(k as MessageKey) : ''].filter(Boolean).join(' · ')
  }
  const set = (key: string, code: string, text: string) => setNames({ ...names, [key]: { ...names[key], [code]: text } })
  const inGame = (key: string, code: string) => original[key]?.[code] ?? original[key]?.eng_us ?? ''
  return (
    <Section
      title={t('team.tab.names')}
      description={t(every ? `${kind}.namesAllHint` : `${kind}.namesLanguageHint`)}
      action={
        <Select value={lang} onValueChange={setLang}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('team.allLanguages')}</SelectItem>
            {languages.map((code) => (
              <SelectItem key={code} value={code}>
                {code}
                {nameKeys.some((k) => names[k]?.[code]?.trim()) ? ' •' : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-48">{t('team.nameKey')}</TableHead>
            <TableHead>{t('team.inGame')}</TableHead>
            <TableHead className="w-[45%]">{every ? t('team.allLanguages') : t('team.ownValue')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {nameKeys.map((key) => {
            const own = languages.filter((code) => names[key]?.[code]?.trim())
            return (
              <TableRow key={key}>
                <TableCell className="align-top whitespace-normal">
                  <p className="font-medium">{label(key)}</p>
                  {hint(key) && <p className="text-xs text-muted-foreground">{hint(key)}</p>}
                </TableCell>
                <TableCell className="align-top whitespace-normal text-muted-foreground">{(every ? inGame(key, uiLang) : original[key]?.[lang]) || '—'}</TableCell>
                <TableCell className="align-top whitespace-normal">
                  {every ? (
                    <div className="space-y-1">
                      <Input value={names[key]?.[ALL] ?? ''} maxLength={limits[key]} placeholder={inGame(key, uiLang)} onChange={(e) => set(key, ALL, e.target.value)} />
                      {own.length > 0 && <p className="text-xs text-muted-foreground">{t('team.ownValues', { langs: own.join(', ') })}</p>}
                    </div>
                  ) : (
                    <Input value={names[key]?.[lang] ?? ''} maxLength={limits[key]} placeholder={names[key]?.[ALL] || inGame(key, lang)} onChange={(e) => set(key, lang, e.target.value)} />
                  )}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </Section>
  )
}

/** The names as a grid: one row per language (the first, "All", is the value of every language) and one column per
 * name. An empty language cell shows, as its placeholder, what it will get: the "All" value as it is being typed,
 * else the game's name in that language. `required` names must have an "All" value. */
export function NamesGrid({
  kind,
  columns,
  languages,
  original,
  names,
  setNames,
  required = [],
}: {
  kind: 'team' | 'league' | 'country' | 'stadium'
  columns: string[]
  languages: string[]
  original: NameTable
  names: NameTable
  setNames: (n: NameTable) => void
  required?: string[]
}) {
  const { t } = useI18n()
  const uiLang = useStatus().data?.names_language ?? 'eng_us'
  const limits = NAME_LIMITS[kind]
  const label = (key: string) => {
    const k = `${kind}Name.${key}`
    return hasMessage(k) ? t(k as MessageKey) : key
  }
  const set = (key: string, code: string, text: string) => setNames({ ...names, [key]: { ...names[key], [code]: text } })
  // a language cell: the value saved, else the game's text (a value, not a hint); the same text as the game is not a
  // change (it is dropped from the form)
  const setLang = (key: string, code: string, text: string) => {
    const { [code]: _old, ...rest } = names[key] ?? {}
    setNames({ ...names, [key]: text === (original[key]?.[code] ?? '') ? rest : { ...rest, [code]: text } })
  }
  const shown = (key: string, code: string) => names[key]?.[code] ?? original[key]?.[code] ?? ''
  const inGame = (key: string, code: string) => original[key]?.[code] ?? original[key]?.eng_us ?? ''
  const missing = (key: string) => required.includes(key) && !names[key]?.[ALL]?.trim()
  const colgroup = (
    <colgroup>
      <col className="w-24" />
      {columns.map((key) => (
        // a short name (a 3-letter abbreviation) gets a narrow column, the others share the rest
        <col key={key} className={(limits[key] ?? 99) <= 3 ? 'w-44' : undefined} />
      ))}
    </colgroup>
  )
  const head = (
    <thead className="sticky top-0 z-10 shadow-[0_1px_0_var(--border)] [&_th]:bg-card">
      <tr className="border-b text-left text-muted-foreground">
        <th className="px-2 py-2 font-medium">{t('names.language')}</th>
        {columns.map((key) => (
          <th key={key} className="px-2 py-2 font-medium">
            {label(key)}
          </th>
        ))}
      </tr>
    </thead>
  )
  const allRow = (
    <tr className="border-b bg-muted/40">
      <td className="px-2 py-1.5 align-top leading-8 font-semibold">{t('names.all')}</td>
      {columns.map((key) => (
        <td key={key} className="px-2 py-1.5 align-top">
          <Input
            value={names[key]?.[ALL] ?? ''}
            maxLength={limits[key]}
            placeholder={inGame(key, uiLang)}
            aria-invalid={missing(key) || undefined}
            className={cn('h-8', missing(key) && 'border-destructive')}
            onChange={(e) => set(key, ALL, e.target.value)}
          />
          {missing(key) && <p className="mt-1 text-xs text-destructive">{t('names.required')}</p>}
        </td>
      ))}
    </tr>
  )
  const langRows = (codes: string[]) =>
    codes.map((code) => (
      <tr key={code} className="border-b last:border-0">
        <td className="px-2 py-1.5 font-mono text-xs text-muted-foreground">{code}</td>
        {columns.map((key) => (
          <td key={key} className="px-2 py-1.5">
            <Input className="h-8" value={shown(key, code)} maxLength={limits[key]} placeholder={names[key]?.[ALL]?.trim() || inGame(key, code)} onChange={(e) => setLang(key, code, e.target.value)} />
          </td>
        ))}
      </tr>
    ))
  // one name only (a stadium's): "All" and the languages in two halves side by side on wide screens
  if (columns.length === 1) {
    const half = Math.ceil((languages.length + 1) / 2) - 1 // "All" is the first row of the left half
    return (
      <Section title={t('team.tab.names')} description={t('names.gridHint')}>
        <div className="grid items-start gap-x-6 lg:grid-cols-2">
          {[languages.slice(0, half), languages.slice(half)].map((codes, i) => (
            <table key={i} className="w-full text-sm">
              {colgroup}
              {head}
              <tbody>
                {i === 0 && allRow}
                {langRows(codes)}
              </tbody>
            </table>
          ))}
        </div>
      </Section>
    )
  }
  return (
    <Section title={t('team.tab.names')} description={t('names.gridHint')}>
      {/* the grid scrolls on its own, with the header always on top */}
      <FillScroll>
        <table className="w-full text-sm">
          {colgroup}
          {head}
          <tbody>
            {allRow}
            {langRows(languages)}
          </tbody>
        </table>
      </FillScroll>
    </Section>
  )
}

// ---- database fields --------------------------------------------------------------------------------------------

const NONE = '__none__'
const hex = (rgb: FieldValue | undefined) =>
  Array.isArray(rgb) && rgb.every((c) => typeof c === 'number') ? '#' + rgb.map((c) => c.toString(16).padStart(2, '0')).join('') : '#000000'
const fromHex = (value: string) => [1, 3, 5].map((i) => parseInt(value.slice(i, i + 2), 16))

export function useFieldLabel() {
  const { t } = useI18n()
  return {
    label: (name: string) => {
      const k = `field.${name}`
      return hasMessage(k) ? t(k as MessageKey) : name
    },
    hint: (name: string) => {
      const k = `field.${name}.hint`
      return hasMessage(k) ? t(k as MessageKey) : ''
    },
    option: (name: string, value: number) => {
      for (const k of [`option.${name}.${value}`, `option.${name}`]) if (hasMessage(k)) return t(k as MessageKey, { value, stars: value + 1 })
      return String(value)
    },
  }
}

/** Lists long enough to need a search: chosen in the picker dialog (the app's Add dialog) instead of a select. */
type PickKind = 'nation' | 'team'

const foldText = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

function PickIcon({ kind, id, small }: { kind: PickKind; id: number; small?: boolean }) {
  return kind === 'nation' ? (
    <CountryFlag id={id} size={64} className={small ? 'h-3.5 w-5' : 'h-5 w-7'} />
  ) : (
    <Crest id={id} size={64} className={small ? 'size-4' : 'size-7'} />
  )
}

/** The picker dialog over a whole list (countries or teams): search by name or ID; the user's created countries first. */
export function RefPickerDialog({
  kind,
  open,
  onOpenChange,
  exclude = [],
  title,
  actionLabel,
  onPick,
}: {
  kind: PickKind
  open: boolean
  onOpenChange: (open: boolean) => void
  exclude?: number[]
  title: string
  actionLabel?: string
  onPick: (id: number) => void
}) {
  const { t } = useI18n()
  const options = useOptions().data
  const [q, setQ] = useState('')
  const all: Ref[] = (kind === 'nation' ? options?.nations : options?.teams) ?? []
  const wanted = foldText(q.trim())
  const items = all.filter((r) => !exclude.includes(r.id) && (!wanted || foldText(r.name).includes(wanted) || String(r.id) === wanted))
  const toItem = (r: Ref): PickerItem<number> => ({ key: r.id, icon: <PickIcon kind={kind} id={r.id} />, title: r.name, subtitle: `ID ${r.id}` })
  const groups =
    kind === 'nation'
      ? [
          { label: t('field.pick.newCountries'), items: items.filter((r) => r.is_new).map(toItem) },
          { label: t('field.pick.originalCountries'), items: items.filter((r) => !r.is_new).map(toItem) },
        ]
      : [{ items: items.map(toItem) }]
  return (
    <PickerDialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o)
        if (!o) setQ('')
      }}
      title={title}
      description={t(kind === 'nation' ? 'field.pick.countryDescription' : 'field.pick.teamDescription')}
      placeholder={t(kind === 'nation' ? 'countries.search' : 'teams.search')}
      query={q}
      onQuery={setQ}
      groups={groups}
      empty={t('field.pick.empty')}
      actionLabel={actionLabel}
      onPick={onPick}
    />
  )
}

/** One item of a long list (a country, a team): a button with its picture and name that opens the picker dialog. */
function RefPickerInput({
  kind,
  label,
  value,
  optional,
  onChange,
  className,
}: {
  kind: PickKind
  label: string
  value: number | null
  optional: boolean
  onChange: (id: number | null) => void
  className?: string
}) {
  const { t } = useI18n()
  const options = useOptions().data
  const [open, setOpen] = useState(false)
  const all: Ref[] = (kind === 'nation' ? options?.nations : options?.teams) ?? []
  const name = value === null ? null : (all.find((r) => r.id === value)?.name ?? `#${value}`)
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <Button type="button" variant="outline" className={cn('min-w-0 flex-1 justify-between font-normal', className)} onClick={() => setOpen(true)}>
        <span className="flex min-w-0 items-center gap-2">
          {value !== null && <PickIcon kind={kind} id={value} small />}
          <span className={cn('truncate', value === null && 'text-muted-foreground')}>{name ?? t('field.none')}</span>
        </span>
        <ChevronDown className="opacity-50" />
      </Button>
      {optional && value !== null && (
        <Button type="button" variant="ghost" size="icon-sm" title={t('field.pick.clear')} aria-label={t('field.pick.clear')} onClick={() => onChange(null)}>
          <X />
        </Button>
      )}
      <RefPickerDialog
        kind={kind}
        open={open}
        onOpenChange={setOpen}
        exclude={value === null ? [] : [value]}
        title={label}
        actionLabel={t('field.pick.choose')}
        onPick={(id) => {
          onChange(id)
          setOpen(false)
        }}
      />
    </div>
  )
}

/** A list of countries: chips with a remove button and an Add button that opens the picker dialog. `firstLabel` marks
 * the first one (a league's own country; the others are where it also shows). */
function NationsInput({ value, onChange, title, firstLabel, className }: { value: number[]; onChange: (v: number[]) => void; title: string; firstLabel?: string; className?: string }) {
  const { t } = useI18n()
  const nations = useOptions().data?.nations ?? []
  const [open, setOpen] = useState(false)
  const name = (id: number) => nations.find((n) => n.id === id)?.name ?? `#${id}`
  return (
    <div className={cn('flex flex-wrap items-center gap-1.5 rounded-md border p-1.5', className)}>
      {value.map((id, i) => (
        <span key={id} className="inline-flex items-center gap-1.5 rounded-md bg-muted px-2 py-0.5 text-sm">
          <PickIcon kind="nation" id={id} small />
          {name(id)}
          {i === 0 && firstLabel && <span className="text-xs text-muted-foreground">({firstLabel})</span>}
          <button type="button" className="text-muted-foreground hover:text-foreground" aria-label={t('field.nationsRemove')} title={t('field.nationsRemove')} onClick={() => onChange(value.filter((x) => x !== id))}>
            <X className="size-3.5" />
          </button>
        </span>
      ))}
      <Button type="button" variant="outline" size="sm" className="h-7 border-dashed" onClick={() => setOpen(true)}>
        <Plus /> {t('field.nationsAdd')}
      </Button>
      <RefPickerDialog kind="nation" open={open} onOpenChange={setOpen} exclude={value} title={title} onPick={(id) => onChange([...value, id])} />
    </div>
  )
}

/** A league's countries as one list, its own country first and then the ones it also shows in (the fields countryid
 * and extra_countries, kept apart in the project). Removing the first makes the next one its own. Edited in the
 * league's Countries tab, so the fields editor skips both. */
export const LEAGUE_COUNTRIES = { own: 'countryid', extra: 'extra_countries', hidden: 'hidden_in_countries' } as const

/** One input for one field; the shown value is the edited one, else the game's. */
function FieldInput({ spec, value, original, onChange, roster, bar }: { spec: FieldSpec; value: FieldValue | undefined; original: FieldValue | undefined; onChange: (v: FieldValue) => void; roster?: RosterRow[]; bar?: boolean }) {
  const { t } = useI18n()
  const { label, option } = useFieldLabel()
  const options = useOptions().data
  const current = value === undefined ? original : value
  const changed = value !== undefined && value !== '' && !sameValue(value, original)
  const ring = changed ? 'border-primary' : undefined
  // the "none" value of an optional field is its lowest value (-1 for a position, 0 for a country)
  const none = spec.optional ? spec.min : null
  const isNone = current === null || current === undefined || current === none
  const select = (items: Ref[]) => (
    <Select value={isNone ? NONE : String(current)} onValueChange={(v) => onChange(v === NONE ? none : Number(v))}>
      <SelectTrigger className={cn('w-full', ring)}>
        <SelectValue placeholder="—" />
      </SelectTrigger>
      <SelectContent>
        {spec.optional && <SelectItem value={NONE}>{t('field.none')}</SelectItem>}
        {!isNone && typeof current === 'number' && !items.some((i) => i.id === current) && <SelectItem value={String(current)}>#{current}</SelectItem>}
        {items.map((i) => (
          <SelectItem key={i.id} value={String(i.id)}>
            {i.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
  switch (spec.kind) {
    case 'text':
      return <Input className={ring} value={typeof value === 'string' ? value : ''} placeholder={typeof original === 'string' ? original : ''} maxLength={spec.max_length ?? undefined} onChange={(e) => onChange(e.target.value)} />
    case 'date':
      return <Input className={ring} type="date" value={typeof current === 'string' ? current : ''} onChange={(e) => onChange(e.target.value || null)} />
    case 'color':
      return (
        <div className="flex items-center gap-2">
          <input type="color" className={cn('h-8 w-12 cursor-pointer rounded border bg-transparent', ring)} value={hex(current)} onChange={(e) => onChange(fromHex(e.target.value))} />
          <span className="font-mono text-xs text-muted-foreground">{Array.isArray(current) ? current.join(', ') : '—'}</span>
        </div>
      )
    case 'select':
      return select(spec.options.map((o) => ({ id: o, name: option(spec.name, o) })))
    case 'position':
      return select(options?.positions ?? [])
    case 'nation':
    case 'team':
      return (
        <RefPickerInput
          kind={spec.kind}
          label={label(spec.name)}
          value={isNone || typeof current !== 'number' ? null : current}
          optional={spec.optional}
          onChange={(id) => onChange(id ?? none)}
          className={ring}
        />
      )
    case 'nations':
      return <NationsInput value={Array.isArray(current) ? (current as number[]) : []} onChange={onChange} title={label(spec.name)} className={ring} />
    case 'roster':
      return select((roster ?? []).map((p) => ({ id: p.id, name: p.jersey !== null ? `${p.jersey} · ${p.name}` : p.name })))
    default:
      if (bar && spec.min !== null && spec.max !== null && spec.max - spec.min <= 100) {
        const shown = typeof current === 'number' ? current : Math.round((spec.min + spec.max) / 2)
        return (
          <div className="flex items-center gap-3">
            <Slider min={spec.min} max={spec.max} step={1} value={[shown]} onValueChange={([v]) => onChange(v)} />
            <span className={cn('w-8 shrink-0 text-right text-sm tabular-nums', changed && 'font-medium text-primary')}>{typeof current === 'number' ? current : '—'}</span>
          </div>
        )
      }
      return (
        <Input
          className={cn('tabular-nums', ring)}
          type="number"
          min={spec.min ?? undefined}
          max={spec.max ?? undefined}
          value={current === null || current === undefined ? '' : String(current)}
          onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
        />
      )
  }
}

/** The fields of some groups, one card per group. */
export function FieldsEditor({
  form,
  groups,
  fields,
  setField,
  roster,
  columns = 'md:grid-cols-2',
  title,
  extra,
  bars = false,
  skip = [],
}: {
  form: EditForm
  groups: string[]
  /** Fields edited elsewhere on the page (not shown here). */
  skip?: string[]
  fields: Fields
  setField: (name: string, value: FieldValue) => void
  roster?: RosterRow[]
  /** Numeric fields as sliders (the attributes). */
  bars?: boolean
  columns?: string
  title?: (group: string) => ReactNode
  extra?: Record<string, ReactNode>
}) {
  const { t } = useI18n()
  const { label, hint } = useFieldLabel()
  return (
    <div className={cn('grid gap-4', columns)}>
      {groups.map((group) => {
        const specs = form.fields.filter((f) => f.group === group && !skip.includes(f.name))
        if (!specs.length) return null
        const groupKey = `fieldGroup.${group}`
        return (
          <Section key={group} title={title?.(group) ?? (hasMessage(groupKey) ? t(groupKey as MessageKey) : group)}>
            <div className="grid gap-3">
              {extra?.[group]}
              {specs.map((spec) => {
                const name = spec.name
                return (
                  <div key={spec.name} className="grid items-center gap-1 sm:grid-cols-[minmax(9rem,40%)_1fr] sm:gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm">{label(name)}</p>
                      {hint(name) && <p className="text-xs text-muted-foreground">{hint(name)}</p>}
                    </div>
                    <FieldInput spec={spec} value={fields[spec.name]} original={form.values[spec.name]} onChange={(v) => setField(spec.name, v)} roster={roster} bar={bars} />
                  </div>
                )
              })}
            </div>
          </Section>
        )
      })}
    </div>
  )
}
