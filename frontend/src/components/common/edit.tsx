import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { Loader2, RotateCcw, Save, Undo2 } from 'lucide-react'
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { EditForm, FieldSpec, FieldValue, NameTable, Ref, RosterRow } from '@/api/types'
import { Section } from '@/components/common/detail'
import { hasMessage, useI18n, type MessageKey } from '@/i18n'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useOptions } from '@/state/queries'

export const ALL = '*'
export type Fields = Record<string, FieldValue>

/** Longest text the game shows for each name (the others have no fixed limit). */
export const NAME_LIMITS: Record<'team' | 'league' | 'country', Record<string, number | undefined>> = {
  team: { abbr15: 15, abbr10: 10, abbr7: 7, abbr3: 3 },
  league: { abbr15: 15, trophy_abbr15: 15 },
  country: { full: 40, abbr3: 3 },
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
}: {
  data: T | undefined
  queryKey: QueryKey
  invalidate: string[]
  save: (form: FormState) => Promise<T>
  reset: () => Promise<T>
}) {
  const { t } = useI18n()
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>({ names: {}, fields: {} })
  const savedForm = useMemo<FormState>(() => ({ names: data?.saved_names ?? {}, fields: data?.saved ?? {} }), [data])
  useEffect(() => {
    if (data) setForm(savedForm)
  }, [data, savedForm])
  const cleaned = useMemo(() => ({ names: cleanNames(form.names), fields: cleanFields(form.fields, data?.values ?? {}) }), [form, data])
  const dirty = !!data && !sameForm(cleaned, savedForm)
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
    setNames: (names: NameTable) => setForm((f) => ({ ...f, names })),
    setField: (name: string, value: FieldValue) => setForm((f) => ({ ...f, fields: { ...f.fields, [name]: value } })),
    discard: () => setForm(savedForm),
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
      <Button size="sm" disabled={!entity.dirty || entity.saving.isPending} onClick={() => entity.saving.mutate()}>
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

/** Each name: one value for every language, and a value of its own for the languages that need one. */
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
  const [lang, setLang] = useState(languages.includes('por_br') ? 'por_br' : (languages[0] ?? 'eng_us'))
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
  const shown = (key: string, code: string) => original[key]?.[code] ?? original[key]?.eng_us ?? ''
  return (
    <div className="space-y-4">
      <Section title={t('team.namesAll')} description={t(`${kind}.namesAllHint`)}>
        <div className="grid gap-4">
          {nameKeys.map((key) => {
            const own = languages.filter((code) => names[key]?.[code]?.trim())
            return (
              <div key={key} className="grid items-center gap-2 sm:grid-cols-[14rem_1fr]">
                <div>
                  <p className="text-sm font-medium">{label(key)}</p>
                  <p className="text-xs text-muted-foreground">{hint(key)}</p>
                </div>
                <div className="space-y-1">
                  <Input value={names[key]?.[ALL] ?? ''} maxLength={limits[key]} placeholder={shown(key, lang)} onChange={(e) => set(key, ALL, e.target.value)} />
                  {own.length > 0 && <p className="text-xs text-muted-foreground">{t('team.ownValues', { langs: own.join(', ') })}</p>}
                </div>
              </div>
            )
          })}
        </div>
      </Section>
      <Section
        title={t('team.namesLanguage')}
        description={t(`${kind}.namesLanguageHint`)}
        action={
          <Select value={lang} onValueChange={setLang}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
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
              <TableHead className="w-[45%]">{t('team.ownValue')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {nameKeys.map((key) => (
              <TableRow key={key}>
                <TableCell className="font-medium">{label(key)}</TableCell>
                <TableCell className="text-muted-foreground">{original[key]?.[lang] ?? '—'}</TableCell>
                <TableCell>
                  <Input value={names[key]?.[lang] ?? ''} maxLength={limits[key]} placeholder={names[key]?.[ALL] || shown(key, lang)} onChange={(e) => set(key, lang, e.target.value)} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>
    </div>
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

/** One input for one field; the shown value is the edited one, else the game's. */
function FieldInput({ spec, value, original, onChange, roster }: { spec: FieldSpec; value: FieldValue | undefined; original: FieldValue | undefined; onChange: (v: FieldValue) => void; roster?: RosterRow[] }) {
  const { t } = useI18n()
  const { option } = useFieldLabel()
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
      return select(options?.nations ?? [])
    case 'team':
      return select(options?.teams ?? [])
    case 'roster':
      return select((roster ?? []).map((p) => ({ id: p.id, name: p.jersey !== null ? `${p.jersey} · ${p.name}` : p.name })))
    default:
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
}: {
  form: EditForm
  groups: string[]
  fields: Fields
  setField: (name: string, value: FieldValue) => void
  roster?: RosterRow[]
  columns?: string
  title?: (group: string) => ReactNode
  extra?: Record<string, ReactNode>
}) {
  const { t } = useI18n()
  const { label, hint } = useFieldLabel()
  return (
    <div className={cn('grid gap-4', columns)}>
      {groups.map((group) => {
        const specs = form.fields.filter((f) => f.group === group)
        if (!specs.length) return null
        const groupKey = `fieldGroup.${group}`
        return (
          <Section key={group} title={title?.(group) ?? (hasMessage(groupKey) ? t(groupKey as MessageKey) : group)}>
            <div className="grid gap-3">
              {extra?.[group]}
              {specs.map((spec) => (
                <div key={spec.name} className="grid items-center gap-1 sm:grid-cols-[minmax(9rem,40%)_1fr] sm:gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm">{label(spec.name)}</p>
                    {hint(spec.name) && <p className="text-xs text-muted-foreground">{hint(spec.name)}</p>}
                  </div>
                  <FieldInput spec={spec} value={fields[spec.name]} original={form.values[spec.name]} onChange={(v) => setField(spec.name, v)} roster={roster} />
                </div>
              ))}
            </div>
          </Section>
        )
      })}
    </div>
  )
}
