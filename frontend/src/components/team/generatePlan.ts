/** What "Generate players" makes: the positions that complete a squad of GENERATED_SQUAD by line, counting the players
 * the squad already has. */

export const GENERATED_SQUAD = 18 // a generated squad never goes past this many players (the existing ones count)

type Line = 'goal' | 'fullback' | 'centreback' | 'midfield' | 'attack'

// a position code (teamplayerlinks / preferredposition1) -> its line; wingers count as attackers, wing-backs as full-backs
const lineOf = (code: number): Line | undefined => {
  if (code === 0) return 'goal'
  if ([2, 3, 7, 8].includes(code)) return 'fullback'
  if ([1, 4, 5, 6].includes(code)) return 'centreback'
  if (code >= 9 && code <= 19) return 'midfield'
  if (code >= 20 && code <= 27) return 'attack'
  return undefined
}

// the full squad, most needed first: the eleven of a 4-4-2, the second goalkeeper, then one reserve per line
// (GK, RB, LB, CB, CB, RM, LM, CM, CM, ST, ST | GK | RB, CB, CM, CM, ST, ST)
const PLAN = [0, 3, 7, 5, 5, 12, 16, 14, 14, 25, 25, 0, 3, 5, 14, 14, 25, 25]

/** The positions to generate, in order, for a squad whose players have these positions (null = unknown). At most
 * `max` players in the end (the smaller of GENERATED_SQUAD and the team's limit). Each existing player takes a place of
 * his line in the plan (his own position if it is still free, else the line's first free one); the free places are
 * generated in plan order up to the room left. */
export function generatePlan(existing: (number | null | undefined)[], max: number): number[] {
  const room = Math.max(Math.min(GENERATED_SQUAD, max) - existing.length, 0)
  const open = PLAN.map((code) => ({ code, line: lineOf(code) }))
  for (const code of existing) {
    const line = code == null ? undefined : lineOf(code)
    if (!line) continue
    const exact = open.findIndex((p) => p.code === code)
    const at = exact >= 0 ? exact : open.findIndex((p) => p.line === line)
    if (at >= 0) open.splice(at, 1)
  }
  return open.slice(0, room).map((p) => p.code)
}
