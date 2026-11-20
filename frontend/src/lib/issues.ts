import type { ProjectIssue } from '@/api/types'
import { hasMessage, type MessageKey, type TFunction } from '@/i18n'

/** Validation message in the interface language (by code + params), else the code. */
export function issueText(t: TFunction, issue: ProjectIssue) {
  const key = `issue.${issue.code}`
  return hasMessage(key) ? t(key as MessageKey, issue.params) : issue.code
}

/** The page of the league/team/player of an issue, with its label ("Time: Nome"); null for a project-wide issue. */
export function issueLink(t: TFunction, issue: ProjectIssue) {
  if (!issue.kind || issue.id === null) return null
  const name = issue.name || `#${issue.id}`
  const label = { league: 'issues.linkLeague', team: 'issues.linkTeam', player: 'issues.linkPlayer' }[issue.kind] as MessageKey
  return { label: t(label, { name }), to: `/${issue.kind}s/${issue.id}` }
}
