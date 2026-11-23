import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api, type ListParams } from '@/api/client'
import type { ProjectIssue } from '@/api/types'

/** The backend status; polled while the game is being prepared or a job runs. */
export function useStatus() {
  return useQuery({
    queryKey: ['status'],
    queryFn: api.status,
    refetchInterval: (q) => {
      const s = q.state.data
      return s && (s.game.state === 'building' || s.job?.state === 'running') ? 500 : false
    },
  })
}

/** The token of the prepared game: part of every query key and picture URL, so another game never mixes in. */
export function useToken() {
  return useStatus().data?.game.token ?? ''
}

export function useList<T>(kind: 'countries' | 'leagues' | 'teams' | 'players' | 'stadiums', params: ListParams, fetcher: (p: ListParams) => Promise<T>) {
  const token = useToken()
  const lang = useStatus().data?.names_language
  return useQuery({ queryKey: [kind, token, lang, params], queryFn: () => fetcher(params), placeholderData: keepPreviousData, enabled: !!token })
}

export function useOptions() {
  const token = useToken()
  const lang = useStatus().data?.names_language
  return useQuery({ queryKey: ['options', token, lang], queryFn: api.options, enabled: !!token, staleTime: Infinity })
}

const NO_ISSUES: ProjectIssue[] = []

/** The project's problems. Under the 'status' key: every save already refreshes the status, so they follow it. */
export function useProjectIssues() {
  const token = useToken()
  const lang = useStatus().data?.names_language
  const query = useQuery({ queryKey: ['status', 'issues', token, lang], queryFn: api.issues, enabled: !!token })
  return query.data?.issues ?? NO_ISSUES
}

/** The problems of one league/team/player (optionally of one field). */
export function useIssues(kind: 'league' | 'team' | 'player', id: number | undefined, field?: string) {
  const issues = useProjectIssues()
  return useMemo(
    () => issues.filter((i) => i.kind === kind && i.id === id && (field === undefined || i.field === field)),
    [issues, kind, id, field],
  )
}
