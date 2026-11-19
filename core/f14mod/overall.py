"""A player's overall rating, worked out from his attributes and main position the way the game does it.

Each position has a weighted mean of the attributes (the weights add up to 100), rounded, capped at 99, plus a bonus
for the international reputation. Checked against the clean game: 16319 of 16328 players come out exactly (the
others are one point off).
"""

# the attributes of each kind of position (database columns) and their weights
_ROLES = {
    # GK
    'r0': {'gkreflexes': 22, 'gkhandling': 22, 'gkdiving': 24, 'gkpositioning': 22, 'gkkicking': 4, 'reactions': 6},
    # SW
    'r1': {'interceptions': 20, 'standingtackle': 14, 'marking': 12, 'slidingtackle': 12, 'headingaccuracy': 8, 'ballcontrol': 7, 'shortpassing': 6, 'reactions': 6, 'vision': 6, 'longpassing': 5, 'aggression': 4},
    # RWB/LWB
    'r2': {'standingtackle': 11, 'slidingtackle': 10, 'crossing': 10, 'shortpassing': 10, 'ballcontrol': 10, 'interceptions': 10, 'marking': 9, 'stamina': 8, 'reactions': 8, 'dribbling': 7, 'sprintspeed': 4, 'agility': 3},
    # RB/LB
    'r3': {'slidingtackle': 13, 'standingtackle': 12, 'interceptions': 12, 'marking': 10, 'stamina': 8, 'reactions': 8, 'crossing': 7, 'headingaccuracy': 7, 'ballcontrol': 7, 'shortpassing': 6, 'sprintspeed': 5, 'aggression': 5},
    # RCB/CB/LCB
    'r4': {'marking': 15, 'standingtackle': 15, 'slidingtackle': 15, 'headingaccuracy': 10, 'strength': 10, 'aggression': 8, 'interceptions': 8, 'shortpassing': 5, 'ballcontrol': 5, 'reactions': 5, 'jumping': 4},
    # RDM/CDM/LDM
    'r5': {'shortpassing': 13, 'interceptions': 13, 'longpassing': 11, 'marking': 10, 'standingtackle': 10, 'ballcontrol': 9, 'reactions': 9, 'vision': 8, 'stamina': 6, 'strength': 6, 'aggression': 5},
    # RM/LM
    'r6': {'crossing': 14, 'dribbling': 14, 'ballcontrol': 12, 'shortpassing': 12, 'longpassing': 8, 'vision': 8, 'reactions': 7, 'positioning': 7, 'acceleration': 5, 'sprintspeed': 5, 'stamina': 5, 'agility': 3},
    # RCM/CM/LCM
    'r7': {'shortpassing': 15, 'longpassing': 13, 'vision': 12, 'ballcontrol': 10, 'dribbling': 9, 'reactions': 8, 'interceptions': 8, 'positioning': 8, 'standingtackle': 6, 'stamina': 6, 'longshots': 5},
    # RAM/CAM/LAM
    'r8': {'shortpassing': 16, 'vision': 16, 'ballcontrol': 13, 'positioning': 12, 'dribbling': 11, 'reactions': 8, 'longshots': 6, 'finishing': 5, 'shotpower': 5, 'acceleration': 4, 'agility': 4},
    # RF/CF/LF
    'r9': {'finishing': 12, 'positioning': 12, 'dribbling': 11, 'ballcontrol': 11, 'shotpower': 10, 'longshots': 10, 'reactions': 10, 'shortpassing': 6, 'headingaccuracy': 5, 'vision': 5, 'acceleration': 4, 'sprintspeed': 4},
    # RW/LW
    'r10': {'crossing': 16, 'dribbling': 16, 'ballcontrol': 13, 'shortpassing': 10, 'positioning': 9, 'acceleration': 6, 'sprintspeed': 6, 'reactions': 6, 'agility': 5, 'vision': 5, 'finishing': 4, 'longshots': 4},
    # RS/ST/LS
    'r11': {'finishing': 20, 'positioning': 12, 'headingaccuracy': 10, 'shotpower': 10, 'reactions': 10, 'dribbling': 8, 'ballcontrol': 8, 'volleys': 5, 'longshots': 5, 'acceleration': 5, 'sprintspeed': 4, 'strength': 3},
}
# main position id -> kind of position
ROLE_OF_POSITION = {0: 'r0', 1: 'r1', 2: 'r2', 3: 'r3', 4: 'r4', 5: 'r4', 6: 'r4', 7: 'r3', 8: 'r2', 9: 'r5', 10: 'r5', 11: 'r5', 12: 'r6', 13: 'r7', 14: 'r7', 15: 'r7', 16: 'r6', 17: 'r8', 18: 'r8', 19: 'r8', 20: 'r9', 21: 'r9', 22: 'r9', 23: 'r10', 24: 'r11', 25: 'r11', 26: 'r11', 27: 'r10'}


def _bonus(rep: int, base: int) -> int:
    """The international reputation (1-5) lifts a good rating by up to 3 points."""
    if rep == 3:
        return 1 if base > 50 else 0
    if rep == 4:
        return 2 if base > 68 else 1 if base > 34 else 0
    if rep == 5:
        return 3 if base > 77 else 2 if base > 51 else 1 if base > 25 else 0
    return 0


def compute_overall(row: dict) -> int | None:
    """The overall of a player row (database columns), or None when his main position is not a playing one."""
    role = ROLE_OF_POSITION.get(row.get('preferredposition1'))
    if role is None:
        return None
    total = sum((row.get(col) or 0) * weight for col, weight in _ROLES[role].items())
    base = min((total + 50) // 100, 99)
    return base + _bonus(row.get('internationalrep') or 1, base)
