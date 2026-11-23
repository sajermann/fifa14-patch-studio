import { Box, Check, ChevronUp, CloudRain, LoaderCircle, Moon, Snowflake, Sun, X, type LucideIcon } from 'lucide-react'
import { lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import type { StadiumInfo } from '@/api/types'
import { Badge, Facts, RawTable, Section } from '@/components/common/detail'
import { StadiumImage } from '@/components/common/pictures'
import { hasMessage, useI18n, type MessageKey } from '@/i18n'
import { cn } from '@/lib/utils'

const StadiumPreview = lazy(() => import('@/components/common/StadiumPreview')) // three.js only loads when asked

/** The stadium in 3D, built only when asked (a big stadium is tens of MB and takes seconds); `open` lives in the page,
 * which gives it half of the height when open. */
export function Stadium3D({ stadium, open, setOpen, className }: { stadium: StadiumInfo; open: boolean; setOpen: (v: boolean) => void; className?: string }) {
  const { t } = useI18n()
  return (
    <Section
      scroll={open}
      className={className}
      title={t('stadium3d.title')}
      action={
        stadium.times.length > 0 &&
        (open ? (
          <Button size="sm" variant="outline" onClick={() => setOpen(false)}>
            <ChevronUp /> {t('stadium3d.close')}
          </Button>
        ) : (
          <Button size="sm" onClick={() => setOpen(true)}>
            <Box /> {t('preview.show3d')}
          </Button>
        ))
      }
    >
      {!stadium.times.length ? (
        <p className="text-sm text-muted-foreground">{t('stadium3d.none')}</p>
      ) : open ? (
        <div className="flex h-full min-h-48 flex-col gap-2">
          <div className="min-h-0 flex-1 overflow-hidden rounded-md bg-muted">
            <Suspense
              fallback={
                <div className="flex size-full items-center justify-center text-muted-foreground">
                  <LoaderCircle className="size-6 animate-spin" />
                </div>
              }
            >
              <StadiumPreview id={stadium.id} times={stadium.times} />
            </Suspense>
          </div>
          <p className="text-xs text-muted-foreground">{t('stadium3d.hint')}</p>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{t('stadium3d.ask')}</p>
      )}
    </Section>
  )
}

const DAY = 1
const NIGHT = 3

/** What the match screen offers in the stadium: day, night, rain and snow, each with a tick or a cross. Rain or snow
 * allowed at only one of the times says which. */
function StadiumConditions({ conditions }: { conditions: StadiumInfo['conditions'] }) {
  const { t } = useI18n()
  if (!conditions.length) return <>{t('stadium.noConditions')}</>
  const times = conditions.map((c) => c.time_of_day)
  const only = (flag: 'rain' | 'snow') => {
    const at = conditions.filter((c) => c[flag]).map((c) => c.time_of_day)
    if (!at.length || at.length === conditions.length || at.length > 1) return undefined
    return at[0] === DAY ? t('stadium.cond.onlyDay') : at[0] === NIGHT ? t('stadium.cond.onlyNight') : undefined
  }
  const items: { icon: LucideIcon; label: string; on: boolean; note?: string }[] = [
    { icon: Sun, label: t('stadium.cond.day'), on: times.includes(DAY) },
    { icon: Moon, label: t('stadium.cond.night'), on: times.includes(NIGHT) },
    { icon: CloudRain, label: t('stadium.cond.rain'), on: conditions.some((c) => c.rain), note: only('rain') },
    { icon: Snowflake, label: t('stadium.cond.snow'), on: conditions.some((c) => c.snow), note: only('snow') },
  ]
  return (
    <span className="flex flex-wrap gap-1.5">
      {items.map(({ icon: Icon, label, on, note }) => (
        <span
          key={label}
          title={`${label}: ${t(on ? 'stadium.cond.yes' : 'stadium.cond.no')}${note ? ` (${note})` : ''}`}
          className={cn('inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs', !on && 'text-muted-foreground')}
        >
          <Icon className="size-3.5" />
          {label}
          {note && <span className="text-muted-foreground">({note})</span>}
          {on ? <Check className="size-3.5 text-emerald-600 dark:text-emerald-400" /> : <X className="size-3.5 text-destructive" />}
        </span>
      ))}
    </span>
  )
}

/** Data of the stadium on top, its menu pictures below one another (a click opens them big). */
export function StadiumDetails({ stadium: s, customName, title, className, scroll }: { stadium: StadiumInfo; customName?: string | null; title?: string; className?: string; scroll?: boolean }) {
  const { t } = useI18n()
  return (
    <Section scroll={scroll} className={className} title={title ?? t('section.stadium', { name: s.name })}>
      <Facts
        items={[
          ...Object.entries(s.names).map(([k, v]) => [hasMessage(`stadiumName.${k}`) ? t(`stadiumName.${k}` as MessageKey) : k, v] as [string, React.ReactNode]),
          ...(customName ? [[t('stadium.customName'), customName] as [string, React.ReactNode]] : []),
          [t('stadium.capacity'), s.capacity?.toLocaleString() ?? '—'],
          [t('stadium.yearBuilt'), s.year_built || '—'],
          [t('stadium.conditions'), <StadiumConditions key="w" conditions={s.conditions} />],
          [t('col.country'), s.country_id !== null && s.country ? <Link key="c" to={`/nations/${s.country_id}`} className="hover:underline">{s.country}</Link> : '—'],
          [t('stadium.homeTeam'), s.home_team ? <Link key="h" to={`/teams/${s.home_team.id}`} className="hover:underline">{s.home_team.name}</Link> : t('stadium.noHomeTeam')],
          [t('stadium.teamCount'), s.team_count],
          [t('col.id'), <Link key="i" to={`/stadiums/${s.id}`} className="hover:underline">{s.id}</Link>],
        ]}
      />
      <div className="mt-4 space-y-3">
        {s.pictures.length ? (
          s.pictures.map((v) => (
            <figure key={v} className="space-y-1">
              <StadiumImage id={s.id} variant={v} size={512} className="aspect-[981/278] w-full rounded border bg-muted/40" />
              <figcaption className="text-xs text-muted-foreground">{t('stadium.picture', { variant: v })}</figcaption>
            </figure>
          ))
        ) : (
          <p className="text-sm text-muted-foreground">{t('stadium.noPictures')}</p>
        )}
      </div>
    </Section>
  )
}

/** The files of the stadium and its database row (for whoever needs them; not the center of the screen). */
export function StadiumDatabase({ stadium: s, className }: { stadium: StadiumInfo; className?: string }) {
  const { t } = useI18n()
  return (
    <div className={cn('grid items-start gap-4 xl:grid-cols-2', className)}>
      <Section title={t('stadium.files', { count: s.files.length })}>
        <p className="mb-3 text-xs text-muted-foreground">{t('stadium.filesHint')}</p>
        <ul className="space-y-1 text-xs">
          {s.files.map((f) => (
            <li key={f.path} className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate font-mono">{f.path}</span>
              <Badge>{f.where ?? '—'}</Badge>
            </li>
          ))}
          {!s.files.length && <li className="text-muted-foreground">{t('stadium.noFiles')}</li>}
        </ul>
      </Section>
      <Section title={t('section.rawRow', { table: 'stadiums' })}>
        <RawTable raw={s.raw} />
      </Section>
    </div>
  )
}
