import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/api/client'
import { Facts, OriginalBadge, OverallBadge, RawTable, Section } from '@/components/common/detail'
import { BackButton, useBack, useFrom } from '@/lib/back'
import { cn } from '@/lib/utils'
import { Crest, LeagueImage } from '@/components/common/pictures'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { hasMessage, useI18n, type MessageKey } from '@/i18n'
import { useStatus, useToken } from '@/state/queries'

export function LeaguePage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const navigate = useNavigate()
  const lang = useStatus().data?.names_language ?? 'eng_us'
  const { data, isLoading } = useQuery({
    queryKey: ['league', token, lang, id],
    queryFn: () => api.league(id),
    enabled: !!token,
  })
  const back = useBack({ to: '/leagues', label: t('nav.leagues') })
  const from = useFrom(data?.name ?? t('nav.leagues'))
  if (isLoading || !data) return <LoadingBlock />
  return (
    <div className="space-y-4">
      <BackButton back={back} />
      <div className="flex min-w-0 items-center gap-3">
        <LeagueImage id={data.id} size={96} available={data.has_logo} className="size-12" />
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold break-words">{data.name}</h1>
          <p className="text-sm text-muted-foreground">
            {[data.country, data.level !== null ? t('leagues.level', { level: data.level }) : null, `ID ${data.id}`].filter(Boolean).join(' · ')}
          </p>
        </div>
        <OriginalBadge />
      </div>
      <Section title={t('league.names', { lang })}>
        <Facts
          items={data.name_keys.map((k) => {
            const key = `leagueName.${k}`
            return [hasMessage(key) ? t(key as MessageKey) : k, data.names[k]?.[lang] ?? data.names[k]?.eng_us ?? '—']
          })}
        />
      </Section>
      <Section title={t('col.teams')}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12" />
              <TableHead>{t('col.name')}</TableHead>
              <TableHead>{t('col.overall')}</TableHead>
              <TableHead>{t('col.players')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.teams.map((tm) => (
              <TableRow key={tm.id} className={cn('cursor-pointer', !tm.edited && 'text-muted-foreground')} onClick={() => navigate(`/teams/${tm.id}`, from)}>
                <TableCell>
                  <Crest id={tm.id} size={64} available={tm.has_crest} className="size-8" />
                </TableCell>
                <TableCell>
                  <span className="font-medium text-foreground">{tm.name}</span> <OriginalBadge edited={tm.edited} />
                </TableCell>
                <TableCell>
                  <OverallBadge value={tm.overall} />
                </TableCell>
                <TableCell className="tabular-nums">{tm.player_count}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>
      <Section title={t('tab.raw')}>
        <RawTable raw={data.raw} />
      </Section>
    </div>
  )
}
