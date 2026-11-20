import type { ProjectIssue } from '@/api/types'
import { hasMessage, type MessageKey, type TFunction } from '@/i18n'

/** The parts of a face in the interface language, joined ("eyes, hair (3D model)"). */
export function facePartsText(t: TFunction, parts: readonly string[]) {
  return parts.map((p) => (hasMessage(`faces.part.${p}`) ? t(`faces.part.${p}` as MessageKey) : p)).join(', ')
}

/** Validation message in the interface language (by code + params), else the code. */
export function issueText(t: TFunction, issue: ProjectIssue) {
  const key = `issue.${issue.code}`
  const params = Array.isArray(issue.params.parts) ? { ...issue.params, parts: facePartsText(t, issue.params.parts as string[]) } : issue.params
  return hasMessage(key) ? t(key as MessageKey, params) : issue.code
}

/** The page of the league/team/player of an issue, with its label ("Time: Nome"); null for a project-wide issue. */
export function issueLink(t: TFunction, issue: ProjectIssue) {
  if (!issue.kind || issue.id === null) return null
  const name = issue.name || `#${issue.id}`
  const label = { league: 'issues.linkLeague', team: 'issues.linkTeam', player: 'issues.linkPlayer' }[issue.kind] as MessageKey
  return { label: t(label, { name }), to: `/${issue.kind}s/${issue.id}` }
}
