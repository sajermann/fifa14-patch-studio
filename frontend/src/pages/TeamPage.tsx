import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RotateCcw, Save, Undo2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useBlocker, useParams } from 'react-router-dom'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/api/client'
import type { NameTable, TeamDetail } from '@/api/types'
import { Facts, OriginalBadge, OverallBadge, RawTable, Section } from '@/components/common/detail'
import { ColorDot, Crest, Photo } from '@/components/common/pictures'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { toast } from '@/lib/notify'
import { useI18n, type MessageKey } from '@/i18n'
import { BackButton, useBack, useFrom, useTabParam } from '@/lib/back'
import { useStatus, useToken } from '@/state/queries'

const TABS = ['names', 'roster', 'raw'] as const
const ALL = '*'
/** Longest text the game shows for each name (the full name and the narration name have no fixed limit). */
export const NAME_LIMITS: Record<string, number | undefined> = {
  abbr15: 15,
  abbr10: 10,
  abbr7: 7,
  abbr3: 3,
}

const clean = (names: NameTable): NameTable =>
  Object.fromEntries(
    Object.entries(names)
      .map(([k, v]) => [k, Object.fromEntries(Object.entries(v).filter(([, text]) => text.trim()))] as const)
      .filter(([, v]) => Object.keys(v).length),
  )

/** The names in a fixed order (keys and languages sorted), to compare two forms. */
const canonical = (names: NameTable) =>
  JSON.stringify(
    Object.entries(clean(names))
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => [
        k,
        Object.entries(v)
          .map(([code, text]) => [code, text.trim()] as const)
          .sort(([a], [b]) => a.localeCompare(b)),
      ]),
  )

const same = (a: NameTable, b: NameTable) => canonical(a) === canonical(b)

/** Holds the user on the page while the form has unsaved changes (inside the app and when closing the window). */
function UnsavedGuard({ dirty }: { dirty: boolean }) {
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

/** Each name of the team: one value for every language, and a value of its own for the languages that need one. */
function NamesEditor({
  team,
  form,
  setForm,
  lang,
  setLang,
}: {
  team: TeamDetail
  form: NameTable
  setForm: (f: NameTable) => void
  lang: string
  setLang: (l: string) => void
}) {
  const { t } = useI18n()
  const set = (key: string, code: string, text: string) => setForm({ ...form, [key]: { ...(form[key] ?? {}), [code]: text } })
  const original = (key: string, code: string) => team.original_names[key]?.[code] ?? team.original_names[key]?.eng_us ?? ''
  return (
    <div className="space-y-4">
      <Section title={t('team.namesAll')} description={t('team.namesAllHint')}>
        <div className="grid gap-4">
          {team.name_keys.map((key) => {
            const limit = NAME_LIMITS[key]
            const own = team.languages.filter((code) => form[key]?.[code]?.trim())
            return (
              <div key={key} className="grid items-center gap-2 sm:grid-cols-[14rem_1fr]">
                <div>
                  <p className="text-sm font-medium">{t(`teamName.${key}` as MessageKey)}</p>
                  <p className="text-xs text-muted-foreground">{limit ? t('team.limit', { count: limit }) : t(`teamName.${key}.hint` as MessageKey)}</p>
                </div>
                <div className="space-y-1">
                  <Input value={form[key]?.[ALL] ?? ''} maxLength={limit} placeholder={original(key, lang)} onChange={(e) => set(key, ALL, e.target.value)} />
                  {own.length > 0 && <p className="text-xs text-muted-foreground">{t('team.ownValues', { langs: own.join(', ') })}</p>}
                </div>
              </div>
            )
          })}
        </div>
      </Section>
      <Section
        title={t('team.namesLanguage')}
        description={t('team.namesLanguageHint')}
        action={
          <Select value={lang} onValueChange={setLang}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {team.languages.map((code) => (
                <SelectItem key={code} value={code}>
                  {code}
                  {team.name_keys.some((k) => form[k]?.[code]?.trim()) ? ' •' : ''}
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
            {team.name_keys.map((key) => (
              <TableRow key={key}>
                <TableCell className="font-medium">{t(`teamName.${key}` as MessageKey)}</TableCell>
                <TableCell className="text-muted-foreground">{team.original_names[key]?.[lang] ?? '—'}</TableCell>
                <TableCell>
                  <Input
                    value={form[key]?.[lang] ?? ''}
                    maxLength={NAME_LIMITS[key]}
                    placeholder={form[key]?.[ALL] || original(key, lang)}
                    onChange={(e) => set(key, lang, e.target.value)}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>
    </div>
  )
}

export function TeamPage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const qc = useQueryClient()
  const shown = useStatus().data?.names_language ?? 'eng_us'
  const { data: team, isLoading } = useQuery({
    queryKey: ['team', token, id],
    queryFn: () => api.team(id),
    enabled: !!token,
  })
  const tabs = useTabParam(TABS[0])
  const from = useFrom(team?.name ?? t('nav.teams'))
  const back = useBack({ to: '/teams', label: t('nav.teams') })
  const [form, setForm] = useState<NameTable>({})
  const [lang, setLang] = useState(shown)
  const [confirmReset, setConfirmReset] = useState(false)
  useEffect(() => {
    if (team) setForm(team.saved_names)
  }, [team])
  const dirty = useMemo(() => (team ? !same(form, team.saved_names) : false), [form, team])
  const afterSave = (saved: TeamDetail) => {
    qc.setQueryData(['team', token, id], saved)
    setForm(saved.saved_names)
    void qc.invalidateQueries({ queryKey: ['teams'] })
    void qc.invalidateQueries({ queryKey: ['status'] })
  }
  const save = useMutation({
    mutationFn: () => api.saveTeam(id, clean(form)),
    onSuccess: (saved) => {
      afterSave(saved)
      toast.success(t('edit.saved'))
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const reset = useMutation({
    mutationFn: () => api.resetTeam(id),
    onSuccess: (saved) => {
      afterSave(saved)
      toast.success(t('edit.restored'))
    },
    onError: (e: Error) => toast.error(e.message),
  })
  if (isLoading || !team) return <LoadingBlock />
  return (
    <div className="space-y-4">
      <UnsavedGuard dirty={dirty} />
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 items-center gap-3">
          <Crest id={team.id} size={96} available={team.has_crest} className="size-12" />
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold break-words">{team.name}</h1>
            <p className="text-sm text-muted-foreground">
              {team.leagues.map((l, i) => (
                <span key={l.id}>
                  {i > 0 && ' · '}
                  <Link to={`/leagues/${l.id}`} state={from.state} className="hover:underline">
                    {l.name}
                  </Link>
                </span>
              ))}{' '}
              · ID {team.id}
            </p>
          </div>
          <OriginalBadge edited={team.edited} />
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <Button variant="ghost" size="sm" disabled={!dirty} onClick={() => setForm(team.saved_names)}>
            <Undo2 /> {t('common.discard')}
          </Button>
          <Button size="sm" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? <Loader2 className="animate-spin" /> : <Save />} {t('common.save')}
          </Button>
          {team.edited && (
            <Button variant="outline" size="sm" disabled={reset.isPending} onClick={() => setConfirmReset(true)}>
              <RotateCcw /> {t('edit.restore')}
            </Button>
          )}
        </div>
      </div>

      <Tabs {...tabs}>
        <TabsList>
          <TabsTrigger value="names">{t('team.tab.names')}</TabsTrigger>
          <TabsTrigger value="roster">
            {t('team.tab.roster')} ({team.roster.length})
          </TabsTrigger>
          <TabsTrigger value="raw">{t('tab.raw')}</TabsTrigger>
        </TabsList>
        <TabsContent value="names" className="mt-4">
          <NamesEditor team={team} form={form} setForm={setForm} lang={lang} setLang={setLang} />
        </TabsContent>
        <TabsContent value="roster" className="mt-4 space-y-4">
          <Section title={t('team.ratings')}>
            <Facts
              items={[
                [t('col.overall'), <OverallBadge key="o" value={team.overall} />],
                [t('team.attack'), team.attack],
                [t('team.midfield'), team.midfield],
                [t('team.defense'), team.defense],
                [t('col.colors'), <ColorDot key="c" rgb={team.color} />],
              ]}
            />
          </Section>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10" />
                <TableHead>{t('col.number')}</TableHead>
                <TableHead>{t('col.name')}</TableHead>
                <TableHead>{t('col.role')}</TableHead>
                <TableHead>{t('col.position')}</TableHead>
                <TableHead>{t('col.overall')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {team.roster.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <Photo id={p.id} size={64} available={p.has_photo} className="size-8" />
                  </TableCell>
                  <TableCell className="tabular-nums">{p.jersey}</TableCell>
                  <TableCell>
                    <Link to={`/players/${p.id}`} state={from.state} className="font-medium hover:underline">
                      {p.name}
                    </Link>
                  </TableCell>
                  <TableCell>{p.link_position_name}</TableCell>
                  <TableCell>{p.position_name}</TableCell>
                  <TableCell>
                    <OverallBadge value={p.overall} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TabsContent>
        <TabsContent value="raw" className="mt-4">
          <Section title={t('tab.raw')}>
            <RawTable raw={team.raw} />
          </Section>
        </TabsContent>
      </Tabs>

      <AlertDialog open={confirmReset} onOpenChange={setConfirmReset}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('edit.restoreTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('edit.restoreText')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => reset.mutate()}>
              {t('edit.restore')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
