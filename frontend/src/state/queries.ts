import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api, type ListParams } from '@/api/client'

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

export function useList<T>(kind: 'leagues' | 'teams' | 'players', params: ListParams, fetcher: (p: ListParams) => Promise<T>) {
  const token = useToken()
  const lang = useStatus().data?.names_language
  return useQuery({ queryKey: [kind, token, lang, params], queryFn: () => fetcher(params), placeholderData: keepPreviousData, enabled: !!token })
}

export function useOptions() {
  const token = useToken()
  const lang = useStatus().data?.names_language
  return useQuery({ queryKey: ['options', token, lang], queryFn: api.options, enabled: !!token, staleTime: Infinity })
}
