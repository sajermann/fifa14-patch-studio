import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/api/client'
import { Facts, OriginalBadge, OverallBadge, RawTable, Section } from '@/components/common/detail'
import { EditActions, FieldsEditor, useEntityForm } from '@/components/common/edit'
import { Photo } from '@/components/common/pictures'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom, useTabParam } from '@/lib/back'
import { useStatus, useToken } from '@/state/queries'

const TABS = ['data', 'ratings', 'raw'] as const

export function PlayerPage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const lang = useStatus().data?.names_language ?? 'eng_us'
  const queryKey = ['player', token, lang, id]
  const { data, isLoading } = useQuery({ queryKey, queryFn: () => api.player(id), enabled: !!token })
  const tabs = useTabParam(TABS[0])
  const back = useBack({ to: '/players', label: { key: 'nav.players' } })
  const from = useFrom(data?.name ?? { key: 'nav.players' })
  const entity = useEntityForm({
    data,
    queryKey,
    invalidate: ['players', 'team'],
    save: (f) => api.savePlayer(id, f.fields),
    reset: () => api.resetPlayer(id),
  })
  if (isLoading || !data) return <LoadingBlock />
  const editor = (groups: string[], columns?: string) => (
    <FieldsEditor form={data} groups={groups} fields={entity.form.fields} setField={entity.setField} columns={columns} />
  )
  return (
    <div className="space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 items-center gap-3">
          <Photo id={data.id} size={96} available={data.has_photo} className="size-12" />
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold break-words">{data.name}</h1>
            <p className="text-sm text-muted-foreground">
              {[data.position_name, data.nationality_name, data.birthdate, `ID ${data.id}`].filter(Boolean).join(' · ')}
            </p>
          </div>
          <OriginalBadge edited={data.edited} />
        </div>
        <EditActions edited={data.edited} entity={entity} />
      </div>
      <Tabs {...tabs}>
        <TabsList>
          <TabsTrigger value="data">{t('player.tab.data')}</TabsTrigger>
          <TabsTrigger value="ratings">{t('player.tab.ratings')}</TabsTrigger>
          <TabsTrigger value="raw">{t('tab.raw')}</TabsTrigger>
        </TabsList>
        <TabsContent value="data" className="mt-4 space-y-4">
          {editor(['names', 'info', 'positions', 'style'])}
          <Section title={t('player.teams')}>
            <Facts
              items={data.teams.map((tm) => [
                <Link key={tm.id} to={`/teams/${tm.id}`} state={from.state} className="hover:underline">
                  {tm.name}
                </Link>,
                `#${tm.jersey ?? '—'} · ${tm.position_name ?? '—'}`,
              ])}
            />
          </Section>
        </TabsContent>
        <TabsContent value="ratings" className="mt-4 space-y-4">
          <div className="flex items-center gap-2 text-sm">
            {t('col.overall')} <OverallBadge value={data.overall} />
            <span className="text-xs text-muted-foreground">{t('player.overallHint')}</span>
          </div>
          {editor(['physical', 'mental', 'skill', 'goalkeeper'], 'md:grid-cols-2 xl:grid-cols-4')}
        </TabsContent>
        <TabsContent value="raw" className="mt-4">
          <Section title={t('tab.raw')}>
            <RawTable raw={data.raw} />
          </Section>
        </TabsContent>
      </Tabs>
    </div>
  )
}
