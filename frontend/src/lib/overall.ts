// A player's overall, worked out from his attributes and main position the way the game does it (same table as
// core/f14mod/overall.py): a weighted mean (weights add up to 100), capped at 99, plus the reputation bonus.

const ROLES: Record<string, Record<string, number>> = {
  r0: { gkreflexes: 22, gkhandling: 22, gkdiving: 24, gkpositioning: 22, gkkicking: 4, reactions: 6 },
  r1: { interceptions: 20, standingtackle: 14, marking: 12, slidingtackle: 12, headingaccuracy: 8, ballcontrol: 7, shortpassing: 6, reactions: 6, vision: 6, longpassing: 5, aggression: 4 },
  r2: { standingtackle: 11, slidingtackle: 10, crossing: 10, shortpassing: 10, ballcontrol: 10, interceptions: 10, marking: 9, stamina: 8, reactions: 8, dribbling: 7, sprintspeed: 4, agility: 3 },
  r3: { slidingtackle: 13, standingtackle: 12, interceptions: 12, marking: 10, stamina: 8, reactions: 8, crossing: 7, headingaccuracy: 7, ballcontrol: 7, shortpassing: 6, sprintspeed: 5, aggression: 5 },
  r4: { marking: 15, standingtackle: 15, slidingtackle: 15, headingaccuracy: 10, strength: 10, aggression: 8, interceptions: 8, shortpassing: 5, ballcontrol: 5, reactions: 5, jumping: 4 },
  r5: { shortpassing: 13, interceptions: 13, longpassing: 11, marking: 10, standingtackle: 10, ballcontrol: 9, reactions: 9, vision: 8, stamina: 6, strength: 6, aggression: 5 },
  r6: { crossing: 14, dribbling: 14, ballcontrol: 12, shortpassing: 12, longpassing: 8, vision: 8, reactions: 7, positioning: 7, acceleration: 5, sprintspeed: 5, stamina: 5, agility: 3 },
  r7: { shortpassing: 15, longpassing: 13, vision: 12, ballcontrol: 10, dribbling: 9, reactions: 8, interceptions: 8, positioning: 8, standingtackle: 6, stamina: 6, longshots: 5 },
  r8: { shortpassing: 16, vision: 16, ballcontrol: 13, positioning: 12, dribbling: 11, reactions: 8, longshots: 6, finishing: 5, shotpower: 5, acceleration: 4, agility: 4 },
  r9: { finishing: 12, positioning: 12, dribbling: 11, ballcontrol: 11, shotpower: 10, longshots: 10, reactions: 10, shortpassing: 6, headingaccuracy: 5, vision: 5, acceleration: 4, sprintspeed: 4 },
  r10: { crossing: 16, dribbling: 16, ballcontrol: 13, shortpassing: 10, positioning: 9, acceleration: 6, sprintspeed: 6, reactions: 6, agility: 5, vision: 5, finishing: 4, longshots: 4 },
  r11: { finishing: 20, positioning: 12, headingaccuracy: 10, shotpower: 10, reactions: 10, dribbling: 8, ballcontrol: 8, volleys: 5, longshots: 5, acceleration: 5, sprintspeed: 4, strength: 3 },
}
const ROLE_OF_POSITION: Record<number, string> = { 0: 'r0', 1: 'r1', 2: 'r2', 3: 'r3', 4: 'r4', 5: 'r4', 6: 'r4', 7: 'r3', 8: 'r2', 9: 'r5', 10: 'r5', 11: 'r5', 12: 'r6', 13: 'r7', 14: 'r7', 15: 'r7', 16: 'r6', 17: 'r8', 18: 'r8', 19: 'r8', 20: 'r9', 21: 'r9', 22: 'r9', 23: 'r10', 24: 'r11', 25: 'r11', 26: 'r11', 27: 'r10' }

const bonus = (rep: number, base: number) =>
  rep === 3 ? (base > 50 ? 1 : 0) : rep === 4 ? (base > 68 ? 2 : base > 34 ? 1 : 0) : rep === 5 ? (base > 77 ? 3 : base > 51 ? 2 : base > 25 ? 1 : 0) : 0

/** `value(column)` gives the number of a database column (the edited one, else the game's). */
export function computeOverall(value: (column: string) => number | null | undefined): number | undefined {
  const role = ROLE_OF_POSITION[Number(value('preferredposition1'))]
  if (role === undefined) return undefined
  const total = Object.entries(ROLES[role]).reduce((sum, [col, w]) => sum + (Number(value(col)) || 0) * w, 0)
  const base = Math.min(Math.floor((total + 50) / 100), 99)
  return base + bonus(Number(value('internationalrep')) || 1, base)
}
