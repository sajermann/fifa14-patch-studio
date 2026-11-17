import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api } from '@/api/client'
import { BackButton, Facts, OverallBadge, Rating, RawTable, Section } from '@/components/common/detail'
import { Photo } from '@/components/common/pictures'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { hasMessage, useI18n, type MessageKey } from '@/i18n'
import { useStatus, useToken } from '@/state/queries'

const GROUPS: Record<string, string[]> = {
  physical: ['acceleration', 'sprint_speed', 'agility', 'balance', 'jumping', 'stamina', 'strength', 'reactions'],
  mental: ['aggression', 'interceptions', 'positioning', 'vision'],
  skill: ['ball_control', 'crossing', 'curve', 'dribbling', 'finishing', 'freekick_accuracy', 'heading_accuracy', 'long_passing', 'long_shots', 'marking', 'penalties', 'short_passing', 'shot_power', 'sliding_tackle', 'standing_tackle', 'volleys'],
  goalkeeper: ['gk_diving', 'gk_handling', 'gk_kicking', 'gk_positioning', 'gk_reflexes'],
}

export function PlayerPage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const lang = useStatus().data?.names_language ?? 'eng_us'
  const { data, isLoading } = useQuery({ queryKey: ['player', token, lang, id], queryFn: () => api.player(id), enabled: !!token })
  if (isLoading || !data) return <LoadingBlock />
  const label = (k: string) => {
    const key = `attr.${k}`
    return hasMessage(key) ? t(key as MessageKey) : k
  }
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start gap-4">
        <BackButton fallback="/players" />
        <Photo id={data.id} size={128} available={data.has_photo} className="size-20" />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold">{data.name}</h1>
          <p className="text-sm text-muted-foreground">
            {[data.position_name, data.nationality_name, data.birthdate, `ID ${data.id}`].filter(Boolean).join(' · ')}
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          {t('col.overall')} <OverallBadge value={data.overall} />
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Section title={t('player.names')}>
          <Facts items={(['first', 'last', 'common', 'jersey_name'] as const).map((k) => [t(`playerName.${k}` as MessageKey), data.names[k] ?? '—'])} />
        </Section>
        <Section title={t('player.teams')}>
          <Facts
            items={data.teams.map((tm) => [
              <Link key={tm.id} to={`/teams/${tm.id}`} className="hover:underline">
                {tm.name}
              </Link>,
              `#${tm.jersey ?? '—'} · ${tm.position_name ?? '—'}`,
            ])}
          />
        </Section>
      </div>
      <p className="text-xs text-muted-foreground">{t('player.overallHint')}</p>
      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {Object.entries(GROUPS).map(([group, keys]) => (
          <Section key={group} title={t(`attrGroup.${group}` as MessageKey)}>
            <div className="space-y-2">
              {keys.map((k) => (
                <Rating key={k} label={label(k)} value={data.attributes[k]} />
              ))}
            </div>
          </Section>
        ))}
      </div>
      <Section title={t('tab.raw')}>
        <RawTable raw={data.raw} />
      </Section>
    </div>
  )
}
