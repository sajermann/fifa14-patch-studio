import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/api/client'
import { Facts, OriginalBadge, OverallBadge, RawTable, Section } from '@/components/common/detail'
import { EditActions, FieldsEditor, NamesEditor, useEntityForm } from '@/components/common/edit'
import { HideButton, OutOfPatchBadge, usePendingHide } from '@/components/common/HideButton'
import { ColorDot, Crest, Photo } from '@/components/common/pictures'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom, useTabParam } from '@/lib/back'
import { useToken } from '@/state/queries'

const TABS = ['names', 'data', 'roster', 'raw'] as const

export function TeamPage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const queryKey = ['team', token, id]
  const { data: team, isLoading } = useQuery({ queryKey, queryFn: () => api.team(id), enabled: !!token })
  const tabs = useTabParam(TABS[0])
  const from = useFrom(team?.name ?? t('nav.teams'))
  const back = useBack({ to: '/teams', label: t('nav.teams') })
  const hide = usePendingHide(team?.hidden)
  const entity = useEntityForm({
    data: team,
    queryKey,
    invalidate: ['teams', 'league', 'leagues'],
    save: async (f) => {
      let saved = await api.saveTeam(id, f.names, f.fields)
      if (hide.pending !== null) saved = await api.setTeamHidden(id, hide.pending)
      hide.clear()
      return saved
    },
    reset: () => {
      hide.clear()
      return api.resetTeam(id)
    },
    extraDirty: hide.pending !== null,
    onDiscard: hide.clear,
  })
  if (isLoading || !team) return <LoadingBlock />
  return (
    <div className="space-y-4">
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
          {hide.hidden && <OutOfPatchBadge alert label={t('teams.hiddenByProject')} />}
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <EditActions edited={team.edited} entity={entity} />
          <HideButton
            variant="outline"
            hidden={hide.hidden}
            onToggle={hide.toggle}
            hideHint={t('teams.originalHideHint')}
            showHint={t('teams.originalShowHint')}
          />
        </div>
      </div>

      <Tabs {...tabs}>
        <TabsList>
          <TabsTrigger value="names">{t('team.tab.names')}</TabsTrigger>
          <TabsTrigger value="data">{t('team.tab.data')}</TabsTrigger>
          <TabsTrigger value="roster">
            {t('team.tab.roster')} ({team.roster.length})
          </TabsTrigger>
          <TabsTrigger value="raw">{t('tab.raw')}</TabsTrigger>
        </TabsList>
        <TabsContent value="names" className="mt-4">
          <NamesEditor kind="team" nameKeys={team.name_keys} languages={team.languages} original={team.original_names} names={entity.form.names} setNames={entity.setNames} />
        </TabsContent>
        <TabsContent value="data" className="mt-4 space-y-4">
          <Section title={t('team.ratings')} description={t('team.ratingsHint')}>
            <Facts
              items={[
                [t('col.overall'), <OverallBadge key="o" value={team.overall} />],
                [t('team.attack'), team.attack],
                [t('team.midfield'), team.midfield],
                [t('team.defense'), team.defense],
              ]}
            />
          </Section>
          <FieldsEditor form={team} groups={['colors', 'club', 'takers', 'tactics']} fields={entity.form.fields} setField={entity.setField} roster={team.roster} />
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
    </div>
  )
}
